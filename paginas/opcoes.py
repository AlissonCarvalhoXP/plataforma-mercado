"""
paginas/opcoes.py - Pagina "Opcoes": wrapper fino em torno do modulo de
Opcoes B3 (modules/opcoes), que ja tem sua propria UI Plotly.
"""
from dados_app import carregar_carteira, carregar_indicadores, ultimo_valor
from modules.opcoes.view_opcoes import render_aba_opcoes


def pagina_opcoes():
    ind = carregar_indicadores()
    carteira_df = carregar_carteira()
    render_aba_opcoes(selic=ultimo_valor(ind, "Selic") / 100, carteira_df=carteira_df)
