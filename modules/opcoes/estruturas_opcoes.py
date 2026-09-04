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


def escada_strikes(cadeia: list[dict], tipo: str, vencimento: str) -> list[float]:
    """Strikes distintos e ordenados que realmente existem na cadeia para
    aquele tipo e vencimento."""
    return sorted({
        float(linha["Strike"]) for linha in cadeia
        if linha.get("Tipo") == tipo
        and str(linha.get("Data_Vencimento", ""))[:10] == vencimento[:10]
    })


def selecionar_strike(escada: list[float], spot: float, seletor: str,
                       tipo: str) -> float | None:
    """Indexa a escada de strikes REAL, em vez de selecionar por delta.

    Delta dependeria de qual volatilidade alimenta o modelo; indice sobre a
    cadeia listada e' verificavel por inspecao e nao carrega premissa nenhuma.

    ATM = strike mais proximo do spot. OTM anda no sentido de "sem valor
    intrinseco" (pra cima em CALL, pra baixo em PUT); ITM no sentido oposto.
    Devolve None quando o degrau pedido nao existe na cadeia."""
    if not escada:
        return None
    atm = min(escada, key=lambda k: abs(k - spot))
    indice_atm = escada.index(atm)

    if seletor == "ATM":
        return atm
    if len(seletor) < 4:
        return None
    direcao_texto, passo_texto = seletor[:3], seletor[3:]
    if not passo_texto.isdigit():
        return None
    passo = int(passo_texto)

    if direcao_texto == "OTM":
        deslocamento = passo if tipo == "CALL" else -passo
    elif direcao_texto == "ITM":
        deslocamento = -passo if tipo == "CALL" else passo
    else:
        return None

    indice = indice_atm + deslocamento
    if 0 <= indice < len(escada):
        return escada[indice]
    return None


def pernas_para_json(pernas: list[Perna]) -> str:
    """Serializa as pernas para guardar junto de uma operacao registrada.

    Guardar as pernas, e nao so' o nome da estrutura, e' o que permite
    recalcular o resultado meses depois sem depender de a cadeia daquele dia
    ainda existir no banco - mesmo raciocinio de guardar a distribuicao
    implicita no momento da declaracao."""
    import json
    return json.dumps([{"lado": p.lado, "tipo": p.tipo, "strike": p.strike,
                        "premio": p.premio, "quantidade": p.quantidade,
                        "vencimento": p.vencimento} for p in pernas])


def pernas_de_json(texto: str) -> list[Perna]:
    """Reconstroi as pernas a partir do JSON gravado."""
    import json
    return [Perna(**d) for d in json.loads(texto)]


def resultado_no_vencimento(pernas: list[Perna], preco_realizado: float,
                             premio_executado: float | None = None,
                             lote: int = LOTE_PADRAO_B3) -> float:
    """Resultado em reais da estrutura, ao preco que de fato ocorreu.

    `premio_executado` (liquido, em reais, positivo = debito pago) ajusta o
    resultado quando voce montou a operacao a um preco diferente do exibido na
    tela - o que e' a regra, nao a excecao, por causa do spread. A conta e'
    exata: o payoff e' (valor intrinseco total - premio pago), entao trocar o
    premio desloca o resultado pela diferenca.

    Sem `premio_executado`, devolve o payoff nos precos de tela: mede o que a
    FERRAMENTA teria produzido, nao o que voce conseguiu executar."""
    resultado = payoff_estrutura(pernas, preco_realizado, lote)
    if premio_executado is None:
        return resultado
    return resultado + (premio_liquido(pernas, lote) - premio_executado)


@dataclass(frozen=True)
class DeclaracaoEstrutura:
    """Uma estrutura e' DECLARADA, nao codificada: acrescentar uma linha ao
    CATALOGO basta, porque a matematica de risco (perfil_risco) e' escrita e
    testada uma vez so'. Cada perna e' (lado, tipo, seletor, quantidade)."""
    nome: str
    tese_vol: str        # "cara" | "barata"
    tese_direcao: str    # "alta" | "baixa" | "neutra"
    pernas: tuple[tuple[str, str, str, int], ...]
    exige_posicao: bool = False   # True = so' viavel tendo a acao (venda coberta)


