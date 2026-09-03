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

    print("\nTodos os casos passaram.")
