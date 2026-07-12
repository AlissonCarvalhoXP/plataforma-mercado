# analises.py
import pandas as pd
from sqlalchemy import create_engine

engine = create_engine("sqlite:///data/mercado.db")


def analisar_dolar():
    dolar = pd.read_sql("SELECT Date, Close FROM usd_brl ORDER BY Date", engine)
    if len(dolar) < 6:
        return "Dados insuficientes para analisar o dolar."
    atual = dolar["Close"].iloc[-1]
    semana_atras = dolar["Close"].iloc[-6]
    variacao = (atual - semana_atras) / semana_atras * 100
    if variacao > 2:
        leitura = "alta expressiva - possivel aversao a risco global e pressao sobre emergentes."
    elif variacao > 0.5:
        leitura = "leve alta - real um pouco mais fraco."
    elif variacao < -2:
        leitura = "queda expressiva - real mais forte, possivel apetite a risco / juros atrativos."
    elif variacao < -0.5:
        leitura = "leve queda - real um pouco mais forte."
    else:
        leitura = "estabilidade - sem movimento relevante na semana."
    return f"USD/BRL fechou em R$ {atual:.2f} ({variacao:+.2f}% na semana). Leitura: {leitura}"


def analisar_selic():
    selic = pd.read_sql("SELECT valor FROM indicadores_bcb WHERE indicador = 'Selic' ORDER BY data", engine)
    if selic.empty:
        return "Sem dados de Selic."
    atual = selic["valor"].iloc[-1]
    anterior = selic["valor"].iloc[0]
    if atual > anterior:
        return f"Selic subiu para {atual:.2f}% a.a. - politica monetaria mais restritiva."
    elif atual < anterior:
        return f"Selic caiu para {atual:.2f}% a.a. - politica monetaria mais frouxa."
    else:
        return f"Selic estavel em {atual:.2f}% a.a. - Copom manteve a taxa."


def analisar_debentures():
    deb = pd.read_sql("SELECT Indexador FROM debentures_series", engine)
    if deb.empty:
        return "Sem dados de debentures."
    total = len(deb)
    contagem = deb["Indexador"].value_counts()
    cdi = contagem.get("CDI", 0)
    ipca = contagem.get("IPCA", 0)
    return f"{total} series de debentures na base: {cdi} em CDI e {ipca} em IPCA - CDI segue como principal indexador."


if __name__ == "__main__":
    print(analisar_dolar())
    print(analisar_selic())
    print(analisar_debentures())