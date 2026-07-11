# app.py
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

st.title("Plataforma de Inteligência de Mercado")
st.write("Acompanhamento de indicadores de mercado.")

engine = create_engine("sqlite:///data/mercado.db")

# le os indicadores macro do banco
ind = pd.read_sql("SELECT * FROM indicadores_bcb", engine)


def ultimo_valor(nome):
    # filtra as linhas de um indicador e devolve o valor mais recente
    return ind[ind["indicador"] == nome]["valor"].iloc[-1]


# --- INDICADORES MACRO (cartoes lado a lado) ---
st.subheader("Indicadores macro (Banco Central)")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Selic (% a.a.)", round(ultimo_valor("Selic"), 2))
c2.metric("CDI (% a.d.)", round(ultimo_valor("CDI"), 4))
c3.metric("IPCA (% mes)", round(ultimo_valor("IPCA"), 2))
c4.metric("IGP-M (% mes)", round(ultimo_valor("IGP-M"), 2))

# --- DOLAR ---
dolar = pd.read_sql("SELECT * FROM usd_brl", engine)
st.subheader("Dólar (USD/BRL) — fechamento diario")
st.line_chart(dolar, x="Date", y="Close")
st.dataframe(dolar)
