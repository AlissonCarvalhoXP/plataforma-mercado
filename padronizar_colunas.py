# padronizar_colunas.py  (rodar UMA vez)
import pandas as pd
from sqlalchemy import inspect
from db import engine


def padronizar_colunas(df):
    df = df.copy()
    df.columns = [str(col).strip().lower() for col in df.columns]
    return df


def padronizar_tabelas():
    tabelas = inspect(engine).get_table_names()
    print("Tabelas encontradas:", tabelas)

    for tabela in tabelas:
        df = pd.read_sql(f'SELECT * FROM "{tabela}"', engine)
        antes = list(df.columns)
        df = padronizar_colunas(df)
        if antes != list(df.columns):
            df.to_sql(tabela, engine, if_exists="replace", index=False,
                      chunksize=500, method="multi")
            print(f"  {tabela}: colunas padronizadas ({len(df)} linhas)")
        else:
            print(f"  {tabela}: ja estava em minusculo")

    print("\nPronto! Todas as colunas agora estao em minusculo.")


if __name__ == "__main__":
    padronizar_tabelas()
