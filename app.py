# app.py
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

st.title("Plataforma de Inteligência de Mercado")
st.write("Acompanhamento de indicadores de mercado.")

# le os dados do banco
engine = create_engine("sqlite:///data/mercado.db")
dados = pd.read_sql("SELECT * FROM usd_brl", engine)

# grafico do dolar
st.subheader("Dólar (USD/BRL) — fechamento diário")
st.line_chart(dados, x="Date", y="Close")

# tabela completa embaixo
st.subheader("Histórico completo")
st.dataframe(dados)