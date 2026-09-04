"""
paginas/historico_opcoes.py - Pagina "Historico Opcoes": wrapper fino em torno
do modulo de Opcoes (modules/opcoes), mesmo padrao de paginas/opcoes.py.
"""
from modules.opcoes.view_historico import render_pagina_historico


def pagina_historico_opcoes():
    render_pagina_historico()
