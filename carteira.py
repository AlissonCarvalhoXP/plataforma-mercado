"""
carteira.py - Gerencia a carteira de investimentos do usuário.

Tabela: carteira
- id: PK auto-increment
- ativo: ticker ou nome (ex: 'BRL=X', 'Itaúsa', 'Tesouro IPCA 2035')
- descricao: descrição libre (ex: 'USD/BRL', 'Ação ordinária', 'Título público indexado')
- direcao: 'long' ou 'short'
- indexador: 'CDI', 'Prefixado', 'IPCA', 'Dólar', 'Bolsa', 'N/A'
- tamanho: valor em R$ (ex: 50000.0)
- data_criacao: timestamp
- ativa: bool (1/0) para soft delete ou inativação
"""

import pandas as pd
from db import engine
from sqlalchemy import create_engine, inspect, text


def criar_tabela_carteira():
    """Cria a tabela 'carteira' no banco se não existir."""
    criar_sql = """
    CREATE TABLE IF NOT EXISTS carteira (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ativo TEXT NOT NULL,
        descricao TEXT,
        direcao TEXT NOT NULL CHECK(direcao IN ('long', 'short')),
        indexador TEXT DEFAULT 'N/A',
        tamanho REAL NOT NULL DEFAULT 0.0,
        data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ativa BOOLEAN DEFAULT 1
    );
    """
    try:
        with engine.connect() as conn:
            conn.execute(text(criar_sql))
            conn.commit()
        print("[OK] Tabela 'carteira' criada ou já existe.")
    except Exception as e:
        print(f"[ERRO] Falha ao criar tabela: {e}")


def ler_carteira():
    """Lê toda a carteira ativa do banco."""
    try:
        df = pd.read_sql(
            "SELECT id, ativo, descricao, direcao, indexador, tamanho FROM carteira WHERE ativa = 1 ORDER BY id",
            engine
        )
        return df
    except Exception as e:
        print(f"[ERRO] Falha ao ler carteira: {e}")
        return pd.DataFrame()


def salvar_carteira(df):
    """
    Sobrescreve a carteira com dados novos (via st.data_editor).
    
    Assumo que df vem do st.data_editor sem a coluna 'id'.
    Estratégia: delete all active, insert novos.
    """
    try:
        # Delete todas as linhas ativas
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM carteira WHERE ativa = 1"))
            conn.commit()
        
        # Insert novos
        if not df.empty:
            df_clean = df[['ativo', 'descricao', 'direcao', 'indexador', 'tamanho']].copy()
            df_clean['ativa'] = 1
            df_clean.to_sql('carteira', engine, if_exists='append', index=False)
        
        print(f"[OK] Carteira salva: {len(df)} posicoes.")
        return True
    except Exception as e:
        print(f"[ERRO] Falha ao salvar carteira: {e}")
        return False


def gerar_contexto_carteira():
    """
    Formata a carteira como texto para injetar no contexto da IA.
    Retorna string descritiva da carteira.
    """
    df = ler_carteira()
    if df.empty:
        return "Carteira vazia."
    
    contexto = "Carteira do usuario:\n"
    total = df['tamanho'].sum()
    
    for _, row in df.iterrows():
        pct = (row['tamanho'] / total * 100) if total > 0 else 0
        contexto += f"  - {row['ativo']} ({row['direcao']}, {row['indexador']}): R$ {row['tamanho']:,.2f} ({pct:.1f}%)\n"
    
    contexto += f"\nTotal investido: R$ {total:,.2f}"
    return contexto


if __name__ == "__main__":
    criar_tabela_carteira()
    print(gerar_contexto_carteira())
