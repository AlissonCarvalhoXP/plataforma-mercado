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

# Opções negociando abaixo disso (residuais de fim de vida, quase sem valor)
# saem do ranking: o preço justo (Black-Scholes) também fica perto de zero
# nesses casos, e Desconto=(justo-mercado)/justo explode numericamente
# (ex.: -9000%), dominando o Score e tornando peso_diff irrelevante - achado
# real ao calibrar o backtest com dados historicos. Sem intervalo de preco
# relevante, uma tese de mispricing tambem nao importa economicamente aqui.
PRECO_MINIMO_RELEVANTE = 0.05


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
        if mkt < PRECO_MINIMO_RELEVANTE:
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


# ---------------- Sugestao de hedge (Fase E — carteira -> Opcoes) ----------------
DISCLAIMER_HEDGE = ("⚠️ Sugestão de apoio à decisão e estudo quantitativo — "
                     "NÃO constitui recomendação de investimento.")

LOTE_PADRAO_B3 = 100

# (direcao da posicao, regime de vol) -> (tipo de estrutura, Tipo de opcao, lado)
REGRAS_HEDGE = {
    ("long", "ALTA"): ("venda coberta de CALL", "CALL", "vender"),
    ("long", "BAIXA"): ("proteção via compra de PUT", "PUT", "comprar"),
    ("long", "NEUTRA"): ("proteção via compra de PUT", "PUT", "comprar"),
    ("short", "ALTA"): ("venda coberta de PUT", "PUT", "vender"),
    ("short", "BAIXA"): ("proteção via compra de CALL", "CALL", "comprar"),
    ("short", "NEUTRA"): ("proteção via compra de CALL", "CALL", "comprar"),
}


