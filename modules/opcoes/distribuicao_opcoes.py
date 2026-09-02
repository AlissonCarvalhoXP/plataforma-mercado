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


def probabilidade_cenario(cenarios: list[dict], limite_inferior: float,
                           limite_superior: float) -> float:
    """Massa de probabilidade que os cenarios declarados poem nessa faixa.

    Cada cenario e' um ponto (preco-alvo) com massa concentrada - o usuario
    declara tres pontos, nao uma curva. Faixa fechada embaixo, aberta em cima,
    pra nao contar o mesmo alvo duas vezes em faixas adjacentes."""
    total = 0.0
    for cenario in cenarios:
        alvo = float(cenario["Preco_Alvo"])
        if limite_inferior <= alvo < limite_superior:
            total += float(cenario["Probabilidade"])
    return total


def comparar_distribuicoes(faixas: list[FaixaProbabilidade],
                            cenarios: list[dict]) -> list[dict]:
    """Divergencia faixa a faixa entre o que esta' embutido no preco e o que o
    usuario declarou.

    LEMBRETE OBRIGATORIO pra quem exibe: parte da diferenca e' premio de risco
    de variancia, nao discordancia de opiniao - a distribuicao implicita e'
    neutra ao risco (ver docstring do modulo)."""
    saida = []
    for faixa in faixas:
        prob_cenario = probabilidade_cenario(
            cenarios, faixa.limite_inferior, faixa.limite_superior)
        saida.append({
            "limite_inferior": faixa.limite_inferior,
            "limite_superior": faixa.limite_superior,
            "implicita": faixa.probabilidade,
            "cenario": prob_cenario,
            "divergencia": prob_cenario - faixa.probabilidade,
        })
    return saida


def valor_esperado(pernas, distribuicao) -> float:
    """Valor esperado do payoff no vencimento sob a distribuicao dada.

    `distribuicao` aceita as duas formas: lista de FaixaProbabilidade (a
    implicita, avaliada no centro de cada faixa) ou lista de cenarios
    declarados (avaliada no preco-alvo de cada um).

    Exibir os DOIS lado a lado e' o desenho: a ferramenta nao elege estrutura
    vencedora - ela mostra a consequencia de cada uma sob as duas visoes e
    deixa a comparacao com o usuario."""
    import estruturas_opcoes as est
    total = 0.0
    for item in distribuicao:
        if isinstance(item, FaixaProbabilidade):
            preco = (item.limite_inferior + item.limite_superior) / 2
            peso = item.probabilidade
        else:
            preco = float(item["Preco_Alvo"])
            peso = float(item["Probabilidade"])
        total += peso * est.payoff_estrutura(pernas, preco)
    return total


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

    # Caso 4: probabilidade do cenario numa faixa - cada cenario e' um ponto
    # (preco-alvo) com massa; a faixa recebe a massa dos alvos que caem nela
    cenarios_teste = [
        {"Cenario": "alta", "Preco_Alvo": 42.0, "Probabilidade": 0.25},
        {"Cenario": "base", "Preco_Alvo": 35.0, "Probabilidade": 0.55},
        {"Cenario": "baixa", "Preco_Alvo": 28.0, "Probabilidade": 0.20},
    ]
    assert probabilidade_cenario(cenarios_teste, 40.0, 45.0) == 0.25
    assert probabilidade_cenario(cenarios_teste, 33.0, 37.0) == 0.55
    assert probabilidade_cenario(cenarios_teste, 50.0, 60.0) == 0.0
    print("[OK] Caso 4: probabilidade do cenario por faixa de preco.")

    # Caso 5: comparacao expoe a divergencia faixa a faixa
    faixas_simples = [
        FaixaProbabilidade(26.0, 32.0, 0.50),
        FaixaProbabilidade(32.0, 38.0, 0.35),
        FaixaProbabilidade(38.0, 44.0, 0.15),
    ]
    comparacao = comparar_distribuicoes(faixas_simples, cenarios_teste)
    assert len(comparacao) == 3
    faixa_alta = comparacao[2]
    assert abs(faixa_alta["implicita"] - 0.15) < 1e-9
    assert abs(faixa_alta["cenario"] - 0.25) < 1e-9
    assert abs(faixa_alta["divergencia"] - 0.10) < 1e-9
    print("[OK] Caso 5: comparacao mostra divergencia entre cenario e preco.")

    # Caso 6: valor esperado da mesma estrutura sob as duas distribuicoes
    import estruturas_opcoes as est
    trava_ve = [
        est.Perna(lado="comprar", tipo="CALL", strike=30.0, premio=2.00),
        est.Perna(lado="vender", tipo="CALL", strike=35.0, premio=0.50),
    ]
    ve_implicito = valor_esperado(trava_ve, faixas_simples)
    ve_cenario = valor_esperado(trava_ve, cenarios_teste)
    # sob o cenario, que poe 25% acima de 40, a trava vale mais que sob o preco
    assert ve_cenario > ve_implicito
    print("[OK] Caso 6: valor esperado calculado sob as duas distribuicoes.")

    print("\nTodos os casos passaram.")
