# coleta_bcb.py
import requests
import pandas as pd
from sqlalchemy import create_engine


def buscar_serie_bcb(codigo, n=12):
    # busca as ultimas N observacoes de uma serie do BCB e devolve um DataFrame limpo
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados/ultimos/{n}?formato=json"
    resposta = requests.get(url)
    df = pd.DataFrame(resposta.json())
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df["valor"] = pd.to_numeric(df["valor"])
    return df


# dicionario: nome do indicador -> codigo no BCB
indicadores = {
    "Selic": 432,
    "CDI": 12,
    "IPCA": 433,
    "IGP-M": 189,
}

# laco: busca cada indicador e junta numa lista
lista = []
for nome, codigo in indicadores.items():
    df = buscar_serie_bcb(codigo)
    df["indicador"] = nome
    lista.append(df)

todos = pd.concat(lista, ignore_index=True)

# --- INCREMENTAL: guardar so o que e novo ---
from db import engine

# combinacoes (indicador + data) que ja estao no banco
existentes = pd.read_sql("SELECT indicador, data FROM indicadores_bcb", engine, parse_dates=["data"])

# cria uma "chave" unica juntando indicador + data (nos dois DataFrames)
todos["chave"] = todos["indicador"] + " " + todos["data"].astype(str)
existentes["chave"] = existentes["indicador"] + " " + existentes["data"].astype(str)

# mantem so as linhas cuja chave ainda NAO existe, e remove a coluna auxiliar
novos = todos[~todos["chave"].isin(existentes["chave"])].drop(columns="chave")

# acrescenta so os novos
novos.to_sql("indicadores_bcb", engine, if_exists="append", index=False)

print(f"{len(novos)} novos registros adicionados.")