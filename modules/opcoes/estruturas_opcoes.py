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


@dataclass(frozen=True)
class PerfilRisco:
    """perda_maxima/ganho_maximo em None significam ILIMITADO (nao zero)."""
    perda_maxima: float | None
    ganho_maximo: float | None
    breakevens: list[float]
    premio_liquido: float   # positivo = debito pago; negativo = credito recebido


def _inclinacao_acima_do_maior_strike(pernas: list[Perna]) -> float:
    """Acima do maior strike, toda call esta' no dinheiro e toda put virou po -
    entao a inclinacao do payoff e' so' a quantidade liquida de calls."""
    total = 0.0
    for p in pernas:
        if p.tipo == "CALL":
            total += p.quantidade if p.lado == "comprar" else -p.quantidade
    return total


def premio_liquido(pernas: list[Perna], lote: int = LOTE_PADRAO_B3) -> float:
    """Positivo = debito pago para montar; negativo = credito recebido."""
    total = 0.0
    for p in pernas:
        sinal = 1.0 if p.lado == "comprar" else -1.0
        total += sinal * p.premio * p.quantidade
    return total * lote


def perfil_risco(pernas: list[Perna], lote: int = LOTE_PADRAO_B3) -> PerfilRisco:
    """Extremos e breakevens EXATOS, sem grade aproximada.

    O payoff combinado no vencimento e' linear por partes, com quebras apenas
    nos strikes. Entao avaliar em 0, em cada strike, e num ponto alem do maior
    strike basta: qualquer extremo esta' num desses pontos, e cada breakeven
    esta' num segmento entre dois deles, onde a interpolacao linear e' exata.

    Abaixo do menor strike o ativo e' limitado por preco >= 0, entao esse lado
    e' sempre finito. So' o lado de cima pode ser ilimitado.
    """
    strikes = sorted({p.strike for p in pernas})
    pontos = [0.0] + strikes + [strikes[-1] * 2 + 10.0]
    valores = [payoff_estrutura(pernas, s, lote) for s in pontos]

    inclinacao = _inclinacao_acima_do_maior_strike(pernas)
    ganho_maximo = None if inclinacao > 0 else max(valores)
    perda_maxima = None if inclinacao < 0 else min(valores)

    breakevens: list[float] = []
    for i in range(len(pontos) - 1):
        v1, v2 = valores[i], valores[i + 1]
        if abs(v1) < 1e-9:
            breakevens.append(round(pontos[i], 4))
        elif v1 * v2 < 0:
            # segmento e' linear, entao o cruzamento do zero e' exato
            x = pontos[i] + (pontos[i + 1] - pontos[i]) * (-v1) / (v2 - v1)
            breakevens.append(round(x, 4))
    if abs(valores[-1]) < 1e-9:
        breakevens.append(round(pontos[-1], 4))

    return PerfilRisco(
        perda_maxima=perda_maxima, ganho_maximo=ganho_maximo,
        breakevens=sorted(set(breakevens)),
        premio_liquido=premio_liquido(pernas, lote),
    )


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

    # Caso 3: trava de alta tem os quatro numeros exatos e nada ilimitado
    perfil = perfil_risco(trava)
    assert perfil.perda_maxima == -150.0
    assert perfil.ganho_maximo == 350.0
    assert perfil.breakevens == [31.5]
    assert perfil.premio_liquido == 150.0   # debito de R$1,50/acao * 100
    print("[OK] Caso 3: perfil de risco da trava de alta, com breakeven exato.")

    # Caso 4: venda descoberta de CALL tem perda ILIMITADA, ganho travado no premio
    venda_seca = [Perna(lado="vender", tipo="CALL", strike=35.0, premio=1.20)]
    p_seca = perfil_risco(venda_seca)
    assert p_seca.perda_maxima is None          # ilimitada
    assert p_seca.ganho_maximo == 120.0         # o premio recebido
    assert p_seca.breakevens == [36.2]          # 35 + 1,20
    assert p_seca.premio_liquido == -120.0      # credito
    print("[OK] Caso 4: venda descoberta e' marcada como perda ilimitada.")

    # Caso 5: straddle comprado - dois breakevens, perda maxima no strike
    straddle = [
        Perna(lado="comprar", tipo="CALL", strike=30.0, premio=1.50),
        Perna(lado="comprar", tipo="PUT", strike=30.0, premio=1.00),
    ]
    p_str = perfil_risco(straddle)
    assert p_str.perda_maxima == -250.0         # os dois premios, exatamente no strike
    assert p_str.ganho_maximo is None           # ilimitado pra cima
    assert p_str.breakevens == [27.5, 32.5]     # 30 -/+ 2,50
    print("[OK] Caso 5: straddle comprado tem dois breakevens e ganho ilimitado.")

    # Caso 6: borboleta - risco e ganho ambos travados
    borboleta = [
        Perna(lado="comprar", tipo="CALL", strike=30.0, premio=3.00),
        Perna(lado="vender", tipo="CALL", strike=35.0, premio=1.50, quantidade=2),
        Perna(lado="comprar", tipo="CALL", strike=40.0, premio=0.50),
    ]
    p_bor = perfil_risco(borboleta)
    assert p_bor.perda_maxima is not None and p_bor.ganho_maximo is not None
    assert p_bor.perda_maxima == -50.0          # debito liquido: 3 - 3 + 0,5 = 0,50
    assert p_bor.ganho_maximo == 450.0          # (35-30-0,50) * 100
    print("[OK] Caso 6: borboleta tem perda e ganho ambos limitados.")

    print("\nTodos os casos passaram.")
