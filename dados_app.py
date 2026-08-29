"""
dados_app.py - Leituras de banco compartilhadas entre paginas, com
st.cache_data para nao reconsultar a cada troca de pagina. ultimo_valor
tambem vive aqui, pois opera sobre o DataFrame que este modulo carrega.
"""
import re

import pandas as pd
import streamlit as st

from db import engine

TTL_CACHE_SEGUNDOS = 300  # 5 minutos


@st.cache_data(ttl=TTL_CACHE_SEGUNDOS)
def carregar_indicadores():
    try:
        return pd.read_sql("SELECT * FROM indicadores_bcb", engine)
    except Exception:
        return pd.DataFrame(columns=["data", "valor", "indicador"])


@st.cache_data(ttl=TTL_CACHE_SEGUNDOS)
def carregar_dolar():
    try:
        return pd.read_sql("SELECT * FROM usd_brl ORDER BY date", engine)
    except Exception:
        return pd.DataFrame(columns=["date", "close"])


@st.cache_data(ttl=TTL_CACHE_SEGUNDOS)
def carregar_noticias():
    try:
        return pd.read_sql("SELECT titulo, link, data, categoria FROM noticias", engine)
    except Exception:
        return pd.DataFrame(columns=["titulo", "link", "data", "categoria"])


@st.cache_data(ttl=TTL_CACHE_SEGUNDOS)
def carregar_debentures():
    try:
        series = pd.read_sql("SELECT * FROM debentures_series", engine)
        ofertas = pd.read_sql(
            """
            SELECT numero_requerimento, nome_emissor, cnpj_emissor, emissao,
                  data_requerimento, data_encerramento, valor_total_registrado,
                  nome_lider, agente_fiduciario, titulo_incentivado
            FROM debentures
            """,
            engine,
        )
        deb = series.merge(ofertas, on="numero_requerimento", how="left")
        deb["link_sre"] = "https://web.cvm.gov.br/sre-publico-cvm/#/oferta-publica/" + deb["numero_requerimento"].astype(str)
        return deb
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=TTL_CACHE_SEGUNDOS)
def carregar_carteira():
    from carteira import ler_carteira

    try:
        return ler_carteira()
    except Exception:
        return pd.DataFrame(columns=["id", "ativo", "descricao", "direcao", "indexador", "tamanho"])


def invalidar_cache_carteira():
    """Chamar logo apos salvar a carteira, para a proxima leitura nao vir do cache antigo."""
    carregar_carteira.clear()


def normalizar_indicador(valor):
    if pd.isna(valor):
        return ""
    texto = str(valor).lower().strip()
    texto = re.sub(r"[^a-z0-9]", "", texto)
    return texto


def ultimo_valor(df_indicadores, nome):
    chave = normalizar_indicador(nome)
    serie = df_indicadores[df_indicadores["indicador"].map(normalizar_indicador) == chave]
    if serie.empty:
        return 0.0
    return float(serie["valor"].iloc[-1])


if __name__ == "__main__":
    df_ind = pd.DataFrame({
        "indicador": ["Selic", "Selic", "IGP-M"],
        "data": ["2026-01-01", "2026-01-02", "2026-01-01"],
        "valor": [10.0, 10.5, 0.3],
    })
    assert ultimo_valor(df_ind, "Selic") == 10.5
    assert ultimo_valor(df_ind, "IGP-M") == 0.3
    assert ultimo_valor(df_ind, "IPCA") == 0.0
    print("[OK] Caso 1: ultimo_valor encontra a ultima leitura por indicador normalizado.")

    assert normalizar_indicador("IGP-M") == "igpm"
    assert normalizar_indicador(None) == ""
    print("[OK] Caso 2: normalizar_indicador remove acentuacao/pontuacao e trata None.")

    print("\nTodos os casos passaram.")
