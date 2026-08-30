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
    Skew_pp: float
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


def ajustar_sorriso(pontos: list[tuple[float, float]]):
    """Ajusta uma parabola IV=f(Strike) por minimos quadrados aos pontos
    (strike, iv) de um mesmo dia/Tipo, e devolve uma funcao strike->iv_esperada
    pelo formato da cadeia (o "sorriso" de vol). None se houver menos de 4
    strikes distintos - com 3 pontos a parabola tem 3 graus de liberdade pra
    3 parametros e simplesmente interpola tudo, residuo sempre zero."""
    strikes_distintos = sorted(set(k for k, _ in pontos))
    if len(strikes_distintos) < 4:
        return None
    ks = np.array([k for k, _ in pontos])
    ivs = np.array([v for _, v in pontos])
    coefs = np.polyfit(ks, ivs, 2)
    return lambda k: float(np.polyval(coefs, k))


def calcular_score(diff_pp: float, skew_pp: float, liq: int,
                    peso_diff: float = 0.6, peso_skew: float = 0.6,
                    peso_liq: float = 0.05) -> float:
    """Score do screener - positivo: vol parece barata (comprar); negativo:
    vol parece cara (vender). Dois eixos ortogonais de verdade:
    - diff_pp: gap entre IV e HV (vol atual vs. vol realizada)
    - skew_pp: gap entre a IV desta opcao e a IV que o sorriso do dia (outros
      strikes do mesmo vencimento) preveria pro seu strike

    Deliberadamente NAO usa "desconto" (preco-espaco): e' uma reexpressao
    nao-linear do mesmo gap que diff_pp ja mede - Black-Scholes e' monotonico
    em volatilidade, entao desconto e diff sao colineares por construcao, nao
    duas evidencias independentes. Achado real ao calibrar o backtest (o sweep
    de peso nunca mudava o sinal de nenhuma linha). Ver
    docs/superpowers/specs/2026-08-30-score-opcoes-sem-desconto-design.md."""
    return -diff_pp * peso_diff - skew_pp * peso_skew + math.log1p(max(0, liq)) * peso_liq


