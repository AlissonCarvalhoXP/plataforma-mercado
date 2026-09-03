"""Modelo de cenarios automaticos por Filtered Historical Simulation (FHS).

Funcoes puras: nao le banco, nao acessa rede (mesmo padrao de exposicao.py).

O QUE ESTE MODELO FAZ E O QUE NAO FAZ: ele preve a LARGURA e a FORMA da
distribuicao do ativo no horizonte, nunca o CENTRO. Volatilidade e' previsivel
(clustering e' um dos fatos empiricos mais robustos em financas); direcao nao
e'. Por isso os retornos sao de-mediados antes de virar residuos, e a
distribuicao simulada e' recentrada no preco a termo - que e' nao-arbitragem,
nao opiniao. Ver secao 3.3 de
docs/superpowers/specs/2026-09-02-cenarios-automaticos-fhs-design.md.

A distribuicao produzida aqui e' a medida REAL-WORLD (P). A extraida das opcoes
(distribuicao_opcoes.py) e' a NEUTRA AO RISCO (Q). A diferenca entre as duas e'
PREMIO DE RISCO - documentado e ja precificado - nao oportunidade.
"""
from __future__ import annotations
import math
import numpy as np

LAMBDA_EWMA = 0.94      # RiskMetrics, para dados diarios
DIAS_UTEIS_ANO = 252
MINIMO_PREGOES = 250
SALTO_MAXIMO = 0.35     # variacao em um pregao acima disso = provavel evento societario


def volatilidade_ewma(retornos, lam: float = LAMBDA_EWMA) -> np.ndarray:
    """Serie de volatilidade condicional (desvio-padrao) por EWMA:

        var_t = lam * var_{t-1} + (1 - lam) * r_{t-1}^2

    A posicao i do resultado e' a volatilidade prevista PARA o periodo i,
    usando somente retornos ate' i-1. Essa construcao sem olhar o futuro e' o
    que torna o walk-forward da avaliacao honesto.

    EWMA e nao GARCH por escopo: com ~500 observacoes, GARCH(1,1) da parametros
    instaveis; EWMA tem parametro fixo e conhecido, nao precisa de otimizacao, e
    captura o efeito que importa (clustering)."""
    r = np.asarray(retornos, dtype=float)
    if len(r) == 0:
        return np.array([])
    var = np.empty(len(r))
    var[0] = float(r[0] ** 2)
    for i in range(1, len(r)):
        var[i] = lam * var[i - 1] + (1 - lam) * r[i - 1] ** 2
    return np.sqrt(var)


def residuos_padronizados(retornos, lam: float = LAMBDA_EWMA):
    """Retornos DE-MEDIADOS divididos pela volatilidade condicional.

    De-mediar e' critico e nao e' detalhe: sem isso, os residuos carregam o
    drift do periodo amostral, a simulacao o herda, e o modelo passa a prever
    direcao a partir de retorno passado. Retorno esperado e' notoriamente
    dificil de estimar - drift de 2 anos e' ruido.

    Devolve (residuos, serie_de_vol)."""
    r = np.asarray(retornos, dtype=float)
    r = r - r.mean()
    vol = volatilidade_ewma(r, lam)
    return r / np.maximum(vol, 1e-12), vol


