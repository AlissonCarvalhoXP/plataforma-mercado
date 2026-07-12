# coleta_noticias.py
import feedparser
import pandas as pd
from sqlalchemy import create_engine

# varios feeds de noticias economicas (nome -> url)
feeds = {
    "InfoMoney": "https://www.infomoney.com.br/feed/",
    "Money Times": "https://www.moneytimes.com.br/feed/",
}

noticias = []
for fonte, url in feeds.items():
    feed = feedparser.parse(url)
    for item in feed.entries:
        noticias.append({
            "titulo": item.get("title", ""),
            "link": item.get("link", ""),
            "data": item.get("published", ""),
            "fonte": fonte,
        })

df = pd.DataFrame(noticias)

# --- INCREMENTAL: so as novas ---
engine = create_engine("sqlite:///data/mercado.db")
try:
    existentes = pd.read_sql("SELECT link FROM noticias", engine)
    ja_temos = set(existentes["link"])
except Exception:
    ja_temos = set()

novas = df[~df["link"].isin(ja_temos)]
novas.to_sql("noticias", engine, if_exists="append", index=False)
print(f"{len(novas)} noticias novas adicionadas (de {len(df)} nos feeds).")