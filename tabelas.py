"""
tabelas.py - Configuracao de exibicao de tabelas (column_config nativo do
Streamlit) e destaque condicional, compartilhados entre paginas. Ao contrario
de componentes.py, este modulo IMPORTA streamlit - column_config so existe
la dentro.
"""
import pandas as pd
import streamlit as st

from tema import CORES


def progresso_prazo(data_emissao, data_vencimento, hoje=None):
    """Fracao (0 a 1, com clamp) do prazo da debenture ja decorrida. 0.0 se
    faltar data de emissao/vencimento - nunca lanca excecao por dado ruim."""
    if data_emissao is None or data_vencimento is None or pd.isna(data_emissao) or pd.isna(data_vencimento):
        return 0.0
    inicio = pd.to_datetime(data_emissao)
    fim = pd.to_datetime(data_vencimento)
    agora = pd.to_datetime(hoje) if hoje is not None else pd.Timestamp.now()
    duracao_total = (fim - inicio).total_seconds()
    if duracao_total <= 0:
        return 1.0
    decorrido = (agora - inicio).total_seconds()
    fracao = decorrido / duracao_total
    return max(0.0, min(1.0, fracao))


def _cor_fundo_spread(spread, media):
    """Cor de fundo (com transparencia, sufixo hex '33') para uma celula de
    spread comparada a media do seu indexador. "" se nao houver comparacao
    possivel (spread ou media ausentes)."""
    if pd.isna(spread) or pd.isna(media):
        return ""
    if spread < media:
        return f"background-color: {CORES['signal_pos']}33"
    if spread > media:
        return f"background-color: {CORES['signal_neg']}33"
    return ""


def destacar_spread(df):
    """Aplica _cor_fundo_spread na coluna spread, comparando cada linha a
    media do seu indexador. Devolve um pandas.Styler pronto para
    st.dataframe(destacar_spread(df), ...). Sem-op (Styler neutro) se as
    colunas 'spread'/'indexador' nao existirem."""
    if "spread" not in df.columns or "indexador" not in df.columns:
        return df.style

    medias = df.groupby("indexador")["spread"].transform("mean")
    indice_spread = df.columns.get_loc("spread")

    def _estilo_linha(row):
        estilos = [""] * len(df.columns)
        estilos[indice_spread] = _cor_fundo_spread(row["spread"], medias.loc[row.name])
        return estilos

    return df.style.apply(_estilo_linha, axis=1).format(na_rep="")


def _cor_fundo_sinal(sinal):
    """Cor de fundo (com transparencia) para uma celula de Sinal do ranking de
    opcoes. So COMPRAR_VOL ganha destaque - VENDER_VOL nao e' destaque
    negativo, e' so outra estrategia (mesma convencao de componentes.
    card_oportunidade, que usa 'accent', nao 'signal_neg', para venda de vol)."""
    if sinal == "COMPRAR_VOL":
        return f"background-color: {CORES['signal_pos']}33"
    return ""


def destacar_ranking_opcoes(df):
    """Aplica _cor_fundo_sinal na coluna Sinal do ranking de opcoes (celula a
    celula, nao a linha inteira - mesmo estilo de destacar_spread). Devolve um
    pandas.Styler pronto para st.dataframe(...). Sem-op (Styler neutro) se a
    coluna 'Sinal' nao existir."""
    if "Sinal" not in df.columns:
        return df.style

    indice_sinal = df.columns.get_loc("Sinal")

    def _estilo_linha(row):
        estilos = [""] * len(df.columns)
        estilos[indice_sinal] = _cor_fundo_sinal(row["Sinal"])
        return estilos

    return df.style.apply(_estilo_linha, axis=1)


def colunas_dolar():
    """column_config para a tabela de dolar (pagina Macro)."""
    return {
        "date": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "close": st.column_config.NumberColumn("Fechamento", format="R$ %.4f"),
    }


def colunas_debentures():
    """column_config para a tabela de debentures (pagina Macro). Colunas de
    texto puro (emissor, serie, indexador, rating, etc.) nao entram aqui -
    ficam com a renderizacao nativa, sem mudanca de comportamento."""
    return {
        "spread": st.column_config.NumberColumn("Spread (%)", format="%.2f%%"),
        "valor_serie": st.column_config.NumberColumn("Valor (R$ mi)", format="R$ %.2f"),
        "prazo_anos": st.column_config.NumberColumn("Prazo (anos)", format="%.2f"),
        "progresso_prazo": st.column_config.ProgressColumn("Prazo decorrido", min_value=0.0, max_value=1.0),
        "data_emissao": st.column_config.DateColumn("Emissão", format="DD/MM/YYYY"),
        "data_vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
        "data_encerramento": st.column_config.DateColumn("Encerramento", format="DD/MM/YYYY"),
        "link_sre": st.column_config.LinkColumn("Link SRE", display_text="Ver na CVM"),
    }