def analisar(underlying: dict, series: list[dict], selic: float,
             peso_diff: float = 0.6, peso_skew: float = 0.6, peso_liq: float = 0.05,
             liquidez_min: int = 0, hoje: date | None = None) -> list[dict]:
    """Enriquece a cadeia lida do banco e devolve o ranking (lista de dicts).

    Duas passadas: a primeira calcula preco/IV/prazo de cada serie relevante e
    agrupa (strike, iv) por Tipo pra ajustar o sorriso de vol do dia; a
    segunda usa esse sorriso pra calcular o Skew_pp de cada linha e o Score
    final (ver calcular_score)."""
    hoje = hoje or date.today()
    S = underlying["Spot"]
    HV = underlying["HV_60d"]
    r = selic

    calculados = []
    pontos_por_tipo: dict[str, list[tuple[float, float]]] = {"CALL": [], "PUT": []}
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
        liq = (s.get("Volume") or 0) + (s.get("Open_Interest") or 0)
        if liq < liquidez_min:
            continue

        calculados.append((s, mkt, tipo, dias_corridos, T, iv, liq))
        pontos_por_tipo.setdefault(tipo, []).append((s["Strike"], iv))

    sorrisos = {tipo: ajustar_sorriso(pontos) for tipo, pontos in pontos_por_tipo.items()}

    out: list[LinhaRanking] = []
    for s, mkt, tipo, dias_corridos, T, iv, liq in calculados:
        justo, delta = bs_price_delta(tipo, S, s["Strike"], T, r, HV)
        desconto = (justo - mkt) / justo if justo > 0 else 0.0
        diff = (iv - HV) * 100

        sorriso = sorrisos.get(tipo)
        iv_esperada = sorriso(s["Strike"]) if sorriso else None
        skew = (iv - iv_esperada) * 100 if iv_esperada is not None else 0.0

        score = calcular_score(diff, skew, liq, peso_diff, peso_skew, peso_liq)
        sinal = "COMPRAR_VOL" if score > 0 else "VENDER_VOL"

        out.append(LinhaRanking(
            Codigo_Opcao=s["Codigo_Opcao"], Tipo=tipo, Strike=s["Strike"],
            Data_Vencimento=s["Data_Vencimento"][:10], Dias=dias_corridos,
            Preco_Mercado=round(mkt, 2), Justo_BS=round(justo, 2),
            Desconto=round(desconto, 4), IV=round(iv, 4), HV=round(HV, 4),
            Diff_pp=round(diff, 1), Skew_pp=round(skew, 1),
            Moneyness=moneyness(tipo, S, s["Strike"]),
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
        f"IV {linha['Diff_pp']:+.1f}pp vs. HV, skew {linha['Skew_pp']:+.1f}pp vs. sorriso do dia, "
        f"liquidez {linha['Liquidez']})."
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
         "Justo_BS": 1.50, "Preco_Mercado": 1.27, "Desconto": 0.153, "Diff_pp": -3.2, "Skew_pp": 0.0,
         "Liquidez": 1200, "Score": 15.3, "Sinal": "COMPRAR_VOL"},
        {"Codigo_Opcao": "PETRC310", "Tipo": "CALL", "Strike": 33.0, "Dias": 20,
         "Justo_BS": 1.00, "Preco_Mercado": 0.95, "Desconto": 0.05, "Diff_pp": -1.0, "Skew_pp": 0.0,
         "Liquidez": 800, "Score": 5.0, "Sinal": "COMPRAR_VOL"},
        {"Codigo_Opcao": "PETRP280", "Tipo": "PUT", "Strike": 28.0, "Dias": 20,
         "Justo_BS": 0.50, "Preco_Mercado": 0.54, "Desconto": -0.08, "Diff_pp": 4.5, "Skew_pp": 0.0,
         "Liquidez": 600, "Score": -12.0, "Sinal": "VENDER_VOL"},
        {"Codigo_Opcao": "PETRP290", "Tipo": "PUT", "Strike": 29.0, "Dias": 20,
         "Justo_BS": 0.80, "Preco_Mercado": 0.82, "Desconto": -0.02, "Diff_pp": 1.0, "Skew_pp": 0.0,
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
        "Justo_BS": 0.01, "Preco_Mercado": 0.93, "Desconto": -91.0, "Diff_pp": 19.6, "Skew_pp": 0.0,
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

    # Caso 11: ajustar_sorriso exige >=4 strikes distintos (com 3, a parabola
    # simplesmente interpola tudo e o residuo seria sempre zero)
    pontos_ok = [(30.0, 0.35), (35.0, 0.30), (40.0, 0.28), (45.0, 0.32), (50.0, 0.40)]
    sorriso = ajustar_sorriso(pontos_ok)
    assert sorriso is not None
    assert abs(sorriso(40.0) - 0.28) < 0.1
    assert ajustar_sorriso([(30.0, 0.35), (35.0, 0.30), (40.0, 0.28)]) is None  # so 3 strikes
    assert ajustar_sorriso([(30.0, 0.35), (30.0, 0.36)]) is None  # 1 strike so (repetido)
    print("[OK] Caso 11: ajustar_sorriso exige >=4 strikes distintos, senao devolve None.")

    # Caso 12: calcular_score combina diff e skew no mesmo sentido; liquidez desempata
    s1 = calcular_score(diff_pp=-10.0, skew_pp=-5.0, liq=1000, peso_diff=0.6, peso_skew=0.6)
    assert s1 > 0  # os dois sinais dizem "vol barata" -> comprar
    s2 = calcular_score(diff_pp=10.0, skew_pp=5.0, liq=1000, peso_diff=0.6, peso_skew=0.6)
    assert s2 < 0  # os dois dizem "vol cara" -> vender
    s3 = calcular_score(diff_pp=0.0, skew_pp=0.0, liq=10000, peso_diff=0.6, peso_skew=0.6)
    s4 = calcular_score(diff_pp=0.0, skew_pp=0.0, liq=100, peso_diff=0.6, peso_skew=0.6)
    assert s3 > s4  # liquidez maior desempata pra cima
    print("[OK] Caso 12: calcular_score combina diff e skew (mesmo sentido), liquidez desempata.")

    # Caso 13: analisar() com menos de 4 strikes por Tipo -> Skew_pp = 0.0 (sem sorriso ajustavel)
    series_poucas_strikes = [
        {"Codigo_Opcao": "T1", "Tipo": "CALL", "Strike": 40.0,
         "Data_Vencimento": "2026-09-15", "Ultimo": 1.50, "Bid": 0, "Ask": 0,
         "Volume": 100, "Open_Interest": 100, "IV_Fonte": 0.30},
        {"Codigo_Opcao": "T2", "Tipo": "CALL", "Strike": 42.0,
         "Data_Vencimento": "2026-09-15", "Ultimo": 1.20, "Bid": 0, "Ask": 0,
         "Volume": 100, "Open_Interest": 100, "IV_Fonte": 0.32},
    ]
    rank_poucas = analisar(underlying_teste, series_poucas_strikes, selic=0.14, hoje=date(2026, 8, 30))
    assert all(l["Skew_pp"] == 0.0 for l in rank_poucas)
    print("[OK] Caso 13: menos de 4 strikes -> Skew_pp = 0.0, sem sorriso ajustavel.")

    # Caso 14: com 4+ strikes, uma opcao com IV destoante do sorriso do dia recebe Skew_pp != 0
    series_com_sorriso = [
        {"Codigo_Opcao": "S1", "Tipo": "CALL", "Strike": 35.0,
         "Data_Vencimento": "2026-09-15", "Ultimo": 5.00, "Bid": 0, "Ask": 0,
         "Volume": 100, "Open_Interest": 100, "IV_Fonte": 0.35},
        {"Codigo_Opcao": "S2", "Tipo": "CALL", "Strike": 40.0,
         "Data_Vencimento": "2026-09-15", "Ultimo": 1.50, "Bid": 0, "Ask": 0,
         "Volume": 100, "Open_Interest": 100, "IV_Fonte": 0.15},  # destoante do sorriso
        {"Codigo_Opcao": "S3", "Tipo": "CALL", "Strike": 45.0,
         "Data_Vencimento": "2026-09-15", "Ultimo": 0.50, "Bid": 0, "Ask": 0,
         "Volume": 100, "Open_Interest": 100, "IV_Fonte": 0.34},
        {"Codigo_Opcao": "S4", "Tipo": "CALL", "Strike": 50.0,
         "Data_Vencimento": "2026-09-15", "Ultimo": 0.20, "Bid": 0, "Ask": 0,
         "Volume": 100, "Open_Interest": 100, "IV_Fonte": 0.38},
    ]
    rank_sorriso = analisar(underlying_teste, series_com_sorriso, selic=0.14, hoje=date(2026, 8, 30))
    skew_s2 = next(l["Skew_pp"] for l in rank_sorriso if l["Codigo_Opcao"] == "S2")
    assert skew_s2 != 0.0
    print("[OK] Caso 14: opcao com IV destoante do sorriso do dia recebe Skew_pp != 0.")

    print("\nTodos os casos passaram.")
