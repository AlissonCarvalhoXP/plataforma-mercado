# briefing.py
import pandas as pd
from sqlalchemy import create_engine
from analises import analisar_dolar, analisar_selic, analisar_debentures
from analise_ia import gerar_briefing

engine = create_engine("sqlite:///data/mercado.db")

# 1) montar o contexto (indicadores + noticias de mercado)
contexto = "\n".join([
    analisar_dolar(),
    analisar_selic(),
    analisar_debentures(),
])

noticias = pd.read_sql(
    "SELECT titulo FROM noticias WHERE categoria NOT IN ('Outros', '')",
    engine,
)
if not noticias.empty:
    contexto += "\nManchetes de mercado: " + "; ".join(noticias["titulo"].head(8))

# 2) a IA escreve o briefing
briefing = gerar_briefing(contexto)
print(briefing)

# 3) guardar no banco
pd.DataFrame([{"texto": briefing}]).to_sql("briefing", engine, if_exists="replace", index=False)
print("\nBriefing salvo no banco.")