def colunas_carteira():
    """column_config para o data_editor da Carteira. Só `direcao` vira
    SelectboxColumn (valores reais confirmados: long/short, já validados por
    carteira.salvar_carteira()) - `indexador` fica texto livre (dado real tem
    valores fora do conjunto canônico documentado, ex.: "Ibov")."""
    return {
        "direcao": st.column_config.SelectboxColumn("Direção", options=["long", "short"], required=True),
        "tamanho": st.column_config.NumberColumn("Tamanho (R$)", format="R$ %.2f", min_value=0.0),
    }


if __name__ == "__main__":
    # Caso 1: progresso_prazo - prazo ainda nao iniciado
    assert progresso_prazo("2026-06-01", "2026-12-01", hoje="2026-01-01") == 0.0
    print("[OK] Caso 1: progresso_prazo antes da emissao -> 0.0.")

    # Caso 2: progresso_prazo - prazo ja vencido (clamp em 1.0)
    assert progresso_prazo("2026-01-01", "2026-06-01", hoje="2026-12-01") == 1.0
    print("[OK] Caso 2: progresso_prazo apos o vencimento -> 1.0 (clamp).")

    # Caso 3: progresso_prazo - no meio do prazo
    meio = progresso_prazo("2026-01-01", "2026-01-11", hoje="2026-01-06")
    assert round(meio, 2) == 0.50
    print("[OK] Caso 3: progresso_prazo no meio do prazo -> ~0.5.")

    # Caso 4: progresso_prazo - datas invalidas/faltando -> 0.0, sem excecao
    assert progresso_prazo(None, "2026-06-01") == 0.0
    assert progresso_prazo("2026-01-01", None) == 0.0
    print("[OK] Caso 4: progresso_prazo com data faltando -> 0.0, sem excecao.")

    # Caso 5: _cor_fundo_spread - abaixo/acima/igual a media
    assert _cor_fundo_spread(1.0, 2.0) == f"background-color: {CORES['signal_pos']}33"
    assert _cor_fundo_spread(3.0, 2.0) == f"background-color: {CORES['signal_neg']}33"
    assert _cor_fundo_spread(2.0, 2.0) == ""
    assert _cor_fundo_spread(float("nan"), 2.0) == ""
    print("[OK] Caso 5: _cor_fundo_spread compara contra a media corretamente.")

    # Caso 6: destacar_spread devolve um Styler utilizavel, sem excecao
    df_teste = pd.DataFrame({"indexador": ["CDI", "CDI", "IPCA"], "spread": [1.0, 3.0, 2.0]})
    styler = destacar_spread(df_teste)
    assert hasattr(styler, "to_html")
    styler.to_html()  # nao deve lancar excecao
    print("[OK] Caso 6: destacar_spread devolve um Styler valido.")

    # Caso 6b: _cor_fundo_sinal - so COMPRAR_VOL ganha destaque
    assert _cor_fundo_sinal("COMPRAR_VOL") == f"background-color: {CORES['signal_pos']}33"
    assert _cor_fundo_sinal("VENDER_VOL") == ""
    print("[OK] Caso 6b: _cor_fundo_sinal destaca so COMPRAR_VOL.")

    # Caso 6c: destacar_ranking_opcoes devolve um Styler utilizavel, sem excecao
    df_ranking_teste = pd.DataFrame({"Sinal": ["COMPRAR_VOL", "VENDER_VOL"], "Score": [5.0, -3.0]})
    styler_opcoes = destacar_ranking_opcoes(df_ranking_teste)
    assert hasattr(styler_opcoes, "to_html")
    styler_opcoes.to_html()
    print("[OK] Caso 6c: destacar_ranking_opcoes devolve um Styler valido.")

    # Caso 7: colunas_* devolvem dicts nao vazios de ColumnConfig
    assert len(colunas_dolar()) == 2
    assert len(colunas_debentures()) == 8
    assert len(colunas_carteira()) == 2
    print("[OK] Caso 7: colunas_dolar/colunas_debentures/colunas_carteira devolvem os dicts esperados.")

    print("\nTodos os casos passaram.")