# A ferramenta NUNCA sugere direcao - o eixo direcional vem do cenario
# declarado pelo usuario (ver distribuicao_opcoes.py). Estruturas com
# tese_direcao "neutra" sao as neutras em delta, oferecidas quando nao ha
# visao direcional declarada.
CATALOGO: list[DeclaracaoEstrutura] = [
    # --- neutras em delta: expressam so' a tese de volatilidade ---
    DeclaracaoEstrutura("compra de straddle", "barata", "neutra",
                        (("comprar", "CALL", "ATM", 1), ("comprar", "PUT", "ATM", 1))),
    DeclaracaoEstrutura("compra de strangle", "barata", "neutra",
                        (("comprar", "CALL", "OTM1", 1), ("comprar", "PUT", "OTM1", 1))),
    DeclaracaoEstrutura("venda de straddle", "cara", "neutra",
                        (("vender", "CALL", "ATM", 1), ("vender", "PUT", "ATM", 1))),
    DeclaracaoEstrutura("venda de strangle", "cara", "neutra",
                        (("vender", "CALL", "OTM1", 1), ("vender", "PUT", "OTM1", 1))),
    DeclaracaoEstrutura("borboleta comprada com calls", "cara", "neutra",
                        (("comprar", "CALL", "ITM1", 1), ("vender", "CALL", "ATM", 2),
                         ("comprar", "CALL", "OTM1", 1))),
    DeclaracaoEstrutura("condor com calls", "cara", "neutra",
                        (("comprar", "CALL", "ITM2", 1), ("vender", "CALL", "ITM1", 1),
                         ("vender", "CALL", "OTM1", 1), ("comprar", "CALL", "OTM2", 1))),
    # --- direcionais: so' aparecem com visao declarada ---
    DeclaracaoEstrutura("compra de CALL", "barata", "alta",
                        (("comprar", "CALL", "ATM", 1),)),
    DeclaracaoEstrutura("trava de alta com calls", "barata", "alta",
                        (("comprar", "CALL", "ATM", 1), ("vender", "CALL", "OTM1", 1))),
    DeclaracaoEstrutura("venda de PUT", "cara", "alta",
                        (("vender", "PUT", "OTM1", 1),)),
    DeclaracaoEstrutura("trava de alta com puts", "cara", "alta",
                        (("vender", "PUT", "ATM", 1), ("comprar", "PUT", "OTM1", 1))),
    DeclaracaoEstrutura("compra de PUT", "barata", "baixa",
                        (("comprar", "PUT", "ATM", 1),)),
    DeclaracaoEstrutura("trava de baixa com puts", "barata", "baixa",
                        (("comprar", "PUT", "ATM", 1), ("vender", "PUT", "OTM1", 1))),
    DeclaracaoEstrutura("venda coberta de CALL", "cara", "baixa",
                        (("vender", "CALL", "OTM1", 1),), exige_posicao=True),
    DeclaracaoEstrutura("trava de baixa com calls", "cara", "baixa",
                        (("vender", "CALL", "ATM", 1), ("comprar", "CALL", "OTM1", 1))),
]


@dataclass(frozen=True)
class EstruturaMontada:
    nome: str
    pernas: list[Perna]
    perfil: PerfilRisco


def _indexar_cadeia(cadeia: list[dict], vencimento: str) -> dict[tuple[str, float], dict]:
    return {
        (linha["Tipo"], float(linha["Strike"])): linha
        for linha in cadeia
        if str(linha.get("Data_Vencimento", ""))[:10] == vencimento[:10]
    }


