#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de teste para validar integração de Relatórios & Email no app.py
"""

import os
import sys
from pathlib import Path

print("\n=== TESTE DE INTEGRACAO: RELATORIOS & EMAIL ===\n")

# 1. Testar imports
print("[1] Validando imports...")
try:
    from relatorios import (
        gerar_relatorio_debentures,
        gerar_relatorio_indicadores,
        gerar_relatorio_dolar,
        exportar_todos_relatorios
    )
    print("   OK: relatorios.py importado")
except Exception as e:
    print(f"   ERRO: {e}")
    sys.exit(1)

try:
    from email_html import enviar_email_html, formatar_dados_metricas
    print("   OK: email_html.py importado")
except Exception as e:
    print(f"   ERRO: {e}")
    sys.exit(1)

try:
    from carteira import ler_carteira, gerar_contexto_carteira
    print("   OK: carteira.py importado")
except Exception as e:
    print(f"   ERRO: {e}")
    sys.exit(1)

try:
    from investidas import filtrar_noticias_por_empresa
    print("   OK: investidas.py importado")
except Exception as e:
    print(f"   ERRO: {e}")
    sys.exit(1)

# 2. Testar banco de dados
print("\n[2] Validando banco de dados...")
try:
    from db import engine
    from sqlalchemy import text
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).fetchone()
    print("   OK: Conexao com banco de dados OK")
except Exception as e:
    print(f"   ERRO: {e}")
    sys.exit(1)

# 3. Testar geração de relatórios
print("\n[3] Testando geracao de relatorios...")
try:
    arquivos = exportar_todos_relatorios()
    for arq in arquivos:
        if Path(arq).exists():
            tamanho = Path(arq).stat().st_size / 1024
            print(f"   OK: {Path(arq).name} ({tamanho:.1f} KB)")
        else:
            print(f"   ERRO: {arq} nao foi criado")
            sys.exit(1)
except Exception as e:
    print(f"   ERRO: {e}")
    sys.exit(1)

# 4. Testar dados de carteira
print("\n[4] Testando carteira...")
try:
    df = ler_carteira()
    print(f"   OK: Carteira carregada ({len(df)} posicoes)")
    contexto = gerar_contexto_carteira()
    print(f"   OK: Contexto gerado ({len(contexto)} caracteres)")
except Exception as e:
    print(f"   ERRO: {e}")

# 5. Testar dados de investidas
print("\n[5] Testando investidas...")
try:
    noticias = filtrar_noticias_por_empresa("Itausa")
    print(f"   OK: Noticias filtradas ({len(noticias)} resultados)")
except Exception as e:
    print(f"   ERRO: {e}")

# 6. Testar formatação de dados para email
print("\n[6] Testando formatacao de dados...")
try:
    from db import engine
    import pandas as pd
    
    ind = pd.read_sql("SELECT * FROM indicadores_bcb", engine)
    def ultimo_valor(nome):
        return ind[ind["indicador"] == nome]["valor"].iloc[-1]
    
    dolar = pd.read_sql("SELECT * FROM usd_brl ORDER BY date DESC LIMIT 1", engine)
    dados = {
        "selic": round(ultimo_valor("Selic"), 2),
        "ipca": round(ultimo_valor("IPCA"), 2),
        "igp_m": round(ultimo_valor("IGP-M"), 2),
        "dolar": dolar["close"].iloc[0] if not dolar.empty else 0,
        "data": "01/01/2025"
    }
    
    from email_html import formatar_dados_metricas
    html = formatar_dados_metricas(dados)
    print(f"   OK: HTML formatado ({len(html)} caracteres)")
    
    if "Selic" in html and "Dolar" in html:
        print("   OK: Conteudo esperado presente no HTML")
    else:
        print("   ERRO: Conteudo esperado NAO encontrado")
        
except Exception as e:
    print(f"   ERRO: {e}")

print("\n[SUCCESS] TESTES COMPLETADOS!\n")
print("Proximos passos:")
print("  1. Execute: streamlit run app.py")
print("  2. Teste os botoes de Download de Relatorios")
print("  3. Configure .env com EMAIL_USER e EMAIL_SENHA")
print("  4. Execute: python atualizar.py\n")

