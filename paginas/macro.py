"""
paginas/macro.py - Pagina "Macro": indicadores do BCB, dolar e debentures.
Cards de KPI (Terminal Cartesiano) no lugar de st.metric, colunas tipadas
via tabelas.py nas tabelas, e destaque condicional do spread.
"""
import pandas as pd
import streamlit as st

from componentes import kpi_card
from dados_app import calcular_delta_indicador, carregar_debentures, carregar_dolar, carregar_indicadores, ultimo_valor
from formatacao import formatar_moeda
from graficos import grafico_barra, grafico_linha
from tabelas import colunas_debentures, colunas_dolar, destacar_spread, progresso_prazo


def _kpi_indicador(ind, nome, label, casas=2):
    valor = round(ultimo_valor(ind, nome), casas)
    valor_texto = f"{valor:.{casas}f}%"
    delta = calcular_delta_indicador(ind, nome)
    if delta is None:
        return kpi_card(label, valor_texto)
    seta = "▲" if delta > 0 else ("▼" if delta < 0 else "•")
    sentido = "positivo" if delta > 0 else ("negativo" if delta < 0 else "neutro")
    delta_texto = f"{seta} {delta:+.{casas}f} p.p."
    return kpi_card(label, valor_texto, delta_texto, sentido)


def pagina_macro():
    st.subheader("Indicadores macro")

    ind = carregar_indicadores()
    dolar = carregar_dolar()
    deb = carregar_debentures()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(_kpi_indicador(ind, "Selic", "Selic (% a.a.)"), unsafe_allow_html=True)
    with c2:
        st.markdown(_kpi_indicador(ind, "CDI", "CDI (% a.d.)", casas=4), unsafe_allow_html=True)
    with c3:
        st.markdown(_kpi_indicador(ind, "IPCA", "IPCA (% mês)"), unsafe_allow_html=True)
    with c4:
        st.markdown(_kpi_indicador(ind, "IGP-M", "IGP-M (% mês)"), unsafe_allow_html=True)

    st.subheader("Dólar (USD/BRL)")
    if not dolar.empty:
        st.plotly_chart(grafico_linha(dolar, "date", "close", titulo="USD/BRL"), width="stretch", theme=None)
        st.dataframe(
            dolar.assign(date=pd.to_datetime(dolar["date"], errors="coerce")),
            width="stretch",
            hide_index=True,
            column_config=colunas_dolar(),
        )
    else:
        st.info("Sem dados de dólar disponíveis.")

    st.subheader("Debêntures")
    if not deb.empty:
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
    else:
        st.info("Sem dados de debêntures disponíveis.")
