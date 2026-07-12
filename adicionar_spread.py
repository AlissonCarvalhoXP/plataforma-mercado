# adicionar_spread.py
import re
import pandas as pd
from sqlalchemy import create_engine


def extrair_spread(texto):
    if not isinstance(texto, str):
        return None
    t = texto.replace(",", ".")  # decimal com ponto
    # 1) padrao "+ X%" (CDI + 1.35%, DI+2.40%, IPCA + 6.20%)
    m = re.search(r"\+\s*(\d+(?:\.\d+)?)\s*%", t)
    if m:
        return float(m.group(1))
    # 2) "spread / sobretaxa / acrescida ... de X%"
    m = re.search(r"(?:spread|sobretaxa|acrescid\w+)[^%]*?de\s*(\d+(?:\.\d+)?)\s*%", t, re.IGNORECASE)
    if m:
        return float(m.group(1))
    # 3) prefixado: taxa isolada no comeco (ex.: 7.10%)
    m = re.match(r"\s*(\d+\.\d+)\s*%", t)
    if m:
        return float(m.group(1))
    return None


engine = create_engine("sqlite:///data/mercado.db")
deb = pd.read_sql("SELECT * FROM debentures_series", engine)

deb["Spread"] = deb["Remuneracao"].apply(extrair_spread)
deb.to_sql("debentures_series", engine, if_exists="replace", index=False)

print(f"{deb['Spread'].notna().sum()} de {len(deb)} series com spread extraido.")
print("\nSpread medio por indexador (%):")
print(deb.groupby("Indexador")["Spread"].mean().round(2))