def _formatar_moeda(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def sugerir_hedge(posicao: dict, ranking: list[dict], spot: float, regime: str) -> dict | None:
    """Sugere um tipo de estrutura de opcoes (com serie e dimensionamento) para
    uma posicao existente na carteira, cruzando direcao x regime de vol.
    Devolve None se nao houver ranking disponivel para o ativo (sem dados de
    opcoes coletados) ou se a direcao/regime nao forem reconhecidos.

    Nao substitui nem depende do screener/ranking generico (analisar()), que
    continua apontando oportunidades em qualquer ativo, com ou sem posicao."""
    if not ranking or not spot or spot <= 0:
        return None

    direcao = str(posicao.get("direcao", "")).strip().lower()
    regra = REGRAS_HEDGE.get((direcao, regime))
    if regra is None:
        return None

    tipo_estrutura, tipo_opcao, lado = regra
    ativo = posicao.get("ativo", "")

    candidatas = [linha for linha in ranking
                  if linha["Tipo"] == tipo_opcao and linha["Moneyness"] == "OTM"]
    if not candidatas:
        return None
    if lado == "vender":
        melhor = min(candidatas, key=lambda linha: linha["Score"])
    else:
        melhor = max(candidatas, key=lambda linha: linha["Score"])

    tamanho = float(posicao.get("tamanho", 0) or 0)
    quantidade_acoes = tamanho / spot
    contratos = int(quantidade_acoes // LOTE_PADRAO_B3)

    if contratos < 1:
        texto = (
            f"Posição de {_formatar_moeda(tamanho)} em {ativo} é menor que 1 "
            f"lote-padrão ({LOTE_PADRAO_B3} ações) ao preço atual "
            f"(R$ {spot:.2f}) — hedge via opções não é viável neste tamanho. "
            f"{DISCLAIMER_HEDGE}"
        )
        return {
            "ativo": ativo, "direcao_posicao": direcao, "tipo_estrutura": tipo_estrutura,
            "codigo_opcao_sugerida": None, "contratos": 0, "texto": texto,
        }

    texto = (
        f"{ativo} ({direcao}, {_formatar_moeda(tamanho)}): {tipo_estrutura} — "
        f"{lado} {contratos} contrato(s) de {melhor['Codigo_Opcao']} "
        f"(strike R$ {melhor['Strike']:.2f}, vencimento {melhor['Data_Vencimento']}). "
        f"{DISCLAIMER_HEDGE}"
    )
    return {
        "ativo": ativo, "direcao_posicao": direcao, "tipo_estrutura": tipo_estrutura,
        "codigo_opcao_sugerida": melhor["Codigo_Opcao"], "contratos": contratos, "texto": texto,
    }


# ---------------- Oportunidades em destaque (Fase F — clareza do ranking) ----------------
def _texto_desconto(linha: dict) -> str:
    """Formata o desconto para exibicao. Quando o justo (Black-Scholes) e'
    proximo de zero (opcao bem fora do dinheiro/perto do vencimento), a razao
    (justo-mercado)/justo explode numericamente (ex.: -9000%) - nesses casos
    mostra a diferenca em R$ em vez de um percentual sem sentido."""
    desconto_pct = linha["Desconto"] * 100
    if abs(desconto_pct) > 100:
        diferenca = linha["Justo_BS"] - linha["Preco_Mercado"]
        return f"desconto extremo (justo ~R$ {linha['Justo_BS']:.2f}, diferença R$ {diferenca:+.2f})"
    return f"desconto {desconto_pct:+.1f}% sobre o justo"


def _texto_oportunidade(linha: dict, sinal: str) -> dict:
    direcao_txt = "COMPRA" if sinal == "COMPRAR_VOL" else "VENDA"
    texto = (
        f"{linha['Codigo_Opcao']} ({linha['Tipo']}, strike R$ {linha['Strike']:.2f}, "
        f"vence em {linha['Dias']} dias) — sinal de {direcao_txt} de volatilidade "
        f"({_texto_desconto(linha)}, "
        f"IV {linha['Diff_pp']:+.1f}pp vs. HV, liquidez {linha['Liquidez']})."
    )
    return {
        "codigo_opcao": linha["Codigo_Opcao"], "tipo": linha["Tipo"],
        "sinal": sinal, "texto": texto,
    }


def destacar_oportunidades(ranking: list[dict]) -> dict:
    """Extrai a melhor oportunidade de compra e de venda de volatilidade do
    ranking ja calculado por analisar() (mesmos filtros de liquidez/peso ja
    aplicados por quem chamou). Chave com valor None quando nao ha candidata
    daquele lado (ex.: ranking vazio, ou so ha sinais de um lado)."""
    compras = [linha for linha in ranking if linha["Sinal"] == "COMPRAR_VOL"]
    vendas = [linha for linha in ranking if linha["Sinal"] == "VENDER_VOL"]

    melhor_compra = max(compras, key=lambda linha: linha["Score"]) if compras else None
    melhor_venda = min(vendas, key=lambda linha: linha["Score"]) if vendas else None

    return {
        "compra": _texto_oportunidade(melhor_compra, "COMPRAR_VOL") if melhor_compra else None,
        "venda": _texto_oportunidade(melhor_venda, "VENDER_VOL") if melhor_venda else None,
    }


if __name__ == "__main__":
    ranking_exemplo = [
        {"Codigo_Opcao": "PETRC300", "Tipo": "CALL", "Strike": 32.0,
         "Data_Vencimento": "2026-10-16", "Moneyness": "OTM", "Score": 5.0},
        {"Codigo_Opcao": "PETRC310", "Tipo": "CALL", "Strike": 33.0,
         "Data_Vencimento": "2026-10-16", "Moneyness": "OTM", "Score": 8.0},
        {"Codigo_Opcao": "PETRP280", "Tipo": "PUT", "Strike": 28.0,
         "Data_Vencimento": "2026-10-16", "Moneyness": "OTM", "Score": 6.0},
        {"Codigo_Opcao": "PETRP290", "Tipo": "PUT", "Strike": 29.0,
         "Data_Vencimento": "2026-10-16", "Moneyness": "OTM", "Score": 9.0},
    ]
    spot = 30.0
    posicao_long = {"ativo": "PETR4", "direcao": "long", "tamanho": 30000.0}
    posicao_short = {"ativo": "PETR4", "direcao": "short", "tamanho": 30000.0}

    # Caso 1: long + ALTA -> venda coberta de CALL, melhor Score entre as CALLs OTM
    r = sugerir_hedge(posicao_long, ranking_exemplo, spot, "ALTA")
    assert r["tipo_estrutura"] == "venda coberta de CALL"
    assert r["codigo_opcao_sugerida"] == "PETRC300"  # vender -> pega o menor Score (5.0 < 8.0)
    assert r["contratos"] == 10  # 30000/30 = 1000 acoes / 100 = 10 contratos
    print("[OK] Caso 1: long + ALTA -> venda coberta de CALL, melhor Score, dimensionado.")

    # Caso 2: long + BAIXA -> protecao via compra de PUT
    r = sugerir_hedge(posicao_long, ranking_exemplo, spot, "BAIXA")
    assert r["tipo_estrutura"] == "proteção via compra de PUT"
    assert r["codigo_opcao_sugerida"] == "PETRP290"  # Score 9.0 > 6.0
    print("[OK] Caso 2: long + BAIXA -> proteção via compra de PUT.")

    # Caso 3: short + ALTA -> venda coberta de PUT
    r = sugerir_hedge(posicao_short, ranking_exemplo, spot, "ALTA")
    assert r["tipo_estrutura"] == "venda coberta de PUT"
    assert r["codigo_opcao_sugerida"] == "PETRP280"  # vender -> pega o menor Score (6.0 < 9.0)
    print("[OK] Caso 3: short + ALTA -> venda coberta de PUT.")

    # Caso 4: short + NEUTRA -> protecao via compra de CALL
    r = sugerir_hedge(posicao_short, ranking_exemplo, spot, "NEUTRA")
    assert r["tipo_estrutura"] == "proteção via compra de CALL"
    assert r["codigo_opcao_sugerida"] == "PETRC310"
    print("[OK] Caso 4: short + NEUTRA -> proteção via compra de CALL.")

    # Caso 5: posicao menor que 1 lote-padrao -> nao sugere 0 contratos, retorna aviso
    posicao_pequena = {"ativo": "PETR4", "direcao": "long", "tamanho": 500.0}
    r = sugerir_hedge(posicao_pequena, ranking_exemplo, spot, "ALTA")
    assert r["contratos"] == 0
    assert r["codigo_opcao_sugerida"] is None
    assert "lote-padrão" in r["texto"]
    print("[OK] Caso 5: posição menor que 1 lote-padrão -> aviso, sem sugestão de 0 contratos.")

    # Caso 6: sem ranking disponivel -> None
    assert sugerir_hedge(posicao_long, [], spot, "ALTA") is None
    print("[OK] Caso 6: sem ranking disponível -> None.")

    # Caso 7: destacar_oportunidades extrai a melhor compra e a melhor venda
    ranking_misto = [
        {"Codigo_Opcao": "PETRC300", "Tipo": "CALL", "Strike": 32.0, "Dias": 20,
         "Justo_BS": 1.50, "Preco_Mercado": 1.27, "Desconto": 0.153, "Diff_pp": -3.2,
         "Liquidez": 1200, "Score": 15.3, "Sinal": "COMPRAR_VOL"},
        {"Codigo_Opcao": "PETRC310", "Tipo": "CALL", "Strike": 33.0, "Dias": 20,
         "Justo_BS": 1.00, "Preco_Mercado": 0.95, "Desconto": 0.05, "Diff_pp": -1.0,
         "Liquidez": 800, "Score": 5.0, "Sinal": "COMPRAR_VOL"},
        {"Codigo_Opcao": "PETRP280", "Tipo": "PUT", "Strike": 28.0, "Dias": 20,
         "Justo_BS": 0.50, "Preco_Mercado": 0.54, "Desconto": -0.08, "Diff_pp": 4.5,
         "Liquidez": 600, "Score": -12.0, "Sinal": "VENDER_VOL"},
        {"Codigo_Opcao": "PETRP290", "Tipo": "PUT", "Strike": 29.0, "Dias": 20,
         "Justo_BS": 0.80, "Preco_Mercado": 0.82, "Desconto": -0.02, "Diff_pp": 1.0,
         "Liquidez": 900, "Score": -3.0, "Sinal": "VENDER_VOL"},
    ]
    dest = destacar_oportunidades(ranking_misto)
    assert dest["compra"]["codigo_opcao"] == "PETRC300"  # maior Score entre COMPRAR_VOL (15.3 > 5.0)
    assert "COMPRA" in dest["compra"]["texto"]
    assert dest["venda"]["codigo_opcao"] == "PETRP280"  # menor Score entre VENDER_VOL (-12.0 < -3.0)
    assert "VENDA" in dest["venda"]["texto"]
    print("[OK] Caso 7: destacar_oportunidades extrai a melhor compra e a melhor venda.")

    # Caso 8: sem candidatas de um lado (ou ranking vazio) -> None, sem excecao
    dest2 = destacar_oportunidades([ranking_misto[0]])
    assert dest2["compra"] is not None
    assert dest2["venda"] is None
    dest3 = destacar_oportunidades([])
    assert dest3["compra"] is None and dest3["venda"] is None
    print("[OK] Caso 8: sem candidatas de um lado (ou ranking vazio) -> None, sem excecao.")

    # Caso 9: justo perto de zero -> desconto extremo vira texto legivel, nao percentual absurdo
    linha_justo_zero = {
        "Codigo_Opcao": "PETRU446W4", "Tipo": "PUT", "Strike": 44.61, "Dias": 26,
        "Justo_BS": 0.01, "Preco_Mercado": 0.93, "Desconto": -91.0, "Diff_pp": 19.6,
        "Liquidez": 601, "Score": -50.0, "Sinal": "VENDER_VOL",
    }
    dest4 = destacar_oportunidades([linha_justo_zero])
    assert "extremo" in dest4["venda"]["texto"]
    assert "-9100" not in dest4["venda"]["texto"]  # nao mostra o percentual absurdo
    assert "R$ 0.01" in dest4["venda"]["texto"]  # mostra o justo em R$ no lugar
    print("[OK] Caso 9: justo perto de zero -> desconto extremo em R$, nao percentual absurdo.")

    # Caso 10: opcoes quase sem valor (abaixo de PRECO_MINIMO_RELEVANTE) saem do ranking
    underlying_teste = {"Spot": 40.0, "HV_60d": 0.30}
    series_teste = [
        {"Codigo_Opcao": "TESTE_OK", "Tipo": "CALL", "Strike": 40.0,
         "Data_Vencimento": "2026-09-15", "Ultimo": 1.50, "Bid": 0, "Ask": 0,
         "Volume": 100, "Open_Interest": 100, "IV_Fonte": None},
        {"Codigo_Opcao": "TESTE_RESIDUAL", "Tipo": "CALL", "Strike": 60.0,
         "Data_Vencimento": "2026-09-15", "Ultimo": 0.01, "Bid": 0, "Ask": 0,
         "Volume": 50, "Open_Interest": 50, "IV_Fonte": None},
    ]
    rank_teste = analisar(underlying_teste, series_teste, selic=0.14, hoje=date(2026, 8, 30))
    codigos = {l["Codigo_Opcao"] for l in rank_teste}
    assert "TESTE_OK" in codigos
    assert "TESTE_RESIDUAL" not in codigos
    print("[OK] Caso 10: opcoes com preco abaixo de PRECO_MINIMO_RELEVANTE sao excluidas do ranking.")

    print("\nTodos os casos passaram.")
