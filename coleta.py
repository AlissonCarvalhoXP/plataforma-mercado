# coleta.py
import yfinance as yf
from sqlalchemy import create_engine

# 1) COLETA
dados = yf.download("BRL=X", period="6mo", interval="1d")

# 2) LIMPEZA
dados.columns = dados.columns.droplevel(1)   # remove o nivel do ticker
dados.columns.name = None                    # remove o rotulo "Price" do canto
dados = dados.reset_index()                  # a data vira a coluna "Date"

# 3) ARMAZENAMENTO
engine = create_engine("sqlite:///data/mercado.db")
dados.to_sql("usd_brl", engine, if_exists="replace", index=False)

print("Dados salvos no banco com sucesso!")
print(f"{len(dados)} linhas gravadas na tabela 'usd_brl'.")