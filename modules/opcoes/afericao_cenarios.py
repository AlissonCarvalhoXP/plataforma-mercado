"""Afericao dos cenarios declarados: o que voce disse bate com o que aconteceu?

Funcoes puras: nao le banco, nao acessa rede (mesmo padrao de exposicao.py).

Por que esta pergunta vale a pena, ao contrario do Score: calibracao e' uma
pergunta BEM-POSTA. "Quando voce diz 25%, acontece 25% das vezes?" tem resposta
objetiva, verificavel, e nao depende de o modelo prever retorno - mede o
declarante, nao o mercado. Ver secao 4.4c do ROADMAP_MIH_Opcoes_Handoff.md para
o contraste com o Score, que so' conseguimos invalidar.

A mesma tabela e' calculada para a distribuicao IMPLICITA do momento da
declaracao, respondendo "eu fui melhor calibrado que o preco?".

AVISO: calibracao nao implica lucro. Acertar a distribuicao nao diz que havia
vantagem a capturar - so' que sua descricao do futuro era honesta.
"""
from __future__ import annotations

# Com um vencimento a cada ~45 pregoes, sao ~8 observacoes por ano por ativo.
# Abaixo disso a tabela e' ruido; a tela avisa em vez de concluir.
MINIMO_OBSERVACOES = 8

ORDEM_REGIOES = ("baixa", "base", "alta")


def _por_nome(cenarios: list[dict]) -> dict[str, dict]:
    return {c["Cenario"]: c for c in cenarios}


def fronteiras(cenarios: list[dict]) -> tuple[float, float]:
    """Os dois pontos que separam baixa|base|alta: os pontos MEDIOS entre os
    precos-alvo declarados.

    Usar o ponto medio, e nao o proprio alvo, e' o que torna as regioes
    exaustivas e sem sobreposicao - cada preco realizado cai em exatamente uma
    delas. Sem fronteira explicita nao existe afericao: nao daria pra dizer em
    que regiao o resultado caiu."""
    c = _por_nome(cenarios)
    baixa, base, alta = c["baixa"]["Preco_Alvo"], c["base"]["Preco_Alvo"], c["alta"]["Preco_Alvo"]
    return ((baixa + base) / 2, (base + alta) / 2)


def regiao_do_realizado(cenarios: list[dict], preco_realizado: float) -> str:
    """Em qual regiao declarada o preco realizado caiu."""
    inferior, superior = fronteiras(cenarios)
    if preco_realizado < inferior:
        return "baixa"
    if preco_realizado < superior:
        return "base"
    return "alta"


def tabela_calibracao(declaracoes: list[dict]) -> list[dict]:
    """Por regiao: probabilidade media DECLARADA contra frequencia OCORRIDA.

    `declaracoes` sao dicts com "cenarios" (as tres linhas declaradas) e
    "Preco_Realizado". Declaracoes sem realizado sao IGNORADAS - contar uma
    previsao ainda em aberto seria inventar dado.

    Escolhi tabela de calibracao em vez de CRPS aqui de proposito: com ~8
    observacoes por ano, um score agregado seria ruidoso e ilegivel, enquanto
    "voce disse 25% e ocorreu 75%" e' interpretavel na hora."""
    fechadas = [d for d in declaracoes if d.get("Preco_Realizado") is not None]
    if not fechadas:
        return []

    soma_prob = {r: 0.0 for r in ORDEM_REGIOES}
    ocorrencias = {r: 0 for r in ORDEM_REGIOES}
    for d in fechadas:
        c = _por_nome(d["cenarios"])
        for regiao in ORDEM_REGIOES:
            soma_prob[regiao] += float(c[regiao]["Probabilidade"])
        ocorrencias[regiao_do_realizado(d["cenarios"], float(d["Preco_Realizado"]))] += 1

    n = len(fechadas)
    return [{"regiao": regiao,
             "prob_declarada": round(soma_prob[regiao] / n, 4),
             "frequencia": round(ocorrencias[regiao] / n, 4),
             "ocorrencias": ocorrencias[regiao],
             "n": n}
            for regiao in ORDEM_REGIOES]


def resumir_afericao(tabela: list[dict], n_observacoes: int) -> str:
    """Texto legivel do que a tabela permite (ou nao permite) concluir."""
    if not tabela:
        return "Sem declaracoes fechadas ainda - nada a aferir."
    if n_observacoes < MINIMO_OBSERVACOES:
        return (f"Amostra insuficiente: {n_observacoes} de {MINIMO_OBSERVACOES} "
                f"observacoes minimas. A tabela abaixo e' indicativa, nao "
                f"conclusiva - com um vencimento a cada ~45 pregoes, isso leva "
                f"cerca de um ano por ativo.")
    maior_desvio = max(tabela, key=lambda l: abs(l["frequencia"] - l["prob_declarada"]))
    desvio = (maior_desvio["frequencia"] - maior_desvio["prob_declarada"]) * 100
    return (f"{n_observacoes} observacoes. Maior descolamento na regiao "
            f"'{maior_desvio['regiao']}': declarou {maior_desvio['prob_declarada']:.0%}, "
            f"ocorreu {maior_desvio['frequencia']:.0%} ({desvio:+.0f} p.p.).")


