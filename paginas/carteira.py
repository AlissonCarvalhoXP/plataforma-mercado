"""
paginas/carteira.py - Pagina "Carteira": edicao da carteira do usuario.
"""
import pandas as pd
import streamlit as st

from dados_app import invalidar_cache_carteira


def pagina_carteira():
    st.subheader("Minha carteira")
    try:
        from carteira import gerar_contexto_carteira, ler_carteira, salvar_carteira

        df_carteira = ler_carteira()
        if df_carteira.empty:
            df_carteira = pd.DataFrame(
                [{
                    "ativo": "Ex: USD/BRL",
                    "descricao": "Posição de hedge",
                    "direcao": "long",
                    "indexador": "Dólar",
                    "tamanho": 50000.0,
                }]
            )

        cols = ["ativo", "descricao", "direcao", "indexador", "tamanho"]
        if not set(cols).issubset(df_carteira.columns):
            for col in cols:
                if col not in df_carteira.columns:
                    df_carteira[col] = ""

        df_editado = st.data_editor(
            df_carteira[cols],
            width="stretch",
            hide_index=True,
            key="carteira_editor",
            num_rows="dynamic",
        )

        if st.button("Salvar carteira"):
            ok = salvar_carteira(df_editado)
            if ok:
                invalidar_cache_carteira()
                st.success("Carteira atualizada com sucesso!")
                st.rerun()
            else:
                st.error("Não foi possível salvar a carteira.")

        st.markdown("**Resumo da carteira**")
        st.info(gerar_contexto_carteira())
    except Exception as exc:
        st.warning(f"Erro ao carregar carteira: {exc}")
