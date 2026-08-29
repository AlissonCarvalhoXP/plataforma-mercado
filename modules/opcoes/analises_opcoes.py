"""Camada de análise do Módulo de Opções (Fase C do handoff).

Porta os blocos 2 e 3 do protótipo para Python, usando scipy.stats.norm.
Recebe a cadeia lida do mercado.db e devolve o ranking enriquecido.

Taxa livre de risco: passar a Selic vinda de coleta_bcb (não usar valor fixo).
"""
from __future__ import annotations
import math
from dataclasses import dataclass, asdict
from datetime import date
import numpy as np
from scipy.stats import norm


# ---------------- Black-Scholes + gregas + IV (bloco 2) ----------------
def bs_price_delta(tipo: str, S: float, K: float, T: float, r: float, sig: float):
    if T <= 0 or sig <= 0:
        intr = max(S - K, 0.0) if tipo == "CALL" else max(K - S, 0.0)
        return intr, 0.0
    d1 = (math.log(S / K) + (r + sig * sig / 2) * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    if tipo == "CALL":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2), norm.cdf(d1)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1), norm.cdf(d1) - 1


def implied_vol(tipo, mkt, S, K, T, r):
    """Newton-Raphson com fallback de bisseção (trata o risco citado no handoff)."""
    if mkt <= 0 or T <= 0:
        return 0.0
    sig = 0.30
    for _ in range(60):
        price, _ = bs_price_delta(tipo, S, K, T, r, sig)
        d1 = (math.log(S / K) + (r + sig * sig / 2) * T) / (sig * math.sqrt(T))
        vega = S * norm.pdf(d1) * math.sqrt(T)
        if vega < 1e-8:
            break
        diff = price - mkt
        if abs(diff) < 1e-6:
            return round(sig, 6)
        sig -= diff / vega
        if sig <= 1e-4 or sig > 5:
            break
    lo, hi = 1e-4, 5.0
    for _ in range(200):
        mid = (lo + hi) / 2
        price, _ = bs_price_delta(tipo, S, K, T, r, mid)
        if abs(price - mkt) < 1e-6:
            return round(mid, 6)
        hi, lo = (mid, lo) if price > mkt else (hi, mid)
    return round((lo + hi) / 2, 6)


def moneyness(tipo, S, K, band=0.05):
    if abs(S - K) / S <= band:
        return "ATM"
    if tipo == "CALL":
        return "ITM" if S > K else "OTM"
    return "ITM" if S < K else "OTM"


# ---------------- Enriquecimento / ranking (bloco 3) ----------------
@dataclass
class LinhaRanking:
    Codigo_Opcao: str
    Tipo: str
    Strike: float
    Data_Vencimento: str
    Dias: int
    Preco_Mercado: float
    Justo_BS: float
    Desconto: float
    IV: float
    HV: float
    Diff_pp: float
    Moneyness: str
    Delta: float
    Liquidez: int
    Score: float
    Sinal: str


DIAS_BASE = 252  # convenção BR (dias úteis) — decisão registrada no handoff


def analisar(underlying: dict, series: list[dict], selic: float,
             peso_diff: float = 0.6, peso_liq: float = 0.05,
             liquidez_min: int = 0, hoje: date | None = None) -> list[dict]:
    """Enriquece a cadeia lida do banco e devolve o ranking (lista de dicts)."""
    hoje = hoje or date.today()
    S = underlying["Spot"]
    HV = underlying["HV_60d"]
    r = selic
    out: list[LinhaRanking] = []

    for s in series:
        venc = date.fromisoformat(s["Data_Vencimento"][:10])
        dias_corridos = max(1, (venc - hoje).days)
        # dias úteis ~ corridos * 252/365 (aproximação; refinar com calendário B3)
        T = (dias_corridos * DIAS_BASE / 365) / DIAS_BASE
        mkt = s.get("Ultimo") or 0
        if not mkt and s.get("Bid") and s.get("Ask"):
            mkt = (s["Bid"] + s["Ask"]) / 2
        if mkt <= 0:
            continue

        tipo = s["Tipo"]
        iv = s.get("IV_Fonte") or implied_vol(tipo, mkt, S, s["Strike"], T, r)
        justo, delta = bs_price_delta(tipo, S, s["Strike"], T, r, HV)
        desconto = (justo - mkt) / justo if justo > 0 else 0.0
        diff = (iv - HV) * 100
        liq = (s.get("Volume") or 0) + (s.get("Open_Interest") or 0)
        if liq < liquidez_min:
            continue
        score = desconto * 100 - diff * peso_diff + math.log1p(liq) * peso_liq
        sinal = "COMPRAR_VOL" if score > 0 else "VENDER_VOL"

        out.append(LinhaRanking(
            Codigo_Opcao=s["Codigo_Opcao"], Tipo=tipo, Strike=s["Strike"],
            Data_Vencimento=s["Data_Vencimento"][:10], Dias=dias_corridos,
            Preco_Mercado=round(mkt, 2), Justo_BS=round(justo, 2),
            Desconto=round(desconto, 4), IV=round(iv, 4), HV=round(HV, 4),
            Diff_pp=round(diff, 1), Moneyness=moneyness(tipo, S, s["Strike"]),
            Delta=round(delta, 3), Liquidez=liq, Score=round(score, 2), Sinal=sinal,
        ))

    out.sort(key=lambda x: abs(x.Score), reverse=True)
    return [asdict(x) for x in out]


def regime_volatilidade(series: list[dict], hv: float) -> str:
    """Compara IV média da cadeia com a HV 60d (bloco de estratégias)."""
    ivs = [s["IV_Fonte"] for s in series if s.get("IV_Fonte")]
    if not ivs:
        return "NEUTRA"
    avg = sum(ivs) / len(ivs)
    if avg > hv * 1.10:
        return "ALTA"
    if avg < hv * 0.92:
        return "BAIXA"
    return "NEUTRA"
