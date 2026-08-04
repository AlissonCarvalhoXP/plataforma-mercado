# coleta_debentures.py
import requests
import zipfile
import io
import pandas as pd
from db import engine

url = "https://dados.cvm.gov.br/dados/OFERTA/DISTRIB/DADOS/oferta_distribuicao.zip"
resposta = requests.get(url)

zip_arquivo = zipfile.ZipFile(io.BytesIO(resposta.content))
nome_csv = [n for n in zip_arquivo.namelist() if "oferta_resolucao_160" in n][0]
ofertas = pd.read_csv(zip_arquivo.open(nome_csv), sep=";", encoding="latin-1")

debentures = ofertas[ofertas["Valor_Mobiliario"].str.contains("DEB", case=False, na=False)]

colunas = [
    "Numero_Requerimento", "Nome_Emissor", "CNPJ_Emissor", "Emissao",
    "Valor_Mobiliario", "Status_Requerimento",
    "Data_requerimento", "Data_Registro", "Data_Encerramento",
    "Valor_Total_Registrado", "Nome_Lider", "Agente_fiduciario",
    "Titulo_incentivado",
]
debentures = debentures[colunas].copy()

for coluna_data in ["Data_requerimento", "Data_Registro", "Data_Encerramento"]:
    debentures[coluna_data] = pd.to_datetime(debentures[coluna_data], errors="coerce")

debentures["Valor_Total_Registrado"] = (
    debentures["Valor_Total_Registrado"].astype(str)
    .str.replace(".", "", regex=False)
    .str.replace(",", ".", regex=False)
)
debentures["Valor_Total_Registrado"] = pd.to_numeric(debentures["Valor_Total_Registrado"], errors="coerce")

debentures.columns = [c.lower() for c in debentures.columns]   # padroniza minusculo
debentures.to_sql("debentures", engine, if_exists="replace", index=False,
                  chunksize=500, method="multi")

print(f"{len(debentures)} debentures salvas na tabela 'debentures'.")