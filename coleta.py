# coleta.py
import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine

# 1) COLETA
dolar = yf.download("BRL=X", period="6mo", interval="1d")

# 2) LIMPEZA
dolar.columns = dolar.columns.droplevel(1)
dolar.columns.name = None
dolar = dolar.reset_index()

# 3) INCREMENTAL: guardar so os dias novos
from db import engine

# le as datas que ja estao no banco (convertendo de volta para data)
existentes = pd.read_sql("SELECT Date FROM usd_brl", engine, parse_dates=["Date"])

# mantem so as linhas cujas datas ainda NAO estao no banco
novos = dolar[~dolar["Date"].isin(existentes["Date"])]

# acrescenta so os novos
novos.to_sql("usd_brl", engine, if_exists="append", index=False)

print(f"{len(novos)} novos dias adicionados.")
