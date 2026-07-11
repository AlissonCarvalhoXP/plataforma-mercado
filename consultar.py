# consultar.py
import pandas as pd
from sqlalchemy import create_engine

# conecta no MESMO arquivo de banco
engine = create_engine("sqlite:///data/mercado.db")

# le TUDO da tabela usando uma consulta SQL
dados = pd.read_sql("SELECT * FROM usd_brl", engine)

print(f"A tabela tem {len(dados)} linhas.")
print(dados.tail())