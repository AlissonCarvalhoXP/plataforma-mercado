# classificar_noticias.py
import pandas as pd
from sqlalchemy import create_engine
from analise_ia import classificar_noticia

engine = create_engine("sqlite:///data/mercado.db")
noticias = pd.read_sql("SELECT * FROM noticias", engine)

# cria a coluna 'categoria' se ainda nao existir
if "categoria" not in noticias.columns:
    noticias["categoria"] = ""

# classifica so as que ainda nao tem categoria
for i, linha in noticias.iterrows():
    if not linha["categoria"]:
        try:
            categoria = classificar_noticia(linha["titulo"])
        except Exception:
            categoria = ""   # falhou (ex.: limite) -> tenta na proxima vez
        noticias.at[i, "categoria"] = categoria
        print(f"[{categoria}] {linha['titulo'][:60]}")

# salva de volta
noticias.to_sql("noticias", engine, if_exists="replace", index=False)
print("Classificacao concluida!")