if __name__ == "__main__":
    # Caso 1: as fronteiras entre regioes sao os pontos medios entre os
    # precos-alvo declarados. Sem uma fronteira explicita nao da' pra dizer em
    # que regiao o realizado caiu - e sem isso nao ha' afericao nenhuma.
    cenarios = [
        {"Cenario": "baixa", "Preco_Alvo": 28.0, "Probabilidade": 0.25},
        {"Cenario": "base", "Preco_Alvo": 35.0, "Probabilidade": 0.50},
        {"Cenario": "alta", "Preco_Alvo": 42.0, "Probabilidade": 0.25},
    ]
    assert fronteiras(cenarios) == (31.5, 38.5)
    print("[OK] Caso 1: fronteiras sao os pontos medios entre os precos-alvo.")

    # Caso 2: o realizado cai na regiao certa, inclusive nos extremos
    assert regiao_do_realizado(cenarios, 25.0) == "baixa"
    assert regiao_do_realizado(cenarios, 33.0) == "base"
    assert regiao_do_realizado(cenarios, 50.0) == "alta"
    assert regiao_do_realizado(cenarios, 31.4) == "baixa"   # logo abaixo da fronteira
    assert regiao_do_realizado(cenarios, 31.6) == "base"    # logo acima
    print("[OK] Caso 2: regiao_do_realizado classifica pelo ponto medio.")

    # Caso 3: a tabela compara probabilidade DECLARADA com frequencia OCORRIDA.
    # Quatro declaracoes iguais (25/50/25); o realizado caiu 1x na baixa,
    # 2x na base, 1x na alta -> frequencias 25%/50%/25%, perfeitamente calibrado.
    declaracoes = [
        {"cenarios": cenarios, "Preco_Realizado": 25.0},   # baixa
        {"cenarios": cenarios, "Preco_Realizado": 33.0},   # base
        {"cenarios": cenarios, "Preco_Realizado": 36.0},   # base
        {"cenarios": cenarios, "Preco_Realizado": 50.0},   # alta
    ]
    tabela = tabela_calibracao(declaracoes)
    por_regiao = {linha["regiao"]: linha for linha in tabela}
    assert por_regiao["baixa"]["prob_declarada"] == 0.25
    assert por_regiao["baixa"]["frequencia"] == 0.25
    assert por_regiao["base"]["frequencia"] == 0.50
    assert por_regiao["alta"]["frequencia"] == 0.25
    assert all(linha["n"] == 4 for linha in tabela)
    print("[OK] Caso 3: tabela compara probabilidade declarada com frequencia real.")

    # Caso 4: descalibrado e' detectado. Declarou 25% de alta, mas a alta
    # ocorreu em 3 de 4 - a tabela tem que mostrar a discrepancia, nao suaviza-la.
    declaracoes_ruins = [
        {"cenarios": cenarios, "Preco_Realizado": 50.0},
        {"cenarios": cenarios, "Preco_Realizado": 51.0},
        {"cenarios": cenarios, "Preco_Realizado": 52.0},
        {"cenarios": cenarios, "Preco_Realizado": 25.0},
    ]
    por_regiao_ruim = {l["regiao"]: l for l in tabela_calibracao(declaracoes_ruins)}
    assert por_regiao_ruim["alta"]["prob_declarada"] == 0.25
    assert por_regiao_ruim["alta"]["frequencia"] == 0.75
    print("[OK] Caso 4: descalibragem aparece na tabela (25% declarado, 75% ocorrido).")

    # Caso 5: declaracoes SEM realizado sao ignoradas - nao contam como acerto
    # nem como erro. Contar uma previsao ainda em aberto seria inventar dado.
    com_pendente = declaracoes + [{"cenarios": cenarios, "Preco_Realizado": None}]
    assert all(linha["n"] == 4 for linha in tabela_calibracao(com_pendente))
    print("[OK] Caso 5: declaracoes sem realizado sao ignoradas na afericao.")

    # Caso 6: com amostra pequena o resumo AVISA em vez de concluir. Com um
    # vencimento a cada ~45 pregoes, sao ~8 observacoes por ano - a tela vai
    # passar meses aqui, e tem que dizer isso.
    resumo_pouco = resumir_afericao(tabela_calibracao(declaracoes), 4)
    assert "insuficiente" in resumo_pouco.lower()
    resumo_ok = resumir_afericao(tabela_calibracao(declaracoes), 12)
    assert "insuficiente" not in resumo_ok.lower()
    print("[OK] Caso 6: amostra abaixo do minimo gera aviso, nao conclusao.")

    # Caso 7: sem declaracao nenhuma nao quebra nem inventa numero
    assert tabela_calibracao([]) == []
    assert "sem declaracoes" in resumir_afericao([], 0).lower()
    print("[OK] Caso 7: sem declaracoes, devolve vazio sem quebrar.")

    print("\nTodos os casos passaram.")
