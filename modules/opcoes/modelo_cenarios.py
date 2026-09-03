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

    print("\nTodos os casos passaram.")
