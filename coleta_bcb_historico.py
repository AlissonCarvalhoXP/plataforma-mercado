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


def _engine_destino(db_path=None):
    """db_path=None -> engine padrao do app (db.engine, respeita DATABASE_URL,
    pode ser Postgres remoto). db_path=caminho -> SQLite LOCAL direto, sem
    depender de rede nenhuma alem da API do BCB.

    Por que isso existe: modules/opcoes/ e' deliberadamente isolado do
    DATABASE_URL remoto (db_opcoes.py ignora DATABASE_URL de proposito - ver
    seu docstring). coleta_cotahist.py precisa da Selic historica pra calcular
    IV, e depender do Postgres remoto no meio de um job de varios minutos
    processando um arquivo local grande e' fragil (conexao pode cair -
    aconteceu na pratica: PendingRollbackError e depois um socket preso em
    CloseWait travando o processo indefinidamente). Rodar este backfill
    tambem contra o SQLite local elimina essa dependencia pra esse pipeline."""
    if db_path:
        import sqlite3
        return sqlite3.connect(db_path)
    from db import engine
    return engine


def backfill(data_inicial, data_final, db_path=None):
    """Baixa Selic/CDI/IPCA/IGP-M no intervalo e grava so o que ainda nao
    existe em indicadores_bcb (mesma chave incremental de coleta_bcb.py:
    indicador + data). db_path=None grava no destino padrao do app (pode ser
    Postgres remoto); db_path=caminho grava direto num SQLite local."""
    destino = _engine_destino(db_path)
    try:
        lista = []
        for nome, codigo in indicadores.items():
            df = buscar_serie_bcb_intervalo(codigo, data_inicial, data_final)
            df["indicador"] = nome
            lista.append(df)
            print(f"{nome}: {len(df)} leituras baixadas ({data_inicial} a {data_final}).")

        todos = pd.concat(lista, ignore_index=True)

        try:
            existentes = pd.read_sql("SELECT indicador, data FROM indicadores_bcb", destino, parse_dates=["data"])
        except Exception:
            existentes = pd.DataFrame(columns=["indicador", "data"])
        todos["chave"] = todos["indicador"] + " " + todos["data"].astype(str)
        existentes["chave"] = existentes["indicador"] + " " + existentes["data"].astype(str)
        novos = todos[~todos["chave"].isin(existentes["chave"])].drop(columns="chave")

        novos.to_sql("indicadores_bcb", destino, if_exists="append", index=False)
        print(f"{len(novos)} novos registros adicionados a indicadores_bcb.")
    finally:
        if db_path:
            destino.close()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--inicio", default="01/01/2024")
    ap.add_argument("--fim", default="31/12/2025")
    ap.add_argument("--db-path", default=None,
                    help="grava direto num SQLite local (ex.: data/mercado.db) "
                         "em vez do destino padrao do app (db.engine)")
    args = ap.parse_args()
    backfill(args.inicio, args.fim, args.db_path)
