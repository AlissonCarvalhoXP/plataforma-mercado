"""
paginas/macro.py - Pagina "Macro": indicadores do BCB e dolar.

Debentures saiu daqui para paginas/debentures.py: credito privado nao e'
indicador macroeconomico, e a mistura obrigava a rolar a pagina inteira de
macro para chegar no que interessa de credito.
"""
import pandas as pd
import streamlit as st

from componentes import kpi_card
from dados_app import calcular_delta_indicador, carregar_dolar, carregar_indicadores, ultimo_valor
from graficos import grafico_linha
from tabelas import colunas_dolar


def _kpi_indicador(ind, nome, label, casas=2, inverter=False, avaliar=True):
    """`avaliar=False`: o delta mostra so a seta, sem cor de julgamento (usado
    em Selic/CDI - juros tem leitura ambigua: bom pra poupador, ruim pra
    tomador). `avaliar=True` (padrao) usa `inverter` para decidir a cor:
    inverter=True inverte a leitura (usado em IPCA/IGP-M - inflacao subindo
    e' desfavoravel, caindo e' favoravel)."""
    valor = round(ultimo_valor(ind, nome), casas)
    valor_texto = f"{valor:.{casas}f}%"
    delta = calcular_delta_indicador(ind, nome)
    if delta is None:
        return kpi_card(label, valor_texto)
    seta = "▲" if delta > 0 else ("▼" if delta < 0 else "•")
    if not avaliar or delta == 0:
        sentido = "neutro"
    elif (delta > 0) != inverter:
        sentido = "positivo"
    else:
        sentido = "negativo"
    delta_texto = f"{seta} {delta:+.{casas}f} p.p."
    return kpi_card(label, valor_texto, delta_texto, sentido)


def pagina_macro():
    st.subheader("Indicadores macro")

    ind = carregar_indicadores()
    dolar = carregar_dolar()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(_kpi_indicador(ind, "Selic", "Selic (% a.a.)", avaliar=False), unsafe_allow_html=True)
    with c2:
        st.markdown(_kpi_indicador(ind, "CDI", "CDI (% a.d.)", casas=4, avaliar=False), unsafe_allow_html=True)
    with c3:
        st.markdown(_kpi_indicador(ind, "IPCA", "IPCA (% mês)", inverter=True), unsafe_allow_html=True)
    with c4:
        st.markdown(_kpi_indicador(ind, "IGP-M", "IGP-M (% mês)", inverter=True), unsafe_allow_html=True)

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
