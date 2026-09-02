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


def implied_vol_lote(tipos, mkts, spots, strikes, prazos, taxas, iteracoes=60):
    """Versao vetorizada (numpy) de implied_vol(), para calcular IV de muitas
    opcoes de uma vez. A versao escalar (Newton-Raphson + bisseccao por
    chamada) e' rapida o bastante pro screener ao vivo (dezenas de chamadas),
    mas impraticavel em volume - medido: >24ms/chamada quando chamada em loop
    (~13h estimadas para os ~2 milhoes de linhas de um backfill anual do
    COTAHIST). Aqui: Newton-Raphson vetorizado com numero fixo de iteracoes,
    sem bisseccao de fallback - aceita um pouco menos de robustez numerica
    caso a caso em troca de ordens de magnitude de velocidade; adequado como
    insumo de backtest estatistico em volume, nao como precificacao
    individual de precisao (para isso, usar implied_vol())."""
    tipos = np.asarray(tipos)
    mkts = np.asarray(mkts, dtype=float)
    spots = np.asarray(spots, dtype=float)
    strikes = np.asarray(strikes, dtype=float)
    prazos = np.maximum(np.asarray(prazos, dtype=float), 1e-6)
    taxas = np.asarray(taxas, dtype=float)

    is_call = tipos == "CALL"
    sigma = np.full(mkts.shape, 0.30, dtype=float)

    for _ in range(iteracoes):
        raiz_t = np.sqrt(prazos)
        d1 = (np.log(spots / strikes) + (taxas + sigma ** 2 / 2) * prazos) / (sigma * raiz_t)
        d2 = d1 - sigma * raiz_t
        preco_call = spots * norm.cdf(d1) - strikes * np.exp(-taxas * prazos) * norm.cdf(d2)
        preco_put = strikes * np.exp(-taxas * prazos) * norm.cdf(-d2) - spots * norm.cdf(-d1)
        preco = np.where(is_call, preco_call, preco_put)
        vega = spots * norm.pdf(d1) * raiz_t
        vega_seguro = np.where(vega > 1e-8, vega, 1e-8)
        sigma = np.clip(sigma - (preco - mkts) / vega_seguro, 1e-4, 5.0)

    return sigma


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


# Limiar da zona neutra, em pontos de volatilidade. ARBITRARIO e declarado como
# tal: calibra-lo exigiria poder preditivo que o backtest mostrou nao existir
# (ver secao 4.4c do ROADMAP_MIH_Opcoes_Handoff.md). Um numero honestamente
# arbitrario e' preferivel a um numero com aparencia de otimizado.
LIMIAR_SINAL_PP = 3.0


def classificar_sinal(diff_pp: float, skew_pp: float, score: float,
                       limiar: float = LIMIAR_SINAL_PP) -> str:
    """Tres estados, com zona neutra explicita. Sem ela, o corte em zero
    rotulava TODA linha da cadeia como compra ou venda, inclusive desvios
    irrelevantes. Basta um dos eixos passar do limiar pra virar sinal."""
    if max(abs(diff_pp), abs(skew_pp)) < limiar:
        return "NEUTRO"
    return "COMPRAR_VOL" if score > 0 else "VENDER_VOL"


def calcular_score(diff_pp: float, skew_pp: float,
                    peso_diff: float = 0.6, peso_skew: float = 0.6) -> float:
    """Score do screener - positivo: vol parece barata (comprar); negativo:
    vol parece cara (vender). Dois eixos ortogonais de verdade:
    - diff_pp: gap entre IV e HV (vol atual vs. vol realizada)
    - skew_pp: gap entre a IV desta opcao e a IV que o sorriso do dia (outros
      strikes do mesmo vencimento) preveria pro seu strike

    NAO usa liquidez (removido em 2026-09-02): liquidez e' qualidade de
    execucao, nao evidencia direcional - o termo log1p(liq)*0,05 empurrava o
    Score pra cima so' por a opcao ser negociada (com liq=10000, ~+0,46), o
    bastante pra inverter sinais. Alem disso, o backtest sempre mediu a formula
    SEM liquidez (chamava com liq=0 e peso_liq=0,0), entao producao e backtest
    so' passaram a ser a mesma coisa agora.

    Deliberadamente NAO usa "desconto" (preco-espaco): e' uma reexpressao
    nao-linear do mesmo gap que diff_pp ja mede - Black-Scholes e' monotonico
    em volatilidade, entao desconto e diff sao colineares por construcao, nao
    duas evidencias independentes. Achado real ao calibrar o backtest (o sweep
    de peso nunca mudava o sinal de nenhuma linha). Ver
    docs/superpowers/specs/2026-08-30-score-opcoes-sem-desconto-design.md."""
    return -diff_pp * peso_diff - skew_pp * peso_skew


