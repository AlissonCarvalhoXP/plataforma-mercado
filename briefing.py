# briefing.py
import pandas as pd
from sqlalchemy import create_engine
from analises import analisar_dolar, analisar_selic, analisar_debentures
from analise_ia import gerar_briefing, gerar_destaques

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

# 3) so salva se DEU CERTO (nao sobrescreve o bom com uma falha)
if briefing:
    print(briefing)
    pd.DataFrame([{"texto": briefing}]).to_sql("briefing", engine, if_exists="replace", index=False)
    print("\nBriefing salvo no banco.")
else:
    print("Briefing nao gerado agora (servidor ocupado). O anterior foi mantido.")

# 4) Destaques do dia (reutiliza o mesmo contexto)
destaques = gerar_destaques(contexto)
if destaques:
    pd.DataFrame([{"texto": destaques}]).to_sql("destaques", engine, if_exists="replace", index=False)
    print("\nDestaques:")
    print(destaques)
else:
    print("Destaques nao gerados agora (servidor ocupado).")