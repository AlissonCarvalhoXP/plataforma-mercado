"""
componentes.py - Helpers de apresentacao reutilizaveis entre paginas.
Funcoes puras (recebem dados, devolvem string) - sem leitura de banco
nem import de streamlit.
"""

_BADGES = {"desfavoravel": "🔴", "favoravel": "🟢", "neutro": "⚪"}


def badge_sinal(sinal):
    """Formata um dict de sinal (do formato de exposicao.gerar_sinais_exposicao)
    como uma linha de markdown com o badge de cor correspondente."""
    marcador = _BADGES[sinal["sentido_impacto"]]
    return f"{marcador} {sinal['texto']}"


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

    print("\nTodos os casos passaram.")
