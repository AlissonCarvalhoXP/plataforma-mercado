"""
paginas/noticias.py - Pagina "Noticias": lista de manchetes classificadas.
"""
import streamlit as st

from dados_app import carregar_noticias


def pagina_noticias():
    st.subheader("Notícias do mercado")
    noticias = carregar_noticias()
    if noticias.empty:
        st.info("Nenhuma notícia disponível no momento.")
    else:
        for _, n in noticias.head(20).iterrows():
            st.markdown(f"`{n['categoria']}` **[{n['titulo']}]({n['link']})** — _{n['data']}_")
