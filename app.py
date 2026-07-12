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
    return ind[ind["indicador"] == nome]["valor"].iloc[-1]


# --- INDICADORES MACRO ---
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

# --- DEBENTURES (novas emissoes CVM) ---
st.subheader("Debêntures — novas emissões (CVM)")
deb = pd.read_sql("SELECT * FROM debentures_series", engine)

d1, d2 = st.columns(2)
d1.metric("Séries coletadas", len(deb))
d2.metric("Volume total (R$ bi)", round(deb["Valor_Serie"].sum() / 1e9, 2))

st.write("**Emissões por indexador**")
st.bar_chart(deb["Indexador"].value_counts())

st.write("**Detalhe das séries**")
st.dataframe(deb[["Serie", "Valor_Serie", "Indexador", "Prazo_Anos", "Data_Vencimento", "Rating"]])