def montar_estruturas(cadeia: list[dict], spot: float, vencimento: str,
                       tese_vol: str, tese_direcao: str, liquidez_min: int = 0,
                       tem_posicao: bool = False) -> tuple[list[EstruturaMontada], list[str]]:
    """Monta toda estrutura do catalogo compativel com a tese, para o
    vencimento dado. Devolve (montadas, motivos_das_recusas).

    Uma estrutura so' e' oferecida se TODAS as pernas existem na cadeia e
    passam na liquidez minima. Quando nao e' possivel, o motivo entra na
    segunda lista - silencio inexplicado seria pior que ausencia."""
    indice = _indexar_cadeia(cadeia, vencimento)
    escadas = {tipo: escada_strikes(cadeia, tipo, vencimento) for tipo in ("CALL", "PUT")}

    # "neutra" oferece so' as neutras em delta; uma visao direcional oferece
    # as daquela direcao MAIS as neutras (que continuam validas).
    if tese_direcao == "neutra":
        direcoes_aceitas = {"neutra"}
    else:
        direcoes_aceitas = {"neutra", tese_direcao}

    montadas: list[EstruturaMontada] = []
    motivos: list[str] = []

    for decl in CATALOGO:
        if decl.tese_vol != tese_vol or decl.tese_direcao not in direcoes_aceitas:
            continue
        if decl.exige_posicao and not tem_posicao:
            # Vender call sem ter o papel nao e' venda coberta, e' venda
            # descoberta - perda ilimitada, perfil totalmente diferente do que
            # o nome da estrutura sugere. Melhor nao oferecer.
            motivos.append(f"{decl.nome}: exige posicao no ativo, que nao ha na carteira")
            continue

        pernas: list[Perna] = []
        motivo_recusa = None
        for lado, tipo, seletor, quantidade in decl.pernas:
            strike = selecionar_strike(escadas[tipo], spot, seletor, tipo)
            if strike is None:
                motivo_recusa = (f"{decl.nome}: cadeia nao tem o strike {seletor} "
                                 f"de {tipo} neste vencimento")
                break
            linha = indice.get((tipo, strike))
            if linha is None:
                motivo_recusa = f"{decl.nome}: serie {tipo} {strike:.2f} nao existe na cadeia"
                break
            if float(linha.get("Liquidez", 0) or 0) < liquidez_min:
                motivo_recusa = (f"{decl.nome}: perna {tipo} {strike:.2f} tem liquidez "
                                 f"abaixo do minimo ({liquidez_min})")
                break
            premio = float(linha.get("Preco_Mercado") or 0)
            pernas.append(Perna(lado=lado, tipo=tipo, strike=strike, premio=premio,
                                quantidade=quantidade, vencimento=vencimento[:10]))

        if motivo_recusa:
            motivos.append(motivo_recusa)
            continue
        montadas.append(EstruturaMontada(nome=decl.nome, pernas=pernas,
                                          perfil=perfil_risco(pernas)))

    return montadas, motivos


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

    # Caso 7: escada de strikes sai ordenada, sem repetir, filtrada por
    # tipo e vencimento
    cadeia_teste = [
        {"Tipo": "CALL", "Strike": 32.0, "Data_Vencimento": "2026-02-20"},
        {"Tipo": "CALL", "Strike": 30.0, "Data_Vencimento": "2026-02-20"},
        {"Tipo": "CALL", "Strike": 34.0, "Data_Vencimento": "2026-02-20"},
        {"Tipo": "CALL", "Strike": 30.0, "Data_Vencimento": "2026-02-20"},  # repetido
        {"Tipo": "PUT",  "Strike": 28.0, "Data_Vencimento": "2026-02-20"},
        {"Tipo": "CALL", "Strike": 99.0, "Data_Vencimento": "2026-03-20"},  # outro venc.
    ]
    esc = escada_strikes(cadeia_teste, "CALL", "2026-02-20")
    assert esc == [30.0, 32.0, 34.0]
    print("[OK] Caso 7: escada de strikes ordenada, sem repeticao, filtrada.")

    # Caso 8: seletores indexam a escada real (nao usam delta - delta dependeria
    # de qual vol alimenta o modelo; indice na escada e' verificavel por
    # inspecao e nao carrega premissa)
    assert selecionar_strike(esc, spot=30.4, seletor="ATM", tipo="CALL") == 30.0
    assert selecionar_strike(esc, spot=30.4, seletor="OTM1", tipo="CALL") == 32.0
    assert selecionar_strike(esc, spot=30.4, seletor="OTM2", tipo="CALL") == 34.0
    assert selecionar_strike(esc, spot=30.4, seletor="OTM3", tipo="CALL") is None
    # pra PUT, OTM e' pra BAIXO do spot
    esc_put = [26.0, 28.0, 30.0, 32.0]
    assert selecionar_strike(esc_put, spot=30.2, seletor="ATM", tipo="PUT") == 30.0
    assert selecionar_strike(esc_put, spot=30.2, seletor="OTM1", tipo="PUT") == 28.0
    assert selecionar_strike(esc_put, spot=30.2, seletor="ITM1", tipo="PUT") == 32.0
    print("[OK] Caso 8: seletores respeitam a direcao de OTM/ITM por tipo.")

    # Caso 9: monta as estruturas viaveis da tese e devolve perfil de risco
    cadeia_completa = []
    for strike, premio in ((28.0, 3.20), (30.0, 1.80), (32.0, 0.90), (34.0, 0.40)):
        cadeia_completa.append({"Codigo_Opcao": f"C{strike:.0f}", "Tipo": "CALL",
                                "Strike": strike, "Data_Vencimento": "2026-02-20",
                                "Preco_Mercado": premio, "Liquidez": 500})
    for strike, premio in ((28.0, 0.50), (30.0, 1.10), (32.0, 2.30), (34.0, 4.10)):
        cadeia_completa.append({"Codigo_Opcao": f"P{strike:.0f}", "Tipo": "PUT",
                                "Strike": strike, "Data_Vencimento": "2026-02-20",
                                "Preco_Mercado": premio, "Liquidez": 500})

    montadas, recusas = montar_estruturas(
        cadeia_completa, spot=30.0, vencimento="2026-02-20",
        tese_vol="barata", tese_direcao="alta")
    nomes = {m.nome for m in montadas}
    assert "compra de CALL" in nomes
    assert "trava de alta com calls" in nomes
    # tese direcional de ALTA nao pode oferecer estrutura de BAIXA
    assert "trava de baixa com puts" not in nomes
    for m in montadas:
        assert m.perfil is not None and len(m.pernas) >= 1
    print("[OK] Caso 9: monta as estruturas da tese, com perfil de risco.")

    # Caso 10: sem visao direcional, so' estruturas neutras em delta
    neutras, _ = montar_estruturas(
        cadeia_completa, spot=30.0, vencimento="2026-02-20",
        tese_vol="barata", tese_direcao="neutra")
    nomes_neutros = {m.nome for m in neutras}
    assert "compra de straddle" in nomes_neutros
    assert "compra de CALL" not in nomes_neutros   # carrega delta, exige visao
    print("[OK] Caso 10: sem visao declarada, so' estruturas neutras em delta.")

    # Caso 11: cadeia pobre recusa a estrutura E diz o motivo, sem silencio
    cadeia_pobre = [
        {"Codigo_Opcao": "C30", "Tipo": "CALL", "Strike": 30.0,
         "Data_Vencimento": "2026-02-20", "Preco_Mercado": 1.80, "Liquidez": 500},
    ]
    poucas, motivos = montar_estruturas(
        cadeia_pobre, spot=30.0, vencimento="2026-02-20",
        tese_vol="barata", tese_direcao="alta")
    assert any("trava de alta com calls" in m for m in motivos)
    assert all(isinstance(m, str) and len(m) > 0 for m in motivos)
    print("[OK] Caso 11: estrutura inviavel e' recusada com motivo explicito.")

    # Caso 12: perna sem liquidez minima barra a estrutura
    cadeia_ilquida = [dict(linha, Liquidez=1) for linha in cadeia_completa]
    nenhuma, motivos_liq = montar_estruturas(
        cadeia_ilquida, spot=30.0, vencimento="2026-02-20",
        tese_vol="barata", tese_direcao="alta", liquidez_min=100)
    assert nenhuma == []
    assert any("liquidez" in m.lower() for m in motivos_liq)
    print("[OK] Caso 12: perna abaixo da liquidez minima barra a estrutura.")

    # Caso 13: venda coberta exige ter a acao. Sem posicao na carteira, a
    # estrutura nao e' oferecida - vender call sem ter o papel e' venda
    # descoberta, perfil de risco completamente diferente do que o nome sugere.
    sem_posicao, motivos_pos = montar_estruturas(
        cadeia_completa, spot=30.0, vencimento="2026-02-20",
        tese_vol="cara", tese_direcao="baixa", tem_posicao=False)
    assert "venda coberta de CALL" not in {m.nome for m in sem_posicao}
    assert any("posicao" in m.lower() for m in motivos_pos)

    com_posicao, _ = montar_estruturas(
        cadeia_completa, spot=30.0, vencimento="2026-02-20",
        tese_vol="cara", tese_direcao="baixa", tem_posicao=True)
    assert "venda coberta de CALL" in {m.nome for m in com_posicao}
    print("[OK] Caso 13: venda coberta so' aparece com posicao na carteira.")

    # Caso 14: pernas sobrevivem a ida e volta em JSON. E' o que permite
    # registrar uma operacao hoje e recalcular o resultado dela meses depois,
    # sem depender de a cadeia daquele dia ainda existir no banco.
    texto = pernas_para_json(trava)
    voltaram = pernas_de_json(texto)
    assert voltaram == trava
    assert payoff_estrutura(voltaram, 40.0) == payoff_estrutura(trava, 40.0)
    print("[OK] Caso 14: pernas sobrevivem a serializacao em JSON.")

    # Caso 15: resultado no vencimento, com e sem preco executado.
    # Sem preco executado, e' o payoff no preco realizado.
    assert resultado_no_vencimento(trava, 40.0) == 350.0
    # Com preco executado PIOR que a tela (paguei 2,00 de debito em vez de
    # 1,50), o resultado cai exatamente a diferenca: 350 - 50 = 300.
    assert resultado_no_vencimento(trava, 40.0, premio_executado=200.0) == 300.0
    # Com preco executado MELHOR que a tela, sobe.
    assert resultado_no_vencimento(trava, 40.0, premio_executado=100.0) == 400.0
    print("[OK] Caso 15: resultado ajusta pelo premio de fato executado.")

    print("\nTodos os casos passaram.")
