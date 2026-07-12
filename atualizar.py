# atualizar.py
import subprocess
import sys

print("Atualizando dolar (USD/BRL)...")
subprocess.run([sys.executable, "coleta.py"])

print("Atualizando indicadores do BCB...")
subprocess.run([sys.executable, "coleta_bcb.py"])

print("Pronto! Todos os dados foram atualizados.")