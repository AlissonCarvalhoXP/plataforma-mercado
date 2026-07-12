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

print("Pronto! Todos os dados foram atualizados.")