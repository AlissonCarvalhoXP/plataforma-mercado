# coleta.py
import yfinance as yf
import pandas as pd
from db import engine

# 1) COLETA
dolar = yf.download("BRL=X", period="6mo", interval="1d")

# 2) LIMPEZA
dolar.columns = dolar.columns.droplevel(1)
dolar.columns.name = None
dolar = dolar.reset_index()
dolar.columns = [c.lower() for c in dolar.columns]   # padroniza em minusculo

# 3) INCREMENTAL: guardar so os dias novos
existentes = pd.read_sql("SELECT date FROM usd_brl", engine, parse_dates=["date"])
novos = dolar[~dolar["date"].isin(existentes["date"])]
novos.to_sql("usd_brl", engine, if_exists="append", index=False)

print(f"{len(novos)} novos dias adicionados.")