def analisar(underlying: dict, series: list[dict], selic: float,
             peso_diff: float = 0.6, peso_skew: float = 0.6,
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
    pontos_por_chave: dict[tuple[str, str], list[tuple[float, float]]] = {}
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

        chave_sorriso = (tipo, s["Data_Vencimento"][:10])
        calculados.append((s, mkt, tipo, dias_corridos, T, iv, liq, chave_sorriso))
        pontos_por_chave.setdefault(chave_sorriso, []).append((s["Strike"], iv))

    # Sorriso por (Tipo, Vencimento), NAO so' por Tipo: a superficie de vol tem
    # estrutura a termo, entao juntar prazos diferentes na mesma parabola faz o
    # Skew_pp medir diferenca de PRAZO em vez de desvio de STRIKE. Verificado
    # com dado sintetico (Caso 20): com a chave errada, uma serie curta com IV
    # 20pp acima da longa aparecia com Skew de 10pp que era puro prazo.
    sorrisos = {chave: ajustar_sorriso(pontos)
                for chave, pontos in pontos_por_chave.items()}

    out: list[LinhaRanking] = []
    for s, mkt, tipo, dias_corridos, T, iv, liq, chave_sorriso in calculados:
        justo, delta = bs_price_delta(tipo, S, s["Strike"], T, r, HV)
        desconto = (justo - mkt) / justo if justo > 0 else 0.0
        diff = (iv - HV) * 100

        sorriso = sorrisos.get(chave_sorriso)
        iv_esperada = sorriso(s["Strike"]) if sorriso else None
        skew = (iv - iv_esperada) * 100 if iv_esperada is not None else 0.0

        score = calcular_score(diff, skew, peso_diff, peso_skew)
        sinal = classificar_sinal(diff, skew, score)

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
def _texto_oportunidade(linha: dict, sinal: str) -> dict:
    """Descreve o DESVIO OBSERVADO, nao uma previsao.

    O vocabulario antigo ("sinal de COMPRA de volatilidade") era duplamente
    impreciso: sugeria poder preditivo que o backtest mostrou nao existir (ver
    secao 4.4c do ROADMAP_MIH_Opcoes_Handoff.md), e a operacao implicada - uma
    call solta - carrega delta, ou seja, nao e' exposicao a volatilidade."""
    posicao = "acima" if sinal == "VENDER_VOL" else "abaixo"
    texto = (
        f"{linha['Codigo_Opcao']} ({linha['Tipo']}, strike R$ {linha['Strike']:.2f}, "
        f"vence em {linha['Dias']} dias) — IV {posicao} da referência: "
        f"{linha['Diff_pp']:+.1f}pp vs. HV, {linha['Skew_pp']:+.1f}pp vs. o sorriso "
        f"do dia. Liquidez {linha['Liquidez']}. Desvio de preço observado — "
        f"não é previsão de retorno."
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
    assert dest["venda"]["codigo_opcao"] == "PETRP280"  # menor Score entre VENDER_VOL (-12.0 < -3.0)
    # O texto descreve o lado do desvio, nao prescreve operacao (ver Caso 19):
    # "COMPRA"/"VENDA" saiu do vocabulario junto com a promessa de previsao.
    assert "abaixo" in dest["compra"]["texto"].lower()
    assert "acima" in dest["venda"]["texto"].lower()
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
    # O texto novo nao fala de desconto (preco-espaco) nenhum - descreve o
    # desvio em pontos de volatilidade. Entao o percentual absurdo que o
    # desconto produzia quando o justo fica perto de zero nao tem por onde
    # vazar. Asserido aqui pra travar isso contra regressao.
    assert "-9100" not in dest4["venda"]["texto"]
    assert "%" not in dest4["venda"]["texto"]
    assert "19.6pp" in dest4["venda"]["texto"] or "+19.6pp" in dest4["venda"]["texto"]
    print("[OK] Caso 9: justo perto de zero nao produz percentual absurdo no texto.")

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

    # Caso 12: calcular_score combina diff e skew no mesmo sentido.
    # A versao anterior deste caso afirmava que "liquidez desempata pra cima" -
    # comportamento removido de proposito em 2026-09-02 (ver Caso 17): liquidez
    # e' qualidade de execucao, nao evidencia de que a vol esta' barata.
    s1 = calcular_score(diff_pp=-10.0, skew_pp=-5.0, peso_diff=0.6, peso_skew=0.6)
    assert s1 > 0  # os dois sinais dizem "vol barata" -> comprar
    s2 = calcular_score(diff_pp=10.0, skew_pp=5.0, peso_diff=0.6, peso_skew=0.6)
    assert s2 < 0  # os dois dizem "vol cara" -> vender
    assert s1 == -s2  # simetrico: mesma magnitude de desvio, sinais opostos
    print("[OK] Caso 12: calcular_score combina diff e skew no mesmo sentido.")

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

    # Caso 15: implied_vol_lote (vetorizada) concorda com implied_vol (escalar)
    # dentro de uma tolerancia pequena, para o mesmo conjunto de opcoes
    tipos_lote = ["CALL", "PUT", "CALL", "PUT"]
    mkts_lote = [2.23, 3.10, 0.85, 1.40]
    spots_lote = [35.50, 35.50, 40.00, 40.00]
    strikes_lote = [33.00, 38.00, 42.00, 39.00]
    prazos_lote = [0.10, 0.25, 0.05, 0.40]
    taxas_lote = [0.14, 0.14, 0.10, 0.10]
    ivs_lote = implied_vol_lote(tipos_lote, mkts_lote, spots_lote, strikes_lote, prazos_lote, taxas_lote)
    for i in range(len(tipos_lote)):
        iv_escalar = implied_vol(tipos_lote[i], mkts_lote[i], spots_lote[i], strikes_lote[i], prazos_lote[i], taxas_lote[i])
        assert abs(ivs_lote[i] - iv_escalar) < 0.01, f"item {i}: lote={ivs_lote[i]:.4f} escalar={iv_escalar:.4f}"
    print("[OK] Caso 15: implied_vol_lote concorda com implied_vol escalar (tolerancia 0.01).")

    # Caso 16: implied_vol_lote roda rapido em volume (a motivacao de existir)
    import time
    n_grande = 200_000
    t0 = time.time()
    implied_vol_lote(
        ["CALL"] * n_grande, [2.0] * n_grande, [35.0] * n_grande,
        [33.0] * n_grande, [0.2] * n_grande, [0.14] * n_grande,
    )
    dt = time.time() - t0
    assert dt < 30.0, f"implied_vol_lote levou {dt:.1f}s para {n_grande} linhas - esperado < 30s"
    print(f"[OK] Caso 16: implied_vol_lote calculou {n_grande} IVs em {dt:.2f}s (< 30s).")

    # Caso 17: Score nao usa mais liquidez. O termo de liquidez empurrava o
    # Score pra cima so' por a opcao ser negociada (log1p(10000)*0,05 ~ +0,46),
    # o bastante pra inverter o sinal de venda pra compra - liquidez e'
    # qualidade de execucao, nao evidencia de que a vol esta' barata.
    # Alem disso, o backtest sempre mediu a formula SEM liquidez (chamava com
    # liq=0 e peso_liq=0,0): so' agora producao e backtest sao a mesma coisa.
    assert calcular_score(10.0, 0.0) == -6.0            # -10 * 0,6
    assert calcular_score(0.0, 10.0) == -6.0            # -10 * 0,6
    assert calcular_score(-10.0, -10.0) == 12.0         # vol barata nos dois eixos
    print("[OK] Caso 17: Score usa so' Diff e Skew - liquidez saiu da formula.")

    # Caso 18: zona neutra - desvio pequeno nao vira sinal
    assert classificar_sinal(1.0, 0.5, calcular_score(1.0, 0.5)) == "NEUTRO"
    assert classificar_sinal(10.0, 0.0, calcular_score(10.0, 0.0)) == "VENDER_VOL"
    assert classificar_sinal(-10.0, 0.0, calcular_score(-10.0, 0.0)) == "COMPRAR_VOL"
    # basta UM dos eixos passar do limiar
    assert classificar_sinal(0.0, 10.0, calcular_score(0.0, 10.0)) == "VENDER_VOL"
    print("[OK] Caso 18: zona neutra evita rotular desvio irrelevante.")

    # Caso 19: o texto de saida descreve DESVIO OBSERVADO, nunca previsao nem
    # "sinal de compra". O backtest mostrou que o Score nao preve retorno;
    # manter o vocabulario de recomendacao seria prometer o que nao se sustenta.
    linha_texto = {
        "Codigo_Opcao": "PETRA300", "Tipo": "CALL", "Strike": 30.0, "Dias": 25,
        "Preco_Mercado": 1.80, "Justo_BS": 1.50, "Desconto": -0.20,
        "Diff_pp": 9.0, "Skew_pp": 4.0, "Liquidez": 1200,
    }
    saida = _texto_oportunidade(linha_texto, "VENDER_VOL")
    texto_gerado = saida["texto"]
    assert "sinal de" not in texto_gerado.lower()
    assert "recomend" not in texto_gerado.lower()
    assert "acima" in texto_gerado.lower() or "abaixo" in texto_gerado.lower()
    assert "PETRA300" in texto_gerado
    print("[OK] Caso 19: texto descreve desvio observado, sem vocabulario de previsao.")

    # Caso 20: o sorriso e' ajustado por (Tipo, Vencimento), nao so' por Tipo.
    # A superficie de vol tem estrutura a termo: uma serie de 7 dias e outra de
    # 90 tem niveis de IV sistematicamente diferentes. Juntando as duas na mesma
    # parabola, parte do Skew_pp passa a medir diferenca de PRAZO em vez de
    # desvio de STRIKE - que e' o que ele deveria medir.
    hoje_teste = date(2026, 1, 5)
    underlying_prazo = {"Spot": 30.0, "HV_60d": 0.30}
    series_prazo = []
    for strike, iv in ((28.0, 0.50), (30.0, 0.48), (32.0, 0.49), (34.0, 0.52)):
        series_prazo.append({"Codigo_Opcao": f"CURTA{strike:.0f}", "Tipo": "CALL",
                             "Strike": strike, "Data_Vencimento": "2026-01-16",
                             "Ultimo": 1.20, "IV_Fonte": iv, "Volume": 100})
    for strike, iv in ((28.0, 0.30), (30.0, 0.28), (32.0, 0.29), (34.0, 0.32)):
        series_prazo.append({"Codigo_Opcao": f"LONGA{strike:.0f}", "Tipo": "CALL",
                             "Strike": strike, "Data_Vencimento": "2026-04-17",
                             "Ultimo": 2.50, "IV_Fonte": iv, "Volume": 100})

    ranking_prazo = analisar(underlying_prazo, series_prazo, selic=0.12, hoje=hoje_teste)
    # Cada serie e' comparada ao sorriso do SEU vencimento, entao o Skew fica
    # pequeno nos dois grupos. Com a chave errada (so' Tipo), o grupo curto
    # apareceria ~10pp acima e o longo ~10pp abaixo de um sorriso medio.
    for linha in ranking_prazo:
        assert abs(linha["Skew_pp"]) < 5.0, (linha["Codigo_Opcao"], linha["Skew_pp"])
    print("[OK] Caso 20: sorriso por (Tipo, Vencimento) - nao mistura prazos.")

    print("\nTodos os casos passaram.")
