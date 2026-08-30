"""Coletor de opções B3 (Fase A do handoff) — segue o padrão de coleta_bcb / coleta_debentures.

Fluxo: brapi.dev (/expirations -> /chain) -> normaliza -> grava em mercado.db.
Spot vem da cotação; HV_60d é CALCULADA (log-retornos de 60 pregões * sqrt(252)).

Uso:
    python coleta_opcoes.py                 # coleta os ativos padrão
    python coleta_opcoes.py PETR4 ITSA4     # coleta específicos

Requer BRAPI_TOKEN no .env (PETR4 funciona no sandbox sem token).
"""
from __future__ import annotations
import os
import re
import sys
import math
from datetime import date
from pathlib import Path

# permite rodar tanto como módulo quanto script
sys.path.insert(0, os.path.dirname(__file__))
import db_opcoes

# repo root, para "from carteira import ler_carteira" (universo dinamico da carteira)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

BASE = "https://brapi.dev/api"
ATIVOS_PADRAO = ["PETR4"]          # amplie para ITSA4/investidas quando tiver plano Pro
DIAS_ALVO = 35
PADRAO_TICKER_B3 = re.compile(r"^[A-Z0-9]{4}\d{1,2}$")


def _token() -> str | None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    return os.getenv("BRAPI_TOKEN")


def _get(path: str, params: dict, token: str | None) -> dict:
    import requests
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.get(f"{BASE}{path}", params=params, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"brapi: {data.get('message')} ({data.get('code')})")
    return data


def _hv60(closes: list[float]) -> float:
    if len(closes) < 5:
        return 0.30
    r = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    r = r[-60:]
    m = sum(r) / len(r)
    var = sum((x - m) ** 2 for x in r) / (len(r) - 1)
    return round(math.sqrt(var * 252), 4)


def _pick_expiry(ativo: str, token) -> str:
    exp = _get("/v2/options/expirations", {"underlying": ativo}, token)
    datas = exp.get("expirations", [])
    if not datas:
        raise RuntimeError(f"Sem vencimentos para {ativo} (exige plano Pro?).")
    hoje = date.today()
    fut = [d for d in datas if date.fromisoformat(d) >= hoje]
    fut.sort(key=lambda d: abs((date.fromisoformat(d) - hoje).days - DIAS_ALVO))
    return fut[0] if fut else datas[0]


def coletar_ativo(ativo: str, token: str | None, db_path=None) -> tuple[int, int]:
    ref = date.today().isoformat()

    # --- ativo-objeto (spot + HV) ---
    q = _get("/v2/stocks/quote", {"symbols": ativo}, token)
    res = q["results"][0]
    d = res.get("data", res)
    spot = d.get("regularMarketPrice") or d.get("close")

    h = _get("/v2/stocks/historical",
             {"symbols": ativo, "range": "3mo", "interval": "1d", "sortOrder": "asc"}, token)
    hd = h["results"][0].get("data", h["results"][0])
    bars = sorted(hd.get("historicalDataPrice", []), key=lambda b: b.get("date", 0))
    closes = [b.get("adjustedClose") or b.get("close") for b in bars if b.get("close")]
    hv = _hv60(closes)

    db_opcoes.upsert_underlying([{
        "Ativo_Objeto": ativo, "Spot": float(spot), "HV_60d": hv,
        "Data_Referencia": ref, "Fonte": "brapi", "Status_Validacao": "OK",
    }], db_path)

    # --- cadeia de opções ---
    expiry = _pick_expiry(ativo, token)
    ch = _get("/v2/options/chain",
              {"underlying": ativo, "expirationDate": expiry}, token)
    rows = []
    for s in ch.get("series", []):
        side = str(s.get("side", "")).upper()
        tipo = "CALL" if side.startswith("C") else "PUT"
        rows.append({
            "Codigo_Opcao": s["symbol"], "Ativo_Objeto": ativo, "Tipo": tipo,
            "Strike": float(s["strike"]),
            "Data_Vencimento": s.get("expirationDate", expiry)[:10],
            "Bid": float(s.get("bid") or 0), "Ask": float(s.get("ask") or 0),
            "Ultimo": float(s.get("close") or s.get("average") or 0),
            "Volume": int(s.get("volume") or 0),
            "Open_Interest": int(s.get("openInterest") or s.get("trades") or 0),
            "IV_Fonte": None,                       # Pro traz IV; senão calculamos na análise
            "Data_Referencia": ref, "Fonte": "brapi", "Status_Validacao": "OK",
        })
    n = db_opcoes.upsert_series(rows, db_path)
    return 1, n


def _filtrar_tickers_b3(valores) -> list[str]:
    """Filtra uma lista de valores (ex.: coluna 'ativo' da carteira) para os que
    parecem tickers B3 (4 caracteres alfanuméricos + 1-2 dígitos, ex.: PETR4, ITUB4, B3SA3). Deduplica e
    ordena. Ignora tudo que nao bate com o padrao (ex.: 'CDB Banco X', 'USD/BRL')."""
    tickers = set()
    for valor in valores:
        ticker = str(valor).strip().upper()
        if PADRAO_TICKER_B3.match(ticker):
            tickers.add(ticker)
    return sorted(tickers)


def ativos_da_carteira() -> list[str]:
    """Le a tabela carteira do MIH (via carteira.ler_carteira()) e devolve os
    tickers B3 unicos reconhecidos. Nunca levanta excecao: banco indisponivel
    ou carteira vazia devolvem lista vazia."""
    try:
        from carteira import ler_carteira
        df = ler_carteira()
    except Exception:
        return []
    if df is None or df.empty or "ativo" not in df.columns:
        return []
    return _filtrar_tickers_b3(df["ativo"].tolist())


def main(ativos: list[str] | None = None):
    token = _token()
    db_opcoes.init_schema()
    ativos = ativos or sorted(set(ativos_da_carteira()) | set(ATIVOS_PADRAO))
    print(f"Coleta de opções — {len(ativos)} ativo(s) | token: {'sim' if token else 'sandbox'}")
    for a in ativos:
        try:
            u, n = coletar_ativo(a, token)
            print(f"  {a}: {n} séries gravadas em mercado.db")
        except Exception as e:
            print(f"  {a}: FALHOU — {e}")


if __name__ == "__main__":
    # Auto-teste rapido (o arquivo tambem e um CLI, entao nao ha bloco de teste
    # separado como em exposicao.py/analises.py) - roda antes de coletar de verdade.
    assert _filtrar_tickers_b3(
        ["PETR4", "ITUB4", "CDB Banco X", "USD/BRL", "petr4", "B3SA3"]
    ) == ["B3SA3", "ITUB4", "PETR4"]
    assert _filtrar_tickers_b3([]) == []
    print("[OK] _filtrar_tickers_b3 reconhece tickers B3 e ignora o resto, deduplicando.")

    main(sys.argv[1:] or None)