def simular_fhs(retornos, spot: float, horizonte: int, taxa: float,
                 n_simulacoes: int = 10000, lam: float = LAMBDA_EWMA,
                 semente: int | None = None) -> np.ndarray:
    """Filtered Historical Simulation: devolve os precos terminais simulados.

    Procedimento: filtra os retornos pelo EWMA, extrai os residuos
    padronizados (que carregam cauda gorda e assimetria REAIS do ativo, sem
    assumir distribuicao), sorteia esses residuos com reposicao ao longo do
    horizonte reescalando pela volatilidade prevista, e recentra o resultado
    no preco a termo.

    A recentragem no termo (spot * exp(taxa * horizonte/252)) e' o que impede
    o drift historico de virar previsao de direcao - ver residuos_padronizados
    e a secao 3.3 da spec."""
    rng = np.random.default_rng(semente)
    z, vol = residuos_padronizados(retornos, lam)
    r_demediado = np.asarray(retornos, dtype=float)
    r_demediado = r_demediado - r_demediado.mean()
    # Um passo extra da recursao: vol[-1] por construcao NAO incorpora
    # retornos[-1] (ver volatilidade_ewma). Sem este passo, a simulacao
    # arrancaria ignorando o dado mais recente - justo o oposto do que o
    # clustering do EWMA promete.
    var_inicial = float(lam * vol[-1] ** 2 + (1 - lam) * r_demediado[-1] ** 2)

    # Vetorizado ao longo das simulacoes: o laco corre o horizonte (dezenas de
    # passos), nao as simulacoes (milhares). A recursao de vol e' dependente do
    # caminho, entao precisa ser iterada - mas todas as trajetorias avancam
    # juntas.
    var = np.full(n_simulacoes, var_inicial, dtype=float)
    soma_retornos = np.zeros(n_simulacoes, dtype=float)
    for _ in range(horizonte):
        choques = z[rng.integers(0, len(z), n_simulacoes)]
        retorno_passo = np.sqrt(var) * choques
        soma_retornos += retorno_passo
        var = lam * var + (1 - lam) * retorno_passo ** 2

    precos = spot * np.exp(soma_retornos)

    # Recentra a MEDIA no preco a termo (condicao de martingale sob a medida a
    # termo). O modelo entrega largura e forma; o centro vem de nao-arbitragem.
    termo = spot * math.exp(taxa * horizonte / DIAS_UTEIS_ANO)
    return precos * (termo / precos.mean())


def resumir_em_cenarios(precos_simulados) -> list[dict]:
    """Resume a distribuicao simulada em tres cenarios, no mesmo formato que a
    UI e distribuicao_opcoes.py ja consomem.

    O preco de cada cenario e' a MEDIA CONDICIONAL da sua regiao, nao o quantil
    de corte. Isso torna o resumo coerente: a media ponderada dos tres pontos
    recupera a media da distribuicao completa. Exibir o quantil 10% como "preco
    do cenario de baixa" e ao mesmo tempo atribuir a ele a massa abaixo do
    quantil 25% seria incoerente - o ponto nao representaria a regiao.

    O resumo e' para EXIBICAO. O valor esperado das estruturas continua sendo
    calculado sobre a distribuicao completa (ver secao 3.4 da spec)."""
    p = np.asarray(precos_simulados, dtype=float)
    q25, q75 = np.quantile(p, [0.25, 0.75])
    regioes = (
        ("baixa", p[p <= q25]),
        ("base", p[(p > q25) & (p <= q75)]),
        ("alta", p[p > q75]),
    )
    return [
        {"Cenario": nome,
         "Preco_Alvo": float(valores.mean()),
         "Probabilidade": float(len(valores) / len(p))}
        for nome, valores in regioes
    ]


def retornos_log(precos) -> np.ndarray:
    """Retornos logaritmicos diarios a partir da serie de precos."""
    p = np.asarray(precos, dtype=float)
    return np.diff(np.log(p))


def validar_serie(precos) -> str | None:
    """Devolve o motivo da recusa, ou None se a serie serve para o modelo.

    Recusa em vez de produzir estimativa ruim silenciosamente - mesmo principio
    das recusas de distribuicao_opcoes.py."""
    p = np.asarray(precos, dtype=float)
    if len(p) < MINIMO_PREGOES:
        return (f"serie curta demais: {len(p)} pregoes, minimo {MINIMO_PREGOES} "
                f"para estimar volatilidade e extrair residuos")
    if np.any(p <= 0):
        return "serie contem preco zero ou negativo"

    variacoes = np.abs(np.diff(p) / p[:-1])
    if np.any(variacoes > SALTO_MAXIMO):
        indice = int(np.argmax(variacoes))
        return (f"salto de {variacoes[indice]:.0%} em um pregao (de {p[indice]:.2f} "
                f"para {p[indice + 1]:.2f}) - provavel evento societario nao "
                f"ajustado; o COTAHIST traz preco bruto")
    return None


