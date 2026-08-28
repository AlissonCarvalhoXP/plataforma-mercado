# app.py
import streamlit as st
import pandas as pd
from datetime import datetime
from db import engine
from modules.opcoes.view_opcoes import render_aba_opcoes


# Configurar tema e layout
st.set_page_config(
    page_title="Market Intelligence Hub",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS customizado
st.markdown("""
<style>
    /* Tema de cores */
    :root {
        --primary-color: #1e3c72;
        --secondary-color: #2a5298;
    }
    
    /* Header */
    .main-title {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        color: white;
        padding: 20px;
        border-radius: 8px;
        text-align: center;
        margin-bottom: 20px;
    }
    
    /* Métrica destaque */
    .metric-card {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        padding: 15px;
        border-radius: 8px;
        text-align: center;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title"><h1>📊 Market Intelligence Hub</h1><p>Suporte à Decisão em Tesouraria e Global Markets</p></div>', unsafe_allow_html=True)

# Função auxiliar: formatar data para BR
def formatar_data_br(data):
    if pd.isna(data):
        return ""
    if isinstance(data, str):
        data = pd.to_datetime(data)
    return data.strftime("%d/%m/%Y")

# Função auxiliar: formatar moeda
def formatar_moeda(valor):
    if pd.isna(valor):
        return ""
    return f"R$ {valor:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")

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

# Formatar dados para exibição
dolar_display = dolar.copy()
dolar_display["date"] = dolar_display["date"].apply(formatar_data_br)
dolar_display["close"] = dolar_display["close"].apply(lambda x: f"R$ {x:.4f}")
st.dataframe(dolar_display, use_container_width=True, hide_index=True)

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
deb_display = deb[[
    "nome_emissor", "serie", "indexador", "spread", "valor_serie", "prazo_anos",
    "data_emissao", "data_vencimento", "rating", "titulo_incentivado",
    "nome_lider", "agente_fiduciario", "data_encerramento", "link_sre",
]].copy()

# Formatar datas
deb_display["data_emissao"] = deb_display["data_emissao"].apply(formatar_data_br)
deb_display["data_vencimento"] = deb_display["data_vencimento"].apply(formatar_data_br)
deb_display["data_encerramento"] = deb_display["data_encerramento"].apply(formatar_data_br)

# Formatar valores
deb_display["valor_serie"] = deb_display["valor_serie"].apply(lambda x: formatar_moeda(x/1e6) if pd.notna(x) else "")
deb_display["spread"] = deb_display["spread"].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "")

st.dataframe(deb_display, use_container_width=True, hide_index=True)

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

# --- RELATORIOS & DOWNLOADS ---
st.subheader("📥 Download de Relatórios")
try:
    from relatorios import gerar_relatorio_debentures, gerar_relatorio_indicadores, gerar_relatorio_dolar
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📊 Relatório Debentures", use_container_width=True):
            try:
                caminho = gerar_relatorio_debentures()
                with open(caminho, "rb") as f:
                    st.download_button(
                        label="⬇️ Baixar Debentures.xlsx",
                        data=f.read(),
                        file_name="relatorio_debentures.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                st.success("✅ Relatório gerado!")
            except Exception as e:
                st.error(f"Erro ao gerar relatório: {e}")
    
    with col2:
        if st.button("📈 Relatório Indicadores", use_container_width=True):
            try:
                caminho = gerar_relatorio_indicadores()
                with open(caminho, "rb") as f:
                    st.download_button(
                        label="⬇️ Baixar Indicadores.xlsx",
                        data=f.read(),
                        file_name="relatorio_indicadores.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                st.success("✅ Relatório gerado!")
            except Exception as e:
                st.error(f"Erro ao gerar relatório: {e}")
    
    with col3:
        if st.button("💵 Relatório Dólar", use_container_width=True):
            try:
                caminho = gerar_relatorio_dolar()
                with open(caminho, "rb") as f:
                    st.download_button(
                        label="⬇️ Baixar Dolar.xlsx",
                        data=f.read(),
                        file_name="relatorio_dolar.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                st.success("✅ Relatório gerado!")
            except Exception as e:
                st.error(f"Erro ao gerar relatório: {e}")
    
    # Opção de gerar todos
    if st.button("🎯 Gerar Todos os Relatórios", use_container_width=True):
        try:
            from relatorios import exportar_todos_relatorios
            arquivos = exportar_todos_relatorios()
            st.success(f"✅ {len(arquivos)} relatórios gerados com sucesso!")
            for arquivo in arquivos:
                st.info(f"📄 {arquivo}")
        except Exception as e:
            st.error(f"Erro ao gerar relatórios: {e}")

except Exception as e:
    st.warning(f"Erro ao carregar relatórios: {e}")

# --- EMAIL BRIEFING ---
st.subheader("📧 Enviar Briefing por Email")
try:
    from email_html import enviar_email_html
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        email_destino = st.text_input("Email destino:", placeholder="seu-email@empresa.com")
    
    with col2:
        if st.button("📤 Enviar Briefing", use_container_width=True):
            if email_destino:
                try:
                    with st.spinner("Enviando email..."):
                        # Coletar dados para email
                        from coleta import ultimo_valor
                        
                        dados = {
                            "selic": round(ultimo_valor("Selic"), 2),
                            "ipca": round(ultimo_valor("IPCA"), 2),
                            "igp_m": round(ultimo_valor("IGP-M"), 2),
                            "dolar": dolar["close"].iloc[-1] if not dolar.empty else 0,
                            "data": formatar_data_br(pd.Timestamp.now())
                        }
                        
                        success = enviar_email_html(email_destino, dados)
                        if success:
                            st.success("✅ Email enviado com sucesso!")
                        else:
                            st.error("❌ Falha ao enviar email. Verifique configurações .env")
                except Exception as e:
                    st.error(f"Erro: {e}")
            else:
                st.warning("Por favor, digite um email válido.")

except Exception as e:
    st.info(f"📧 Email não configurado: {e}")

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
        
# --- OPÇÕES B3 ---
render_aba_opcoes(selic=ultimo_valor("Selic") / 100)
