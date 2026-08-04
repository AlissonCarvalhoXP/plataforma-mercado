# padronizar_colunas.py  (rodar UMA vez)
import pandas as pd
from sqlalchemy import inspect
from db import engine

tabelas = inspect(engine).get_table_names()
print("Tabelas encontradas:", tabelas)

for tabela in tabelas:
    df = pd.read_sql(f'SELECT * FROM "{tabela}"', engine)
    antes = list(df.columns)
    df.columns = [c.lower() for c in df.columns]
    if antes != list(df.columns):
        df.to_sql(tabela, engine, if_exists="replace", index=False,
                  chunksize=500, method="multi")
        print(f"  {tabela}: colunas padronizadas ({len(df)} linhas)")
    else:
        print(f"  {tabela}: ja estava em minusculo")

print("\nPronto! Todas as colunas agora estao em minusculo.")