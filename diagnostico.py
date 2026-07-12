# diagnostico.py
import pandas as pd
from sqlalchemy import create_engine

engine = create_engine("sqlite:///data/mercado.db")
df = pd.read_sql(
    "SELECT Remuneracao FROM debentures_series WHERE Indexador = 'Outro' LIMIT 5",
    engine,
)
for texto in df["Remuneracao"]:
    print((texto or "")[:250])
    print("-" * 60)