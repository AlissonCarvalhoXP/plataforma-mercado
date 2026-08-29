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
import sys
import math
from datetime import date

# permite rodar tanto como módulo quanto script
sys.path.insert(0, os.path.dirname(__file__))
import db_opcoes

BASE = "https://brapi.dev/api"
ATIVOS_PADRAO = ["PETR4"]          # amplie para ITSA4/investidas quando tiver plano Pro
DIAS_ALVO = 35


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


def main(ativos: list[str] | None = None):
    token = _token()
    db_opcoes.init_schema()
    ativos = ativos or ATIVOS_PADRAO
    print(f"Coleta de opções — {len(ativos)} ativo(s) | token: {'sim' if token else 'sandbox'}")
    for a in ativos:
        try:
            u, n = coletar_ativo(a, token)
            print(f"  {a}: {n} séries gravadas em mercado.db")
        except Exception as e:
            print(f"  {a}: FALHOU — {e}")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
