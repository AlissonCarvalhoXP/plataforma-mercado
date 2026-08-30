"""
paginas/macro.py - Pagina "Macro": indicadores do BCB, dolar e debentures.
Extraida de app.py sem mudanca de logica, so trocando st.line_chart/
st.bar_chart por graficos.grafico_linha/graficos.grafico_barra.
"""
import pandas as pd
import streamlit as st

from dados_app import carregar_debentures, carregar_dolar, carregar_indicadores, ultimo_valor
from formatacao import formatar_data_br, formatar_moeda
from graficos import grafico_barra, grafico_linha


def pagina_macro():
    st.subheader("Indicadores macro")

    ind = carregar_indicadores()
    dolar = carregar_dolar()
    deb = carregar_debentures()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Selic (% a.a.)", round(ultimo_valor(ind, "Selic"), 2))
    c2.metric("CDI (% a.d.)", round(ultimo_valor(ind, "CDI"), 4))
    c3.metric("IPCA (% mes)", round(ultimo_valor(ind, "IPCA"), 2))
    c4.metric("IGP-M (% mes)", round(ultimo_valor(ind, "IGP-M"), 2))

    st.subheader("Dólar (USD/BRL)")
    if not dolar.empty:
        st.plotly_chart(grafico_linha(dolar, "date", "close", titulo="USD/BRL"), width="stretch", theme=None)
        dolar_display = dolar.copy()
        dolar_display["date"] = dolar_display["date"].apply(formatar_data_br)
        dolar_display["close"] = dolar_display["close"].apply(lambda x: f"R$ {x:.4f}")
        st.dataframe(dolar_display, width="stretch", hide_index=True)
    else:
        st.info("Sem dados de dólar disponíveis.")

    st.subheader("Debêntures")
    if not deb.empty:
        d1, d2 = st.columns(2)
        d1.metric("Séries coletadas", len(deb))
        d2.metric("Volume total (R$ bi)", round(deb["valor_serie"].sum() / 1e9, 2))
        st.write("**Emissões por indexador**")
        st.plotly_chart(grafico_barra(deb["indexador"].value_counts()), width="stretch", theme=None)
        deb_display = deb[[
            "nome_emissor", "serie", "indexador", "spread", "valor_serie", "prazo_anos",
            "data_emissao", "data_vencimento", "rating", "titulo_incentivado",
            "nome_lider", "agente_fiduciario", "data_encerramento", "link_sre",
        ]].copy()
        for coluna in ["data_emissao", "data_vencimento", "data_encerramento"]:
            if coluna in deb_display.columns:
                deb_display[coluna] = deb_display[coluna].apply(formatar_data_br)
        if "valor_serie" in deb_display.columns:
            deb_display["valor_serie"] = deb_display["valor_serie"].apply(lambda x: formatar_moeda(x / 1e6) if pd.notna(x) else "")
        if "spread" in deb_display.columns:
            deb_display["spread"] = deb_display["spread"].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "")
        st.dataframe(deb_display, width="stretch", hide_index=True)
    else:
        st.info("Sem dados de debêntures disponíveis.")
