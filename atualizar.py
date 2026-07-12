# atualizar.py
import subprocess
import sys

print("Atualizando dolar (USD/BRL)...")
subprocess.run([sys.executable, "coleta.py"])

print("Atualizando indicadores do BCB...")
subprocess.run([sys.executable, "coleta_bcb.py"])

print("Atualizando lista de debentures (CVM)...")
subprocess.run([sys.executable, "coleta_debentures.py"])

print("Enriquecendo novas debentures...")
subprocess.run([sys.executable, "enriquecer_debentures.py"])

print("Coletando noticias...")
subprocess.run([sys.executable, "coleta_noticias.py"])

print("Classificando noticias com IA...")
subprocess.run([sys.executable, "classificar_noticias.py"])

print("Gerando briefing do dia...")
subprocess.run([sys.executable, "briefing.py"])

print("Enviando briefing por e-mail...")
subprocess.run([sys.executable, "enviar_briefing.py"])

print("Verificando alertas...")
subprocess.run([sys.executable, "alertas.py"])

print("Pronto! Todos os dados foram atualizados.")