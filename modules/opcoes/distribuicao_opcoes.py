"""Distribuicao de probabilidade implicita nos precos das opcoes.

Funcoes puras: nao le banco, nao acessa rede (mesmo padrao de exposicao.py).

ATENCAO CONCEITUAL: a distribuicao extraida aqui e' NEUTRA AO RISCO. Ela embute
premio de risco de variancia, que para acoes infla sistematicamente a cauda de
baixa. O mercado precificar 12% de chance de queda forte NAO significa que ele
atribua 12% de crenca a esse evento - parte disso e' o custo do seguro.

Consequencia obrigatoria pra quem exibe esses numeros: rotular sempre como
"embutido no preco", NUNCA como "o mercado acha". Ver secao 6.2 de
docs/superpowers/specs/2026-09-02-recomendacao-estruturada-opcoes-design.md.
"""
from __future__ import annotations
import os, sys
from dataclasses import dataclass
import math
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from analises_opcoes import ajustar_sorriso, bs_price_delta

MINIMO_STRIKES = 4


@dataclass(frozen=True)
class FaixaProbabilidade:
    limite_inferior: float
    limite_superior: float
    probabilidade: float


def distribuicao_implicita(strikes: list[float], ivs: list[float], spot: float,
                            prazo: float, taxa: float,
                            n_faixas: int = 20) -> list[FaixaProbabilidade] | None:
    """Densidade neutra ao risco por Breeden-Litzenberger: a probabilidade de
    terminar entre dois strikes e' o preco de uma borboleta estreita ali.

    Ou seja, a probabilidade E' um preco observavel, nao uma estimativa do
    modelo - o unico modelo usado e' o sorriso ajustado, pra interpolar precos
    de call em strikes que a cadeia nao lista.

    Devolve None quando nao da' pra extrair distribuicao confiavel:
    - menos de MINIMO_STRIKES strikes distintos (sorriso nao ajustavel)
    - densidade negativa em qualquer faixa (a parabola extrapolada violou
      nao-arbitragem) - nesse caso RECUSA em vez de truncar silenciosamente
    """
    if len({float(k) for k in strikes}) < MINIMO_STRIKES:
        return None
    sorriso = ajustar_sorriso(list(zip(strikes, ivs)))
    if sorriso is None:
        return None

    inferior, superior = min(strikes), max(strikes)
    bordas = np.linspace(inferior, superior, n_faixas + 1)
    passo = float(bordas[1] - bordas[0])

    def preco_call(k: float) -> float:
        vol = max(float(sorriso(k)), 1e-4)
        preco, _delta = bs_price_delta("CALL", spot, k, prazo, taxa, vol)
        return float(preco)

    desconto = math.exp(taxa * prazo)
    faixas: list[FaixaProbabilidade] = []
    for i in range(n_faixas):
        centro = float((bordas[i] + bordas[i + 1]) / 2)
        # segunda diferenca central = preco da borboleta estreita nesse centro
        segunda = preco_call(centro - passo) - 2 * preco_call(centro) + preco_call(centro + passo)
        prob = desconto * segunda / passo
        if prob < -1e-6:
            return None   # densidade negativa: ajuste violou nao-arbitragem
        faixas.append(FaixaProbabilidade(
            limite_inferior=float(bordas[i]),
            limite_superior=float(bordas[i + 1]),
            probabilidade=max(prob, 0.0),
        ))
    return faixas


if __name__ == "__main__":
    import math
    from scipy.stats import norm

    # Caso 1: TESTE ANALITICO EXATO. Com IV constante, a distribuicao neutra ao
    # risco E' lognormal, com parametros em forma fechada. Entao da' pra afirmar
    # que a extracao numerica bate com a formula - isso trava o metodo contra a
    # matematica, nao contra um valor que a propria implementacao produziu.
    spot_teste, iv_teste, prazo_teste, taxa_teste = 30.0, 0.30, 0.25, 0.12
    strikes_teste = [float(k) for k in range(20, 43, 2)]
    ivs_teste = [iv_teste] * len(strikes_teste)

    faixas = distribuicao_implicita(strikes_teste, ivs_teste, spot_teste,
                                     prazo_teste, taxa_teste, n_faixas=12)
    assert faixas is not None

    def prob_lognormal(a, b):
        """P(a < S_T < b) sob a medida neutra ao risco."""
        def d(x):
            return ((math.log(x / spot_teste)
                     - (taxa_teste - iv_teste ** 2 / 2) * prazo_teste)
                    / (iv_teste * math.sqrt(prazo_teste)))
        return float(norm.cdf(d(b)) - norm.cdf(d(a)))

    for faixa in faixas:
        esperado = prob_lognormal(faixa.limite_inferior, faixa.limite_superior)
        assert abs(faixa.probabilidade - esperado) < 0.02, (faixa, esperado)
    print("[OK] Caso 1: distribuicao extraida bate com a lognormal analitica.")

    # Caso 2: as probabilidades somam ~1 (o intervalo coberto e' quase toda a massa)
    total = sum(f.probabilidade for f in faixas)
    assert 0.90 < total < 1.02, total
    print("[OK] Caso 2: probabilidades somam aproximadamente 1.")

    # Caso 3: poucos strikes -> recusa, nao inventa distribuicao
    assert distribuicao_implicita([30.0, 32.0], [0.3, 0.3], 30.0, 0.25, 0.12) is None
    print("[OK] Caso 3: menos de 4 strikes distintos -> recusa a distribuicao.")

    print("\nTodos os casos passaram.")
