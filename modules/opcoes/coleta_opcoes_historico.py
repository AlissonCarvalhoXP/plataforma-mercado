"""Coletor de HISTORICO real de opcoes (para o backtest) - v2 com vencimentos PASSADOS.

Descobre vencimentos JA VENCIDOS da PETR4 (que tem historico completo)
em vez de so as series futuras (que mal nasceram).

Fluxo do modo historico:
1. /expirations?includeExpired=true -> lista todos os vencimentos
2. filtra os JA VENCIDOS (mais recentes primeiro)
3. /chain naquele vencimento -> series negociadas
4. /analytics/history de cada serie -> IV, gregas, preco por dia
-> grava tudo na tabela ADITIVA opcoes_historico

Uso:
python coleta_opcoes_historico.py --historico --vencimentos 2 --pausa 5
python coleta_opcoes_historico.py --limite 5 --pausa 5
python coleta_opcoes_historico.py PETRU346W4
"""
from __future__ import annotations
import os, sys, sqlite3, time
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
import db_opcoes

BASE = "https://brapi.dev/api"


def _token():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    return os.getenv("BRAPI_TOKEN")


def init_hist_schema(db_path=None):
    """Cria a tabela de historico (aditivo, idempotente)."""
    con = sqlite3.connect(db_path or db_opcoes.DB_PATH)
    con.execute("""
    CREATE TABLE IF NOT EXISTS opcoes_historico (
    Codigo_Opcao TEXT NOT NULL,
    Ativo_Objeto TEXT,
    Tipo TEXT,
    Strike REAL,
    Data_Vencimento TEXT,
    Data TEXT NOT NULL,
    Preco_Ativo REAL,
    Preco_Opcao REAL,
    IV REAL,
    Delta REAL,
    Gamma REAL,
    Theta REAL,
    Vega REAL,
    Taxa_Livre_Risco REAL,
    Fonte TEXT DEFAULT 'brapi',
    PRIMARY KEY (Codigo_Opcao, Data)
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_hist_ativo_data "
                "ON opcoes_historico (Ativo_Objeto, Data)")
    con.commit()
    con.close()


def _get(path, params, token, max_retries=5):
    """GET com retry e backoff exponencial em caso de 429 (rate limit)."""
    import requests
    h = {"Authorization": f"Bearer {token}"} if token else {}
    espera = 5
    for tentativa in range(max_retries):
        r = requests.get(f"{BASE}{path}", params=params, headers=h, timeout=25)
        if r.status_code == 429:
            ra = r.headers.get("Retry-After")
            pausa = int(ra) if (ra and ra.isdigit()) else espera
            print(f" (429) rate limit - aguardando {pausa}s "
                  f"[tentativa {tentativa+1}/{max_retries}]")
            time.sleep(pausa)
            espera = min(espera * 2, 60)
            continue
        r.raise_for_status()
        d = r.json()
        if isinstance(d, dict) and d.get("error"):
            raise RuntimeError(f"brapi: {d.get('message')} ({d.get('code')})")
        return d
    raise RuntimeError("429 persistente - limite de requisicoes atingido. "
                       "Tente novamente mais tarde ou use um token (plano maior).")


def coletar_serie(symbol, expiry, token, db_path=None, start=None, end=None) -> int:
    """Puxa analytics/history de uma serie e grava linha a linha."""
    params = {"symbol": symbol, "expirationDate": expiry, "sortOrder": "asc"}
    if start:
        params["startDate"] = start
    if end:
        params["endDate"] = end
    data = _get("/v2/options/analytics/history", params, token)

    opt = data.get("option", {})
    ativo = opt.get("underlyingSymbol")
    tipo = "CALL" if str(opt.get("side", "")).upper().startswith("C") else "PUT"
    strike = opt.get("strike")
    venc = opt.get("expirationDate", expiry)[:10]

    con = sqlite3.connect(db_path or db_opcoes.DB_PATH)
    n = 0
    for a in opt.get("analytics", []):
        con.execute("""
        INSERT INTO opcoes_historico
        (Codigo_Opcao,Ativo_Objeto,Tipo,Strike,Data_Vencimento,Data,
        Preco_Ativo,Preco_Opcao,IV,Delta,Gamma,Theta,Vega,Taxa_Livre_Risco,Fonte)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'brapi')
        ON CONFLICT(Codigo_Opcao,Data) DO UPDATE SET
        Preco_Ativo=excluded.Preco_Ativo, Preco_Opcao=excluded.Preco_Opcao,
        IV=excluded.IV, Delta=excluded.Delta
        """, (symbol, ativo, tipo, strike, venc, a.get("date"),
               a.get("underlyingPrice"), a.get("optionPrice"),
               a.get("impliedVolatility"), a.get("delta"), a.get("gamma"),
               a.get("theta"), a.get("vega"), a.get("riskFreeRate")))
        n += 1
    con.commit()
    con.close()
    return n


# ---------------- MODO HISTORICO (vencimentos passados) ----------------
def vencimentos_passados(ativo, token, quantos=2):
    """Lista vencimentos JA VENCIDOS (mais recentes primeiro)."""
    exp = _get("/v2/options/expirations",
               {"underlying": ativo, "includeExpired": "true"}, token)
    datas = exp.get("expirations", [])
    hoje = date.today()
    passados = [d for d in datas if date.fromisoformat(d) < hoje]
    passados.sort(reverse=True)
    return passados[:quantos]


def series_do_vencimento(ativo, expiry, token):
    """Lista os codigos das series negociadas naquele vencimento."""
    ch = _get("/v2/options/chain",
              {"underlying": ativo, "expirationDate": expiry}, token)
    return [s["symbol"] for s in ch.get("series", []) if s.get("symbol")]


def _ja_coletadas(db_path=None):
    con = sqlite3.connect(db_path or db_opcoes.DB_PATH)
    try:
        rows = con.execute("SELECT DISTINCT Codigo_Opcao FROM opcoes_historico").fetchall()
    except sqlite3.OperationalError:
        rows = []
    con.close()
    return {r[0] for r in rows}


def coletar_historico(ativo="PETR4", n_vencimentos=2, pausa=5.0,
                     max_series_por_venc=None):
    """Modo principal: varre vencimentos passados e coleta o historico completo."""
    token = _token()
    init_hist_schema()
    feitas = _ja_coletadas()

    vencs = vencimentos_passados(ativo, token, n_vencimentos)
    if not vencs:
        print(f"Nenhum vencimento passado encontrado para {ativo}.")
        return
    print(f"Modo historico | ativo {ativo} | token: {'sim' if token else 'sandbox'}")
    print(f"Vencimentos ja vencidos selecionados: {vencs}")

    total = 0
    for venc in vencs:
        try:
            symbols = series_do_vencimento(ativo, venc, token)
        except Exception as e:
            print(f" venc {venc}: FALHOU ao listar series - {e}")
            if "429" in str(e):
                print(" >> Limite atingido. Rode de novo mais tarde (retoma).")
                break
            continue

        pendentes = [s for s in symbols if s not in feitas]
        if max_series_por_venc:
            pendentes = pendentes[:max_series_por_venc]
        print(f" venc {venc}: {len(symbols)} series ({len(pendentes)} a coletar)")
        time.sleep(pausa)

        for sym in pendentes:
            try:
                n = coletar_serie(sym, venc, token)
                total += n
                print(f" {sym}: {n} dias")
                feitas.add(sym)
                time.sleep(pausa)
            except Exception as e:
                print(f" {sym}: FALHOU - {e}")
                if "429" in str(e) or "limite" in str(e).lower():
                    print(" >> Limite atingido. Rode de novo mais tarde (retoma).")
                    print(f"Total nesta rodada: {total} pontos")
                    return
    print(f"Total nesta rodada: {total} pontos gravados em opcoes_historico")


# ---------------- MODO ANTIGO (series ja no banco) ----------------
def _series_no_banco(ativo_prefixo="PETR", db_path=None):
    con = sqlite3.connect(db_path or db_opcoes.DB_PATH)
    rows = con.execute(
        "SELECT DISTINCT Codigo_Opcao, Data_Vencimento FROM opcoes_series "
        "WHERE Codigo_Opcao LIKE ?", (ativo_prefixo + "%",)).fetchall()
    con.close()
    return rows


def main_banco(symbols=None, limite=None, pausa=3.0, pular_coletadas=True):
    token = _token()
    init_hist_schema()
    if symbols:
        alvos = [(s, None) for s in symbols]
    else:
        alvos = _series_no_banco("PETR")
    if pular_coletadas:
        feitas = _ja_coletadas()
        alvos = [(s, v) for (s, v) in alvos if s not in feitas]
    if feitas:
        print(f"(retomando: {len(feitas)} serie(s) ja coletadas serao puladas)")
    if limite:
        alvos = alvos[:limite]
    print(f"Historico - {len(alvos)} serie(s) nesta rodada | "
          f"token: {'sim' if token else 'sandbox'} | pausa {pausa}s")
    total = 0
    for symbol, venc in alvos:
        try:
            if venc is None:
                con = sqlite3.connect(db_opcoes.DB_PATH)
                r = con.execute("SELECT Data_Vencimento FROM opcoes_series "
                               "WHERE Codigo_Opcao=? LIMIT 1", (symbol,)).fetchone()
                con.close()
                venc = r[0][:10] if r else None
            if not venc:
                print(f" {symbol}: sem vencimento no banco - pulado")
                continue
            n = coletar_serie(symbol, venc, token)
            total += n
            print(f" {symbol}: {n} dias de historico")
            time.sleep(pausa)
        except Exception as e:
            print(f" {symbol}: FALHOU - {e}")
            if "429" in str(e) or "limite" in str(e).lower():
                print(" >> Limite atingido. Rode de novo mais tarde (retoma).")
                break
    print(f"Total nesta rodada: {total} pontos gravados em opcoes_historico")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*", help="series especificas (opcional)")
    ap.add_argument("--historico", action="store_true",
                    help="modo historico: busca vencimentos JA VENCIDOS (recomendado)")
    ap.add_argument("--ativo", default="PETR4", help="ativo-objeto (default PETR4)")
    ap.add_argument("--vencimentos", type=int, default=2,
                    help="qtos vencimentos passados coletar (modo historico)")
    ap.add_argument("--max-series", type=int, default=None,
                    help="max series por vencimento (modo historico)")
    ap.add_argument("--limite", type=int, default=None, help="max series (modo banco)")
    ap.add_argument("--pausa", type=float, default=5.0, help="segundos entre chamadas")
    args = ap.parse_args()

    if args.historico:
        coletar_historico(args.ativo, args.vencimentos, args.pausa, args.max_series)
    else:
        main_banco(args.symbols or None, limite=args.limite, pausa=args.pausa)
