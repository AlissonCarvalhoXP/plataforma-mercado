# app.py
import pandas as pd
import streamlit as st

from dados_app import carregar_debentures, carregar_dolar, carregar_indicadores, carregar_noticias, ultimo_valor
from db import engine
from paginas.carteira import pagina_carteira
from paginas.investidas import pagina_investidas
from paginas.macro import pagina_macro
from paginas.noticias import pagina_noticias
from paginas.opcoes import pagina_opcoes
from paginas.relatorios import pagina_relatorios
from paginas.resumo import pagina_resumo
from tema import aplicar_tema

st.set_page_config(
    page_title="Market Intelligence Hub",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

aplicar_tema()

st.markdown(
    """
    <div class="topbar">
        <h1>Market Intelligence Hub</h1>
        <p>Radar macro, debêntures, notícias e carteira em uma interface operacional.</p>
        <div class="status-pill">Sistema ativo • monitoramento em tempo real</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    if st.button("🤖 Assistente IA", width="stretch"):
        st.session_state["ia_open"] = True

pg = st.navigation([
    st.Page(pagina_resumo, title="Resumo", icon="📊"),
    st.Page(pagina_macro, title="Macro", icon="📈"),
    st.Page(pagina_noticias, title="Notícias", icon="📰"),
    st.Page(pagina_investidas, title="Investidas", icon="🏢"),
    st.Page(pagina_carteira, title="Carteira", icon="💼"),
    st.Page(pagina_relatorios, title="Relatórios", icon="📥"),
    st.Page(pagina_opcoes, title="Opções", icon="🧮"),
])
pg.run()

# Assistente de IA - persistente, renderizado fora de qualquer pagina
prompt_ia = st.chat_input("Pergunte à plataforma sobre mercado, taxas e renda fixa...")
if prompt_ia:
    try:
        from analise_ia import responder_pergunta
        from carteira import gerar_contexto_carteira

        ind = carregar_indicadores()
        dolar = carregar_dolar()
        deb = carregar_debentures()
        noticias = carregar_noticias()
        mercado = noticias[~noticias["categoria"].isin(["Outros", ""])].copy()

        contexto = (
            f"Indicadores: Selic {round(ultimo_valor(ind, 'Selic'), 2)}% a.a., "
            f"IPCA {round(ultimo_valor(ind, 'IPCA'), 2)}% (mes), IGP-M {round(ultimo_valor(ind, 'IGP-M'), 2)}% (mes).\n"
            f"Dolar USD/BRL atual: R$ {float(dolar['close'].iloc[-1]) if not dolar.empty else 0:.2f}.\n"
            f"Debentures: {len(deb)} series.\n"
        )
        if not deb.empty:
            contexto += f"Por indexador: {deb['indexador'].value_counts().to_dict()}\n"
        try:
            contexto += "\nCarteira: " + gerar_contexto_carteira() + "\n"
        except Exception:
            pass
        try:
            briefing = pd.read_sql("SELECT texto FROM briefing", engine)
            if not briefing.empty:
                contexto += "\nBriefing: " + briefing["texto"].iloc[0] + "\n"
        except Exception:
            pass
        if not mercado.empty:
            contexto += "\nManchetes: " + "; ".join(mercado["titulo"].head(10).tolist())

        with st.spinner("Pensando..."):
            st.write(responder_pergunta(prompt_ia, contexto))
    except Exception as exc:
        st.warning(f"Erro ao responder pergunta: {exc}")
