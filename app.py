# app.py
import streamlit as st
import pandas as pd
from db import engine

st.title("Market Intelligence Hub")
st.write("Acompanhamento de indicadores de mercado.")

# --- BRIEFING DO DIA (IA) ---
st.subheader("🤖 Briefing do dia")
try:
    b = pd.read_sql("SELECT texto FROM briefing", engine)
    st.info(b["texto"].iloc[0])
except Exception:
    st.write("Rode o briefing.py para gerar o comentário do dia.")

# --- DESTAQUES DO DIA (IA) ---
try:
    d = pd.read_sql("SELECT texto FROM destaques", engine)
    st.markdown("**⚡ Destaques do dia**")
    st.markdown(d["texto"].iloc[0])
except Exception:
    pass

# --- INDICADORES MACRO ---
ind = pd.read_sql("SELECT * FROM indicadores_bcb", engine)


def ultimo_valor(nome):
    return ind[ind["indicador"] == nome]["valor"].iloc[-1]


st.subheader("Indicadores macro (Banco Central)")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Selic (% a.a.)", round(ultimo_valor("Selic"), 2))
c2.metric("CDI (% a.d.)", round(ultimo_valor("CDI"), 4))
c3.metric("IPCA (% mes)", round(ultimo_valor("IPCA"), 2))
c4.metric("IGP-M (% mes)", round(ultimo_valor("IGP-M"), 2))

# --- DOLAR ---
dolar = pd.read_sql("SELECT * FROM usd_brl ORDER BY date", engine)
st.subheader("Dólar (USD/BRL) — fechamento diario")
st.line_chart(dolar, x="date", y="close")
st.dataframe(dolar)

# --- DEBENTURES (novas emissoes CVM) ---
st.subheader("Debêntures — novas emissões (CVM)")
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

d1, d2 = st.columns(2)
d1.metric("Séries coletadas", len(deb))
d2.metric("Volume total (R$ bi)", round(deb["valor_serie"].sum() / 1e9, 2))

st.write("**Emissões por indexador**")
st.bar_chart(deb["indexador"].value_counts())

st.write("**Detalhe das séries**")
st.dataframe(deb[[
    "nome_emissor", "serie", "indexador", "spread", "valor_serie", "prazo_anos",
    "data_emissao", "data_vencimento", "rating", "titulo_incentivado",
    "nome_lider", "agente_fiduciario", "data_encerramento", "link_sre",
]])

# --- NOTICIAS ---
st.subheader("Notícias de mercado")
noticias = pd.read_sql("SELECT titulo, link, data, categoria FROM noticias", engine)
mercado = noticias[~noticias["categoria"].isin(["Outros", ""])]
if mercado.empty:
    st.write("Nenhuma notícia de mercado classificada ainda.")
else:
    for _, n in mercado.head(15).iterrows():
        st.markdown(f"`{n['categoria']}` **[{n['titulo']}]({n['link']})** — _{n['data']}_")

# --- INVESTIDAS (ITAUSA E SIMILARES) ---
st.subheader("🏢 Investidas (empresas de interesse)")
try:
    from investidas import filtrar_noticias_por_empresa, criar_tabela_investidas
    
    criar_tabela_investidas()
    
    # Por enquanto, monitorar Itausa (exemplo)
    empresas_interesse = {
        "Itausa": "17.197.092/0001-91"
    }
    
    for nome_empresa, cnpj in empresas_interesse.items():
        noticias_empresa = filtrar_noticias_por_empresa(nome_empresa)
        if not noticias_empresa.empty:
            with st.expander(f"📰 {nome_empresa} ({len(noticias_empresa)} noticias)"):
                for _, n in noticias_empresa.iterrows():
                    st.markdown(f"`{n['categoria']}` **[{n['titulo']}]({n['link']})** — _{n['data']}_")
        else:
            st.info(f"Sem noticias de {nome_empresa} no momento.")
            
except Exception as e:
    st.warning(f"Erro ao carregar Investidas: {e}")

# --- CARTEIRA DO USUARIO (PORTFOLIO INTELLIGENCE V1) ---
st.subheader("💼 Minha Carteira")
try:
    from carteira import ler_carteira, salvar_carteira, gerar_contexto_carteira
    
    df_carteira = ler_carteira()
    
    # Edição inline com st.data_editor
    st.write("**Edite suas posicoes abaixo:**")
    df_editado = st.data_editor(
        df_carteira[['ativo', 'descricao', 'direcao', 'indexador', 'tamanho']],
        use_container_width=True,
        hide_index=True,
        key="carteira_editor"
    )
    
    # Salvar mudancas
    if st.button("Salvar Carteira"):
        if salvar_carteira(df_editado):
            st.success("Carteira atualizada!")
            st.rerun()
    
    # Exibir contexto formatado
    st.markdown("**Resumo da carteira:**")
    st.info(gerar_contexto_carteira())
    
except Exception as e:
    st.warning(f"Erro ao carregar carteira: {e}")

# --- PERGUNTE A PLATAFORMA (IA) ---
st.subheader("💬 Pergunte à plataforma")
pergunta = st.text_input("Ex.: por que o real está forte? qual a taxa média das emissões?")
if pergunta:
    from analise_ia import responder_pergunta
    from carteira import gerar_contexto_carteira
    
    contexto = f"""Indicadores: Selic {round(ultimo_valor('Selic'), 2)}% a.a., IPCA {round(ultimo_valor('IPCA'), 2)}% (mes), IGP-M {round(ultimo_valor('IGP-M'), 2)}% (mes).
Dolar USD/BRL atual: R$ {dolar['close'].iloc[-1]:.2f}.
Debentures: {len(deb)} series. Por indexador: {deb['indexador'].value_counts().to_dict()}.
Emissores de debentures na base: {'; '.join(deb['nome_emissor'].dropna().unique())}.
"""
    spread_medio = deb.groupby("indexador")["spread"].mean().round(2).to_dict()
    contexto += f"\nSpread medio das debentures por indexador (% a.a.): {spread_medio}"
    
    # Injetar contexto da carteira
    try:
        contexto += "\n\n" + gerar_contexto_carteira()
    except Exception:
        pass
    
    try:
        contexto += "\nBriefing: " + pd.read_sql("SELECT texto FROM briefing", engine)["texto"].iloc[0]
    except Exception:
        pass
    if not mercado.empty:
        contexto += "\nManchetes: " + "; ".join(mercado["titulo"].head(10))
    with st.spinner("Pensando..."):
        st.write(responder_pergunta(pergunta, contexto))