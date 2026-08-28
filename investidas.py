"""
investidas.py - Monitora fatos relevantes de empresas (Itausa e similares).

Fonte: CVM Dados Abertos - Formulário de Fatos Relevantes (IAN/FRE)
API: https://dados.cvm.gov.br/dados/ (via arquivo CSV)

Tabela: investidas
- id: PK auto-increment
- cnpj: CNPJ da empresa (ex: '17.197.092/0001-91' Itausa)
- nome_empresa: nome social
- fato_relevante: texto do fato/evento
- link_cvm: link para o documento na CVM
- data_fato: data do fato
- data_arquivamento: data de arquivamento na CVM
- data_coleta: quando foi coletado
"""

import pandas as pd
import requests
import io
from db import engine
from sqlalchemy import text


def criar_tabela_investidas():
    """Cria a tabela 'investidas' no banco se não existir."""
    criar_sql = """
    CREATE TABLE IF NOT EXISTS investidas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cnpj TEXT NOT NULL,
        nome_empresa TEXT,
        fato_relevante TEXT,
        link_cvm TEXT,
        data_fato DATE,
        data_arquivamento DATE,
        data_coleta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(cnpj, data_fato, fato_relevante)
    );
    """
    try:
        with engine.connect() as conn:
            conn.execute(text(criar_sql))
            conn.commit()
        print("[OK] Tabela 'investidas' criada ou ja existe.")
    except Exception as e:
        print(f"[ERRO] Falha ao criar tabela: {e}")


def buscar_fatos_cvm(cnpj_filtro=None):
    """
    Baixa fatos relevantes da CVM Dados Abertos.
    
    CNPJ da Itausa: 17.197.092/0001-91 (ou sem formatacao: 17197092000191)
    
    Nota: CVM usa arquivo CSV em:
    https://dados.cvm.gov.br/dados/COMPANHIA/FATO_RELEVANTE/
    
    Por enquanto, usaremos busca manual via lista de CNPJs de interesse.
    """
    print("[INFO] Funcao buscar_fatos_cvm em desenvolvimento...")
    print("       (Requer autenticacao ou acesso ao arquivo ZIP da CVM)")
    return []


def adicionar_empresa_interesse(cnpj, nome_empresa):
    """Adiciona empresa à lista de monitoramento (tabela de config, futura)."""
    print(f"[TODO] Adicionar empresa {nome_empresa} ({cnpj}) à lista de interesse.")


def filtrar_noticias_por_empresa(nome_empresa):
    """Retorna noticias que mencionam a empresa."""
    try:
        df = pd.read_sql(
            f"""
            SELECT titulo, link, data, categoria FROM noticias
            WHERE UPPER(titulo) LIKE UPPER('%{nome_empresa}%')
            OR UPPER(titulo) LIKE UPPER('%Itausa%')
            ORDER BY data DESC LIMIT 10
            """,
            engine
        )
        return df
    except Exception as e:
        print(f"[ERRO] Falha ao filtrar noticias: {e}")
        return pd.DataFrame()


def gerar_alerta_investidas(nome_empresa):
    """Gera texto de alerta se houver noticias ou fatos da empresa."""
    noticias = filtrar_noticias_por_empresa(nome_empresa)
    if noticias.empty:
        return None
    
    alerta = f"Noticias sobre {nome_empresa}:\n"
    for _, row in noticias.iterrows():
        alerta += f"  - {row['titulo']} ({row['categoria']}) — {row['data']}\n"
    return alerta


if __name__ == "__main__":
    criar_tabela_investidas()
    
    # Teste com Itausa
    print("\n=== Buscando noticias sobre Itausa ===")
    noticias = filtrar_noticias_por_empresa("Itausa")
    print(f"Encontradas {len(noticias)} noticias")
    if not noticias.empty:
        print(noticias.head())
    
    print("\n=== Alerta potencial ===")
    alerta = gerar_alerta_investidas("Itausa")
    if alerta:
        print(alerta)
    else:
        print("Sem noticias de Itausa no momento.")
