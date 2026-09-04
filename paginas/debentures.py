"""
paginas/debentures.py - Pagina "Debentures": series coletadas da CVM, com
spread destacado e progresso de prazo.

Separada de paginas/macro.py: debenture e' credito privado, nao indicador
macroeconomico. Estavam juntas so' por historia, e a mistura obrigava a rolar
a pagina inteira de macro para chegar no que interessa de credito.
"""
import pandas as pd
import streamlit as st

from componentes import kpi_card
from dados_app import carregar_debentures
from formatacao import formatar_moeda
from graficos import grafico_barra
from tabelas import colunas_debentures, destacar_spread, progresso_prazo


def pagina_debentures():
    st.subheader("Debêntures")

    deb = carregar_debentures()
    if deb.empty:
        st.info("Sem dados de debêntures disponíveis. Rode `coleta_debentures.py`.")
        return

    d1, d2 = st.columns(2)
    with d1:
        st.markdown(kpi_card("Séries coletadas", str(len(deb))), unsafe_allow_html=True)
    with d2:
        st.markdown(
            kpi_card("Volume total (bi)", formatar_moeda(deb["valor_serie"].sum() / 1e9)),
            unsafe_allow_html=True,
        )

    st.write("**Emissões por indexador**")
    st.plotly_chart(grafico_barra(deb["indexador"].value_counts()), width="stretch", theme=None)

    deb_display = deb[[
        "nome_emissor", "serie", "indexador", "spread", "valor_serie", "prazo_anos",
        "data_emissao", "data_vencimento", "rating", "titulo_incentivado",
        "nome_lider", "agente_fiduciario", "data_encerramento", "link_sre",
    ]].copy()
    for coluna in ["data_emissao", "data_vencimento", "data_encerramento"]:
        deb_display[coluna] = pd.to_datetime(deb_display[coluna], errors="coerce")
    deb_display["valor_serie"] = deb_display["valor_serie"] / 1e6
    deb_display["progresso_prazo"] = deb_display.apply(
        lambda linha: progresso_prazo(linha["data_emissao"], linha["data_vencimento"]), axis=1
    )
    st.dataframe(
        destacar_spread(deb_display),
        width="stretch",
        hide_index=True,
        column_config=colunas_debentures(),
    )
