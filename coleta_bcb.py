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

# empilha todos os DataFrames num so
todos = pd.concat(lista, ignore_index=True)

# salva no banco, na tabela "indicadores_bcb"
engine = create_engine("sqlite:///data/mercado.db")
todos.to_sql("indicadores_bcb", engine, if_exists="replace", index=False)

print(f"Salvos {len(todos)} registros de {len(indicadores)} indicadores!")
print(todos["indicador"].value_counts())