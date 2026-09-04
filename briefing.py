# briefing.py
import pandas as pd
from sqlalchemy import create_engine
from analises import analisar_dolar, analisar_selic, analisar_debentures
from analise_ia import gerar_briefing, gerar_destaques

from db import engine

# 1) montar o contexto (indicadores + noticias + CARTEIRA)
contexto = "\n".join([
    analisar_dolar(),
    analisar_selic(),
    analisar_debentures(),
])

# Injetar contexto da carteira do usuario
try:
    from carteira import gerar_contexto_carteira
    contexto += "\n\n" + gerar_contexto_carteira()
except Exception:
    pass

# Injetar sinais de exposicao (carteira x indicadores macro)
try:
    from exposicao import gerar_sinais_exposicao
    from carteira import ler_carteira

    indicadores_df = pd.read_sql("SELECT * FROM indicadores_bcb", engine)
    dolar_df = pd.read_sql("SELECT * FROM usd_brl ORDER BY date", engine)
    carteira_df = ler_carteira()

    sinais = gerar_sinais_exposicao(carteira_df, indicadores_df, dolar_df)
    sinais_relevantes = [s for s in sinais if s["sentido_impacto"] != "neutro"]
    if sinais_relevantes:
        contexto += "\n\nSinais de exposição da carteira:\n" + "\n".join(f"- {s['texto']}" for s in sinais_relevantes)
except Exception:
    pass

noticias = pd.read_sql(
    "SELECT titulo FROM noticias WHERE categoria NOT IN ('Outros', '')",
    engine,
)
if not noticias.empty:
    contexto += "\nManchetes de mercado: " + "; ".join(noticias["titulo"].head(8))

# 2) a IA escreve o briefing
def _agora():
    """Data/hora da geracao. Sem isto a tela exibe texto antigo como se fosse
    de agora - e quando a cota da API de IA estoura, o briefing congela sem
    ninguem perceber."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M")


briefing = gerar_briefing(contexto)

# 3) so salva se DEU CERTO (nao sobrescreve o bom com uma falha)
if briefing:
    print(briefing)
    pd.DataFrame([{"texto": briefing, "gerado_em": _agora()}]).to_sql("briefing", engine, if_exists="replace", index=False)
    print("\nBriefing salvo no banco.")
else:
    print("Briefing nao gerado agora (servidor ocupado). O anterior foi mantido.")

# 4) Destaques do dia (reutiliza o mesmo contexto)
destaques = gerar_destaques(contexto)
if destaques:
    pd.DataFrame([{"texto": destaques, "gerado_em": _agora()}]).to_sql("destaques", engine, if_exists="replace", index=False)
    print("\nDestaques:")
    print(destaques)
else:
    print("Destaques nao gerados agora (servidor ocupado).")