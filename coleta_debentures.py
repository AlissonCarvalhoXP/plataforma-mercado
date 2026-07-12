# coleta_debentures.py
import requests
import zipfile
import io
import pandas as pd
from sqlalchemy import create_engine

# 1) baixar o ZIP de ofertas publicas da CVM
url = "https://dados.cvm.gov.br/dados/OFERTA/DISTRIB/DADOS/oferta_distribuicao.zip"
resposta = requests.get(url)

# 2) abrir o ZIP na memoria e achar o CSV da Resolucao 160
zip_arquivo = zipfile.ZipFile(io.BytesIO(resposta.content))
nome_csv = [n for n in zip_arquivo.namelist() if "oferta_resolucao_160" in n][0]

# 3) ler o CSV (separador ";" e encoding latin-1)
ofertas = pd.read_csv(zip_arquivo.open(nome_csv), sep=";", encoding="latin-1")

# 4) filtrar so debentures (todos os indexadores e prazos)
debentures = ofertas[ofertas["Valor_Mobiliario"].str.contains("DEB", case=False, na=False)]

# 5) selecionar as colunas uteis (nivel oferta)
colunas = [
    "Numero_Requerimento", "Nome_Emissor", "CNPJ_Emissor", "Emissao",
    "Valor_Mobiliario", "Status_Requerimento",
    "Data_requerimento", "Data_Registro", "Data_Encerramento",
    "Valor_Total_Registrado", "Nome_Lider", "Agente_fiduciario",
    "Titulo_incentivado",
]
debentures = debentures[colunas].copy()

# 6) limpar as datas (vem em formato ISO no CSV)
for coluna_data in ["Data_requerimento", "Data_Registro", "Data_Encerramento"]:
    debentures[coluna_data] = pd.to_datetime(debentures[coluna_data], errors="coerce")

# 7) limpar o valor (formato BR "1.000.000,00" -> numero)
debentures["Valor_Total_Registrado"] = (
    debentures["Valor_Total_Registrado"].astype(str)
    .str.replace(".", "", regex=False)
    .str.replace(",", ".", regex=False)
)
debentures["Valor_Total_Registrado"] = pd.to_numeric(debentures["Valor_Total_Registrado"], errors="coerce")

# 8) salvar no banco
engine = create_engine("sqlite:///data/mercado.db")
debentures.to_sql("debentures", engine, if_exists="replace", index=False)

print(f"{len(debentures)} debentures salvas na tabela 'debentures'.")
print(debentures.head())