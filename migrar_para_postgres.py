# migrar_para_postgres.py
import os
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERRO: DATABASE_URL nao encontrado no .env.")
    print("Adicione (em UMA linha): DATABASE_URL=postgresql://usuario:senha@host/dbname?sslmode=require")
    raise SystemExit

origem = create_engine("sqlite:///data/mercado.db")
destino = create_engine(DATABASE_URL)

tabelas = inspect(origem).get_table_names()
print("Tabelas a migrar:", tabelas)

for tabela in tabelas:
    df = pd.read_sql(f"SELECT * FROM {tabela}", origem)
    df.to_sql(tabela, destino, if_exists="replace", index=False, chunksize=500, method="multi")
    print(f"  {tabela}: {len(df)} linhas migradas")

print("\nMigracao concluida!")