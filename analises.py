# analises.py
import pandas as pd
from sqlalchemy import create_engine

engine = create_engine("sqlite:///data/mercado.db")


def analisar_dolar():
    dolar = pd.read_sql("SELECT Date, Close FROM usd_brl ORDER BY Date", engine)
    if len(dolar) < 6:
        return "Dados insuficientes para analisar o dolar."

    atual = dolar["Close"].iloc[-1]
    semana_atras = dolar["Close"].iloc[-6]      # ~5 pregoes atras
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


print(analisar_dolar())