if __name__ == "__main__":
    import numpy as np

    # Caso 1: com volatilidade constante, o EWMA converge para ela
    rng = np.random.default_rng(42)
    vol_verdadeira = 0.02
    retornos_const = rng.normal(0.0, vol_verdadeira, 2000)
    vol = volatilidade_ewma(retornos_const)
    assert len(vol) == len(retornos_const)
    # EWMA e' ruidoso (janela efetiva ~1/(1-0.94) ~ 17 dias), entao a media da
    # serie e' o que converge, nao cada ponto
    assert abs(vol[100:].mean() - vol_verdadeira) < 0.15 * vol_verdadeira
    print("[OK] Caso 1: EWMA converge para a volatilidade verdadeira.")

    # Caso 2: NAO olha o futuro. vol[i] e' calculada com retornos ate' i-1,
    # entao mexer no ULTIMO retorno nao pode alterar nenhum valor da serie.
    # Sem essa propriedade, o walk-forward da Task 6 estaria contaminado.
    retornos_alterado = retornos_const.copy()
    retornos_alterado[-1] = 99.0
    vol_alterado = volatilidade_ewma(retornos_alterado)
    assert np.allclose(vol, vol_alterado)
    print("[OK] Caso 2: EWMA nao olha o futuro (ultimo retorno nao afeta a serie).")

    # Caso 3: ESTE E' O TESTE MAIS IMPORTANTE DO MODULO.
    # Com retornos de drift forte, a distribuicao simulada tem que ficar
    # centrada no PRECO A TERMO, nao no preco extrapolado pelo drift. Sem
    # de-mediar os retornos, a simulacao herdaria o drift amostral e estaria
    # prevendo DIRECAO a partir de retorno passado - exatamente a armadilha
    # que este design existe para evitar (secao 3.3 da spec).
    drift_diario = 0.005
    retornos_drift = drift_diario + rng.normal(0.0, 0.01, 500)
    spot_teste, horizonte_teste, taxa_teste = 100.0, 45, 0.0
    precos = simular_fhs(retornos_drift, spot_teste, horizonte_teste,
                          taxa_teste, n_simulacoes=5000, semente=7)
    termo = spot_teste * math.exp(taxa_teste * horizonte_teste / DIAS_UTEIS_ANO)
    assert abs(precos.mean() - termo) < 0.01 * termo
    # extrapolar o drift daria ~100*exp(0.005*45) = 125; tem que estar longe disso
    preco_se_extrapolasse_drift = spot_teste * math.exp(drift_diario * horizonte_teste)
    assert precos.mean() < 0.9 * preco_se_extrapolasse_drift
    print("[OK] Caso 3: distribuicao recentrada no termo - drift historico nao vaza.")

    # Caso 4: a taxa entra pelo termo (juro maior desloca o centro pra cima)
    precos_juro = simular_fhs(retornos_drift, spot_teste, horizonte_teste,
                               taxa=0.12, n_simulacoes=5000, semente=7)
    termo_juro = spot_teste * math.exp(0.12 * horizonte_teste / DIAS_UTEIS_ANO)
    assert abs(precos_juro.mean() - termo_juro) < 0.01 * termo_juro
    assert precos_juro.mean() > precos.mean()
    print("[OK] Caso 4: o centro da distribuicao e' o preco a termo, com juro.")

    # Caso 5: FHS preserva a assimetria dos residuos (nao assume normal).
    # Horizonte 1 preserva mais - agregar horizonte encolhe assimetria (TCL).
    # A serie e' embaralhada com o rng semeado antes de usar: sem isso, os 900
    # ganhos positivos vem antes das 100 quedas grandes, e o EWMA sobe durante
    # as quedas - dividindo os choques negativos por vol alta e encolhendo a
    # assimetria dos residuos por artefato de ordenacao, nao por defeito do
    # modelo.
    from scipy.stats import skew
    choques_assimetricos = np.concatenate([
        rng.normal(0.005, 0.005, 900),      # muitos ganhos pequenos
        rng.normal(-0.06, 0.02, 100),       # poucas quedas grandes
    ])
    rng.shuffle(choques_assimetricos)
    precos_assim = simular_fhs(choques_assimetricos, 100.0, 1, 0.0,
                                n_simulacoes=20000, semente=11)
    assert skew(np.log(precos_assim / 100.0)) < -0.3
    print("[OK] Caso 5: FHS preserva a assimetria real, nao assume normal.")

    # Caso 6: a semente da simulacao incorpora o retorno MAIS RECENTE.
    # vol[-1] por construcao nao o inclui; sem o passo extra da recursao, uma
    # serie que termina em choque geraria a mesma distribuicao de uma serie
    # calma - e o clustering do EWMA nao estaria sendo usado.
    calma = list(rng.normal(0.0, 0.01, 400))
    com_choque = list(calma[:-1]) + [0.20]
    largura_calma = np.std(simular_fhs(calma, 100.0, 5, 0.0,
                                        n_simulacoes=4000, semente=13))
    largura_choque = np.std(simular_fhs(com_choque, 100.0, 5, 0.0,
                                         n_simulacoes=4000, semente=13))
    assert largura_choque > 1.5 * largura_calma, (largura_calma, largura_choque)
    print("[OK] Caso 6: semente da simulacao incorpora o retorno mais recente.")

    # Caso 7: o resumo em tres cenarios e' COERENTE com a distribuicao.
    # O preco de cada cenario e' a MEDIA CONDICIONAL da sua regiao, nao o
    # quantil de corte - por isso a media ponderada dos tres recupera a media
    # da distribuicao completa. Usar o quantil como preco quebraria isso: o
    # ponto exibido nao representaria a regiao que ele resume.
    amostra = simular_fhs(retornos_drift, 100.0, 45, 0.0,
                           n_simulacoes=20000, semente=3)
    cenarios = resumir_em_cenarios(amostra)
    assert [c["Cenario"] for c in cenarios] == ["baixa", "base", "alta"]
    assert abs(sum(c["Probabilidade"] for c in cenarios) - 1.0) < 1e-9
    media_ponderada = sum(c["Preco_Alvo"] * c["Probabilidade"] for c in cenarios)
    assert abs(media_ponderada - amostra.mean()) < 1e-6 * amostra.mean()
    print("[OK] Caso 7: resumo por media condicional recupera a media da distribuicao.")

    # Caso 8: ordenacao e proporcoes por construcao (cortes em 25% e 75%)
    assert cenarios[0]["Preco_Alvo"] < cenarios[1]["Preco_Alvo"] < cenarios[2]["Preco_Alvo"]
    assert abs(cenarios[0]["Probabilidade"] - 0.25) < 0.01
    assert abs(cenarios[1]["Probabilidade"] - 0.50) < 0.01
    assert abs(cenarios[2]["Probabilidade"] - 0.25) < 0.01
    print("[OK] Caso 8: cortes em 25%/75% dao 25/50/25, com precos ordenados.")

    # Caso 9: serie curta demais e' recusada com motivo, nao produz modelo ruim
    curta = list(np.linspace(30.0, 32.0, 100))
    motivo = validar_serie(curta)
    assert motivo is not None and "pregoes" in motivo.lower()
    print("[OK] Caso 9: serie com menos de 250 pregoes e' recusada com motivo.")

    # Caso 10: salto de evento societario e' detectado. O COTAHIST traz preco
    # BRUTO, sem ajuste - o grupamento do MGLU foi de R$1,32 para R$13,15 num
    # pregao (+896%). Sem esta guarda, o modelo leria isso como volatilidade.
    com_grupamento = [10.0] * 300
    com_grupamento[150] = 100.0   # salto de +900%
    motivo_salto = validar_serie(com_grupamento)
    assert motivo_salto is not None and "salto" in motivo_salto.lower()
    print("[OK] Caso 10: salto de evento societario e' detectado e recusado.")

    # Caso 11: serie boa passa, e os retornos log saem com o tamanho certo
    boa = list(100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.015, 400))))
    assert validar_serie(boa) is None
    assert len(retornos_log(boa)) == len(boa) - 1
    print("[OK] Caso 11: serie valida passa e produz retornos log.")

    print("\nTodos os casos passaram.")
