"""Motor de payoff e catalogo de estruturas de opcoes.

Funcoes puras: nao le banco, nao acessa rede, nao tem efeito colateral - quem
chama monta os dados (mesmo padrao de exposicao.py e analises.py).

O payoff aqui e' sempre NO VENCIMENTO. Series de estilo americano podem ser
exercidas antes, e dividendos alteram esse incentivo em calls; este modulo nao
afirma qual e' a convencao vigente de cada serie na B3. Risco antes do
vencimento tambem difere: perda maxima no vencimento nao protege de marcacao a
mercado adversa nem de chamada de margem no meio do caminho.

Ver docs/superpowers/specs/2026-09-02-recomendacao-estruturada-opcoes-design.md
"""
from __future__ import annotations
from dataclasses import dataclass

LOTE_PADRAO_B3 = 100


@dataclass(frozen=True)
class Perna:
    """Uma perna de uma estrutura. `quantidade` permite ratio spreads sem
    tratamento especial. `premio` e' o preco observado da opcao, por acao."""
    lado: str          # "comprar" | "vender"
    tipo: str          # "CALL" | "PUT"
    strike: float
    premio: float
    quantidade: int = 1
    vencimento: str = ""


def payoff_perna(perna: Perna, preco: float) -> float:
    """Payoff da perna no vencimento, POR ACAO, ao preco `preco` do ativo."""
    if perna.tipo == "CALL":
        intrinseco = max(preco - perna.strike, 0.0)
    else:
        intrinseco = max(perna.strike - preco, 0.0)
    if perna.lado == "comprar":
        return (intrinseco - perna.premio) * perna.quantidade
    return (perna.premio - intrinseco) * perna.quantidade


def payoff_estrutura(pernas: list[Perna], preco: float,
                     lote: int = LOTE_PADRAO_B3) -> float:
    """Payoff total da estrutura no vencimento, em reais (ja multiplicado
    pelo lote)."""
    return sum(payoff_perna(p, preco) for p in pernas) * lote


if __name__ == "__main__":
    # Trava de alta: compra CALL 30 por R$2,00, vende CALL 35 por R$0,50.
    # Debito liquido de R$1,50 por acao.
    trava = [
        Perna(lado="comprar", tipo="CALL", strike=30.0, premio=2.00),
        Perna(lado="vender", tipo="CALL", strike=35.0, premio=0.50),
    ]

    # Abaixo de 30: as duas viram po, perde o debito inteiro.
    assert payoff_estrutura(trava, 25.0) == -150.0
    # Acima de 35: ganho travado = (35-30-1,50) * 100
    assert payoff_estrutura(trava, 40.0) == 350.0
    # No breakeven: 30 + 1,50
    assert abs(payoff_estrutura(trava, 31.50)) < 1e-9
    print("[OK] Caso 1: payoff da trava de alta bate com os valores de livro-texto.")

    # Perna isolada, por acao (sem lote)
    compra_call = Perna(lado="comprar", tipo="CALL", strike=30.0, premio=2.00)
    assert payoff_perna(compra_call, 33.0) == 1.0     # 3 de intrinseco - 2 de premio
    assert payoff_perna(compra_call, 28.0) == -2.0    # vira po, perde o premio
    venda_put = Perna(lado="vender", tipo="PUT", strike=30.0, premio=1.00)
    assert payoff_perna(venda_put, 32.0) == 1.00      # expira po, embolsa o premio
    assert payoff_perna(venda_put, 27.0) == -2.00     # 3 de intrinseco contra, +1 de premio
    print("[OK] Caso 2: payoff por perna respeita lado e tipo.")

    print("\nTodos os casos passaram.")
