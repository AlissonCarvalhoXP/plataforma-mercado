# migrar_para_postgres.py
import os
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect


def normalizar_colunas(df):
    """Padroniza nomes de colunas para minúsculas antes de criar a tabela no Postgres."""
    df = df.copy()
    df.columns = [str(col).strip().lower() for col in df.columns]
    return df


def migrar_banco(origem_url="sqlite:///data/mercado.db", destino_url=None):
    load_dotenv()
    destino_url = destino_url or os.getenv("DATABASE_URL")
    if not destino_url:
        raise ValueError(
            "DATABASE_URL nao encontrado. Adicione no .env: DATABASE_URL=postgresql://..."
        )

    origem = create_engine(origem_url)
    destino = create_engine(destino_url)

    tabelas = inspect(origem).get_table_names()
    print("Tabelas a migrar:", tabelas)

    for tabela in tabelas:
        df = pd.read_sql(f'SELECT * FROM "{tabela}"', origem)
        antes = list(df.columns)
        df = normalizar_colunas(df)
        df.to_sql(tabela, destino, if_exists="replace", index=False, chunksize=500, method="multi")
        status = "sem mudanca" if antes == list(df.columns) else "colunas padronizadas"
        print(f"  {tabela}: {len(df)} linhas migradas ({status})")

    print("\nMigracao concluida!")


if __name__ == "__main__":
    migrar_banco()
