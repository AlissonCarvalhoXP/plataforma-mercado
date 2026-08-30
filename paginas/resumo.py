"""
paginas/resumo.py - Pagina "Resumo": briefing do dia, destaques, exposicao
da carteira e sinais do dia. Extraida de app.py sem mudanca de logica,
so trocando st.bar_chart por graficos.grafico_barra e o badge manual por
componentes.badge_sinal.
"""
import pandas as pd
import streamlit as st

from componentes import badge_sinal
from dados_app import carregar_carteira, carregar_dolar, carregar_indicadores
from db import engine
from exposicao import gerar_sinais_exposicao, resumo_exposicao_por_indexador
from graficos import grafico_barra


def pagina_resumo():
    st.subheader("Resumo executivo")

    try:
        briefing = pd.read_sql("SELECT texto FROM briefing", engine)
        if not briefing.empty:
            st.info(briefing["texto"].iloc[0])
    except Exception:
        st.write("Rode o briefing.py para gerar o comentário do dia.")

    try:
        destaques = pd.read_sql("SELECT texto FROM destaques", engine)
        if not destaques.empty:
            st.markdown("**⚡ Destaques do dia**")
            st.markdown(destaques["texto"].iloc[0])
    except Exception:
        pass

    carteira_df = carregar_carteira()
    ind = carregar_indicadores()
    dolar = carregar_dolar()

    st.markdown("**Exposição da carteira**")
    resumo_exposicao = resumo_exposicao_por_indexador(carteira_df)
    if resumo_exposicao.empty:
        st.info("Carteira vazia, sem sinais a mostrar.")
    else:
        st.plotly_chart(grafico_barra(resumo_exposicao), width="stretch", theme=None)

        st.markdown("**Sinais do dia**")
        sinais = gerar_sinais_exposicao(carteira_df, ind, dolar)
        if not sinais:
            st.caption("Sem sinais no momento (dados insuficientes para calcular variação).")
        else:
            for sinal in sinais:
                st.markdown(badge_sinal(sinal))
