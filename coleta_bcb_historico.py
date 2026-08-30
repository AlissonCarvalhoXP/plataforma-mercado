"""coleta_bcb_historico.py - Backfill de historico de indicadores do BCB (Selic,
CDI, IPCA, IGP-M) para um intervalo de datas, complementando coleta_bcb.py
(que so traz os "ultimos N" registros - pensado pra coleta diaria incremental,
nao pra preencher historico de anos passados).

Motivacao: o backfill de historico de opcoes via COTAHIST
(modules/opcoes/coleta_cotahist.py) precisa da Selic real de 2024/2025 como
taxa livre de risco no calculo de IV - sem isso, selic_mais_proxima() cai
sempre na unica leitura disponivel (a mais recente, de hoje), aplicando uma
taxa de anos depois a opcoes historicas. Descoberto na pratica: antes deste
backfill, indicadores_bcb so tinha 60 leituras de Selic, todas entre
2026-07-25 e 2026-09-16.

Uso:
    python coleta_bcb_historico.py --inicio 01/01/2024 --fim 31/12/2025
"""
import requests
import pandas as pd
from db import engine

indicadores = {"Selic": 432, "CDI": 12, "IPCA": 433, "IGP-M": 189}


def buscar_serie_bcb_intervalo(codigo, data_inicial, data_final):
    """Busca uma serie do BCB SGS num intervalo de datas explicito (formato
    DD/MM/AAAA) - diferente de coleta_bcb.py, que so traz os "ultimos N"."""
    url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
           f"?dataInicial={data_inicial}&dataFinal={data_final}&formato=json")
    resposta = requests.get(url, timeout=60)
    resposta.raise_for_status()
    df = pd.DataFrame(resposta.json())
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df["valor"] = pd.to_numeric(df["valor"])
    return df


def backfill(data_inicial, data_final):
    """Baixa Selic/CDI/IPCA/IGP-M no intervalo e grava so o que ainda nao
    existe em indicadores_bcb (mesma chave incremental de coleta_bcb.py:
    indicador + data)."""
    lista = []
    for nome, codigo in indicadores.items():
        df = buscar_serie_bcb_intervalo(codigo, data_inicial, data_final)
        df["indicador"] = nome
        lista.append(df)
        print(f"{nome}: {len(df)} leituras baixadas ({data_inicial} a {data_final}).")

    todos = pd.concat(lista, ignore_index=True)

    existentes = pd.read_sql("SELECT indicador, data FROM indicadores_bcb", engine, parse_dates=["data"])
    todos["chave"] = todos["indicador"] + " " + todos["data"].astype(str)
    existentes["chave"] = existentes["indicador"] + " " + existentes["data"].astype(str)
    novos = todos[~todos["chave"].isin(existentes["chave"])].drop(columns="chave")

    novos.to_sql("indicadores_bcb", engine, if_exists="append", index=False)
    print(f"{len(novos)} novos registros adicionados a indicadores_bcb.")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--inicio", default="01/01/2024")
    ap.add_argument("--fim", default="31/12/2025")
    args = ap.parse_args()
    backfill(args.inicio, args.fim)
