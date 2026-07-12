# enviar_briefing.py
import pandas as pd
from sqlalchemy import create_engine
from enviar_email import enviar_email

from db import engine

partes = ["=== BRIEFING DO DIA ===\n"]
try:
    partes.append(pd.read_sql("SELECT texto FROM briefing", engine)["texto"].iloc[0])
except Exception:
    partes.append("(briefing indisponivel)")

partes.append("\n\n=== DESTAQUES ===\n")
try:
    partes.append(pd.read_sql("SELECT texto FROM destaques", engine)["texto"].iloc[0])
except Exception:
    partes.append("(destaques indisponiveis)")

corpo = "\n".join(partes)
enviar_email("Briefing de mercado do dia", corpo)
print("Briefing enviado por e-mail!")