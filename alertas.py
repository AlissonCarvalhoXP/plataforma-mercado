# alertas.py
import pandas as pd
from enviar_email import enviar_email

from db import engine

# limites de alerta do dolar
TETO = 5.10   # alerta se passar disso
PISO = 5.00   # alerta se cair abaixo disso

dolar = pd.read_sql("SELECT close FROM usd_brl ORDER BY date", engine)
atual = dolar["close"].iloc[-1]

alertas = []
if atual > TETO:
    alertas.append(f"Dolar ROMPEU o teto: R$ {atual:.2f} (acima de R$ {TETO:.2f})")
elif atual < PISO:
    alertas.append(f"Dolar caiu abaixo do piso: R$ {atual:.2f} (abaixo de R$ {PISO:.2f})")

# Alerta de Investidas: noticias sobre empresas de interesse
try:
    from investidas import gerar_alerta_investidas
    alerta_itausa = gerar_alerta_investidas("Itausa")
    if alerta_itausa:
        alertas.append(f"\n{alerta_itausa}")
except Exception:
    pass

if alertas:
    corpo = "\n".join(alertas)
    enviar_email("⚠️ ALERTA de mercado", corpo)
    print("Alerta enviado:", corpo)
else:
    print(f"Sem alertas. Dolar em R$ {atual:.2f} (entre {PISO:.2f} e {TETO:.2f}).")