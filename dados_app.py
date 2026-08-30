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


def calcular_delta_indicador(df_indicadores, nome):
    """Delta = ultima leitura - leitura imediatamente anterior DISTINTA, para
    o indicador `nome`. None se houver menos de 2 leituras distintas (nunca
    inventa um delta). Mesma regra de exposicao._calcular_deltas, generalizada
    para qualquer indicador (usada pelos KPIs da pagina Macro)."""
    if df_indicadores is None or df_indicadores.empty:
        return None
    chave = normalizar_indicador(nome)
    serie = (
        df_indicadores[df_indicadores["indicador"].map(normalizar_indicador) == chave]
        .sort_values("data")
        .drop_duplicates(subset="data", keep="last")
    )
    if len(serie) < 2:
        return None
    valores = serie["valor"].tolist()
    return valores[-1] - valores[-2]


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

    df_selic_2_leituras = pd.DataFrame({
        "indicador": ["Selic", "Selic"],
        "data": pd.to_datetime(["2026-08-01", "2026-08-15"]),
        "valor": [10.50, 10.75],
    })
    assert calcular_delta_indicador(df_selic_2_leituras, "Selic") == 0.25 or round(calcular_delta_indicador(df_selic_2_leituras, "Selic"), 2) == 0.25
    print("[OK] Caso 3: calcular_delta_indicador acha a ultima leitura vs. a anterior.")

    df_uma_leitura = pd.DataFrame({
        "indicador": ["IPCA"],
        "data": pd.to_datetime(["2026-08-01"]),
        "valor": [0.30],
    })
    assert calcular_delta_indicador(df_uma_leitura, "IPCA") is None
    assert calcular_delta_indicador(df_ind, "Selic") is not None  # df_ind (Caso 1) tem 2 leituras de Selic
    print("[OK] Caso 4: calcular_delta_indicador devolve None com menos de 2 leituras.")

    df_com_duplicata = pd.DataFrame({
        "indicador": ["Selic", "Selic", "Selic"],
        "data": pd.to_datetime(["2026-08-01", "2026-08-15", "2026-08-15"]),
        "valor": [10.50, 10.75, 10.75],
    })
    delta_dup = calcular_delta_indicador(df_com_duplicata, "Selic")
    assert round(delta_dup, 2) == 0.25  # 10.75 (15/08) - 10.50 (01/08), nao 10.75 - 10.75
    print("[OK] Caso 5: linha duplicada na ultima data nao zera o delta (dedup por data aplicado).")

    print("\nTodos os casos passaram.")
