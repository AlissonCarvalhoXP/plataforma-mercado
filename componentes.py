"""
componentes.py - Helpers de apresentacao reutilizaveis entre paginas.
Funcoes puras (recebem dados, devolvem string) - sem leitura de banco
nem import de streamlit.
"""

_BADGES = {"desfavoravel": "🔴", "favoravel": "🟢", "neutro": "⚪"}

_CLASSES_DELTA_VALIDAS = {"positivo", "negativo", "neutro"}


def kpi_card(label, valor_texto, delta_texto=None, sentido=None):
    """Monta o HTML de um card de KPI no estilo Terminal Cartesiano. `sentido`
    (quando informado) e' "positivo"/"negativo"/"neutro" - direcao do valor,
    nao o vocabulario de exposicao.gerar_sinais_exposicao."""
    delta_html = ""
    if delta_texto is not None:
        classe = sentido if sentido in _CLASSES_DELTA_VALIDAS else "neutro"
        delta_html = f'<span class="kpi-delta {classe}">{delta_texto}</span>'
    return (
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{valor_texto}{delta_html}</div>'
        f'</div>'
    )


def badge_sinal(sinal):
    """Formata um dict de sinal (do formato de exposicao.gerar_sinais_exposicao)
    como uma linha de markdown com o badge de cor correspondente."""
    marcador = _BADGES[sinal["sentido_impacto"]]
    return f"{marcador} {sinal['texto']}"


_CLASSES_OPORTUNIDADE_VALIDAS = {"compra", "venda"}


def card_oportunidade(titulo, texto, tipo):
    """Monta o HTML de um card de oportunidade/recomendacao no estilo Terminal
    Cartesiano (mesma familia visual do kpi_card). `tipo` e' "compra" ou
    "venda" - a cor da borda e' definida no CSS do tema (tema.py), nao aqui;
    qualquer outro valor cai numa borda neutra."""
    classe = tipo if tipo in _CLASSES_OPORTUNIDADE_VALIDAS else "neutra"
    return (
        f'<div class="oportunidade-card {classe}">'
        f'<div class="oportunidade-titulo">{titulo}</div>'
        f'<div class="oportunidade-texto">{texto}</div>'
        f'</div>'
    )


if __name__ == "__main__":
    sinal_fav = {"sentido_impacto": "favoravel", "texto": "Dólar variou +R$ 0,04 -> favorece R$ 1.000,00 em Dólar (long)"}
    assert badge_sinal(sinal_fav) == "🟢 Dólar variou +R$ 0,04 -> favorece R$ 1.000,00 em Dólar (long)"
    print("[OK] Caso 1: badge_sinal formata sinal favoravel.")

    sinal_desf = {"sentido_impacto": "desfavoravel", "texto": "Selic variou +0.25 p.p. -> pressiona R$ 5.000,00 em Prefixado (long)"}
    assert badge_sinal(sinal_desf) == "🔴 Selic variou +0.25 p.p. -> pressiona R$ 5.000,00 em Prefixado (long)"
    print("[OK] Caso 2: badge_sinal formata sinal desfavoravel.")

    sinal_neutro = {"sentido_impacto": "neutro", "texto": "Selic nao variou -> nao afeta R$ 2.000,00 em CDI (long)"}
    assert badge_sinal(sinal_neutro) == "⚪ Selic nao variou -> nao afeta R$ 2.000,00 em CDI (long)"
    print("[OK] Caso 3: badge_sinal formata sinal neutro.")

    html_sem_delta = kpi_card("Selic", "14,00%")
    assert html_sem_delta == '<div class="kpi-card"><div class="kpi-label">Selic</div><div class="kpi-value">14,00%</div></div>'
    print("[OK] Caso 4: kpi_card sem delta.")

    html_positivo = kpi_card("Selic", "14,00%", "▲ +0.25 p.p.", "positivo")
    assert '<span class="kpi-delta positivo">▲ +0.25 p.p.</span>' in html_positivo
    print("[OK] Caso 5: kpi_card com delta positivo.")

    html_negativo = kpi_card("IPCA", "0,07%", "▼ -0.10 p.p.", "negativo")
    assert 'kpi-delta negativo' in html_negativo
    print("[OK] Caso 6: kpi_card com delta negativo.")

    html_sentido_invalido = kpi_card("X", "1", "0", "sentido-desconhecido")
    assert 'kpi-delta neutro' in html_sentido_invalido
    print("[OK] Caso 7: sentido invalido cai em neutro.")

    html_compra = card_oportunidade("Melhor compra de vol", "PETRC300 ...", "compra")
    assert 'class="oportunidade-card compra"' in html_compra
    assert "Melhor compra de vol" in html_compra and "PETRC300 ..." in html_compra
    print("[OK] Caso 8: card_oportunidade com tipo compra.")

    html_venda = card_oportunidade("Melhor venda de vol", "PETRP280 ...", "venda")
    assert 'class="oportunidade-card venda"' in html_venda
    print("[OK] Caso 9: card_oportunidade com tipo venda.")

    html_neutro = card_oportunidade("X", "y", "tipo-desconhecido")
    assert 'class="oportunidade-card neutra"' in html_neutro
    print("[OK] Caso 10: tipo invalido cai em neutra.")

    print("\nTodos os casos passaram.")
