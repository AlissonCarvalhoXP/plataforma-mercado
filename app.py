# app.py
import io
import re

import pandas as pd
import streamlit as st

from db import engine
from modules.opcoes.view_opcoes import render_aba_opcoes

st.set_page_config(
    page_title="Market Intelligence Hub",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        :root {
           --bg: #060d18;
           --bg-alt: #0b1725;
           --panel: rgba(12, 21, 32, 0.9);
           --panel-soft: rgba(15, 25, 39, 0.75);
           --line: rgba(148, 163, 184, 0.18);
           --text: #e6edf8;
           --muted: #93a9c6;
           --cyan: #67e8f9;
           --blue: #7dd3fc;
           --green: #34d399;
           --violet: #a78bfa;
        }
        html, body, [data-testid="stAppViewContainer"] {
           background: radial-gradient(circle at top left, rgba(103, 232, 249, 0.12), transparent 22%),
                       linear-gradient(135deg, #050d17 0%, #0a1727 34%, #0f1d2e 100%);
           color: var(--text);
        }
        .block-container {
           padding-top: 1.35rem;
           padding-bottom: 2.5rem;
        }
        .topbar {
           background: linear-gradient(135deg, rgba(11, 23, 37, 0.92), rgba(11, 24, 36, 0.75));
           border: 1px solid var(--line);
           border-radius: 20px;
           padding: 1.2rem 1.35rem;
           margin-bottom: 1rem;
           box-shadow: 0 12px 30px rgba(2, 10, 18, 0.4);
           backdrop-filter: blur(10px);
        }
        .topbar h1 {
           margin: 0;
           font-size: 2.1rem;
           font-weight: 700;
           letter-spacing: 0.04em;
        }
        .topbar p {
           margin: 0.25rem 0 0;
           color: var(--muted);
           letter-spacing: 0.02em;
        }
        .status-pill {
           display: inline-block;
           border: 1px solid rgba(103, 232, 249, 0.35);
           background: rgba(103, 232, 249, 0.08);
           color: var(--cyan);
           border-radius: 999px;
           padding: 0.2rem 0.7rem;
           font-size: 0.72rem;
           font-weight: 600;
           margin-top: 0.6rem;
        }
        [data-testid="stSidebar"] {
           background: rgba(7, 15, 23, 0.88);
           border-right: 1px solid var(--line);
        }
        [data-testid="stSidebarNav"] {
           background: rgba(9, 17, 26, 0.65);
        }
        [data-testid="stTabList"] {
           gap: 0.65rem;
           margin-bottom: 1rem;
        }
        [data-testid="stTab"] {
           background: rgba(15, 23, 42, 0.72);
           border: 1px solid var(--line);
           border-radius: 10px 10px 0 0;
           padding: 0.6rem 0.9rem;
           color: var(--muted);
        }
        [data-testid="stTabButton"] > div {
           color: var(--text);
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
           background: transparent;
        }
        .stButton > button,
        .stDownloadButton > button {
           border-radius: 12px;
           border: 1px solid rgba(125, 211, 252, 0.45);
           background: linear-gradient(135deg, rgba(125, 211, 252, 0.16), rgba(103, 232, 249, 0.07));
           color: var(--text);
           transition: all 0.2s ease;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover {
           border-color: rgba(125, 211, 252, 0.7);
           box-shadow: 0 8px 22px rgba(103, 232, 249, 0.15);
        }
        .stDataFrame {
           background: rgba(6, 14, 22, 0.5);
           border-radius: 12px;
        }
        .stAlert {
           background: rgba(12, 21, 32, 0.72);
           border: 1px solid var(--line);
           border-left: 3px solid var(--cyan);
           color: var(--text);
        }
        .element-container > div > div {
           border-radius: 12px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

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
    st.title("Operações")
    st.caption("Plataforma de inteligência de mercado")
    st.markdown("- Macro / taxas / dólar")
    st.markdown("- Debêntures e emissões")
    st.markdown("- Notícias")
    st.markdown("- Monitor de empresas")
    st.markdown("- Carteira e cenário")
    st.markdown("- Relatórios executivos")
    if st.button("🤖 Assistente IA", use_container_width=True):
        st.session_state["ia_open"] = True


def formatar_data_br(data):
    if pd.isna(data):
        return ""
    if isinstance(data, str):
        data = pd.to_datetime(data)
    return data.strftime("%d/%m/%Y")


def formatar_moeda(valor):
    if pd.isna(valor):
        return ""
    return f"R$ {valor:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


ind = pd.read_sql("SELECT * FROM indicadores_bcb", engine)


def normalizar_indicador(valor):
    if pd.isna(valor):
        return ""
    texto = str(valor).lower().strip()
    texto = re.sub(r"[^a-z0-9]", "", texto)
    return texto


def ultimo_valor(nome):
    chave = normalizar_indicador(nome)
    serie = ind[ind["indicador"].map(normalizar_indicador) == chave]
    if serie.empty:
        return 0.0
    return float(serie["valor"].iloc[-1])


def montar_contexto_ia():
    try:
        dolar = pd.read_sql("SELECT * FROM usd_brl ORDER BY date", engine)
        deb = pd.read_sql("SELECT * FROM debentures_series", engine)
        mercado = pd.read_sql("SELECT titulo FROM noticias LIMIT 5", engine)
        return {
           "selic": ultimo_valor("Selic"),
           "ipca": ultimo_valor("IPCA"),
           "igp_m": ultimo_valor("IGP-M"),
           "dolar": float(dolar["close"].iloc[-1]) if not dolar.empty else 0.0,
           "debentures": len(deb),
           "manchetes": "; ".join(mercado["titulo"].head(5).tolist()) if not mercado.empty else "",
        }
    except Exception:
        return {"selic": 0.0, "ipca": 0.0, "igp_m": 0.0, "dolar": 0.0, "debentures": 0, "manchetes": ""}


# Dados referenciados em várias abas
try:
    dolar = pd.read_sql("SELECT * FROM usd_brl ORDER BY date", engine)
except Exception:
    dolar = pd.DataFrame(columns=["date", "close"])

try:
    noticias = pd.read_sql("SELECT titulo, link, data, categoria FROM noticias", engine)
    mercado = noticias[~noticias["categoria"].isin(["Outros", ""])].copy()
except Exception:
    noticias = pd.DataFrame(columns=["titulo", "link", "data", "categoria"])
    mercado = noticias.copy()

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
except Exception:
    deb = pd.DataFrame()


# Helpers de download

def gerar_bytes_relatorio(export_func):
    try:
        caminho = export_func()
        if not caminho:
           return None, None
        with open(caminho, "rb") as arquivo:
           return arquivo.read(), caminho
    except Exception as exc:
        st.error(f"Erro ao preparar relatório: {exc}")
        return None, None


# Abas
overview_tab, macro_tab, noticias_tab, investidas_tab, carteira_tab, relatorios_tab, opcoes_tab = st.tabs(
    ["Resumo", "Macro", "Notícias", "Investidas", "Carteira", "Relatórios", "Opções"]
)

with overview_tab:
    st.subheader("Resumo executivo")
    try:
        briefing = pd.read_sql("SELECT texto FROM briefing", engine)
        if not briefing.empty:
           st.info(briefing["texto"].iloc[0])
    except Exception:
        st.write("Rode o briefing.py para gerar o comentário do dia.")

    try:
        destaques = pd.read_sql("SELECT texto FROM destaques", engine)
        if not destaques.empty:
           st.markdown("**⚡ Destaques do dia**")
           st.markdown(destaques["texto"].iloc[0])
    except Exception:
        pass

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Selic", f"{ultimo_valor('Selic'):.2f}%")
    c2.metric("IPCA", f"{ultimo_valor('IPCA'):.2f}%")
    c3.metric("IGP-M", f"{ultimo_valor('IGP-M'):.2f}%")
    c4.metric("Dólar", formatar_moeda(float(dolar["close"].iloc[-1]) if not dolar.empty else 0))

with macro_tab:
    st.subheader("Indicadores macro")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Selic (% a.a.)", round(ultimo_valor("Selic"), 2))
    c2.metric("CDI (% a.d.)", round(ultimo_valor("CDI"), 4))
    c3.metric("IPCA (% mes)", round(ultimo_valor("IPCA"), 2))
    c4.metric("IGP-M (% mes)", round(ultimo_valor("IGP-M"), 2))

    st.subheader("Dólar (USD/BRL)")
    if not dolar.empty:
        st.line_chart(dolar, x="date", y="close")
        dolar_display = dolar.copy()
        dolar_display["date"] = dolar_display["date"].apply(formatar_data_br)
        dolar_display["close"] = dolar_display["close"].apply(lambda x: f"R$ {x:.4f}")
        st.dataframe(dolar_display, use_container_width=True, hide_index=True)
    else:
        st.info("Sem dados de dólar disponíveis.")

    st.subheader("Debêntures")
    if not deb.empty:
        d1, d2 = st.columns(2)
        d1.metric("Séries coletadas", len(deb))
        d2.metric("Volume total (R$ bi)", round(deb["valor_serie"].sum() / 1e9, 2))
        st.write("**Emissões por indexador**")
        st.bar_chart(deb["indexador"].value_counts())
        deb_display = deb[[
           "nome_emissor", "serie", "indexador", "spread", "valor_serie", "prazo_anos",
           "data_emissao", "data_vencimento", "rating", "titulo_incentivado",
           "nome_lider", "agente_fiduciario", "data_encerramento", "link_sre",
        ]].copy()
        for coluna in ["data_emissao", "data_vencimento", "data_encerramento"]:
           if coluna in deb_display.columns:
               deb_display[coluna] = deb_display[coluna].apply(formatar_data_br)
        if "valor_serie" in deb_display.columns:
           deb_display["valor_serie"] = deb_display["valor_serie"].apply(lambda x: formatar_moeda(x / 1e6) if pd.notna(x) else "")
        if "spread" in deb_display.columns:
           deb_display["spread"] = deb_display["spread"].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "")
        st.dataframe(deb_display, use_container_width=True, hide_index=True)
    else:
        st.info("Sem dados de debêntures disponíveis.")

with noticias_tab:
    st.subheader("Notícias do mercado")
    if noticias.empty:
        st.info("Nenhuma notícia disponível no momento.")
    else:
        for _, n in noticias.head(20).iterrows():
           st.markdown(f"`{n['categoria']}` **[{n['titulo']}]({n['link']})** — _{n['data']}_")

with investidas_tab:
    st.subheader("Monitor de empresas")
    try:
        from investidas import (
           adicionar_empresa_interesse,
           criar_tabela_empresas_interesse,
           filtrar_noticias_por_empresa,
           listar_empresas_interesse,
           remover_empresa_interesse,
        )

        criar_tabela_empresas_interesse()

        with st.form("form_empresas_interesse", clear_on_submit=True):
           nome_empresa = st.text_input("Empresa", placeholder="Ex.: Itaúsa")
           cnpj = st.text_input("CNPJ (opcional)", placeholder="17.197.092/0001-91")
           enviado = st.form_submit_button("Adicionar empresa")
           if enviado and nome_empresa:
               ok = adicionar_empresa_interesse(nome_empresa, cnpj)
               if ok:
                   st.success(f"Empresa {nome_empresa} adicionada ao monitoramento.")
               else:
                   st.warning("Não foi possível salvar a empresa.")

        empresas = listar_empresas_interesse()
        if empresas.empty:
           st.info("Nenhuma empresa configurada. Adicione uma para começar a monitorar notícias.")
        else:
           for _, empresa in empresas.iterrows():
               nome = empresa["nome_empresa"]
               cnpj_empresa = empresa.get("cnpj", "")
               noticias_empresa = filtrar_noticias_por_empresa(nome)
               col1, col2 = st.columns([4, 1])
               with col1:
                   st.markdown(f"### {nome} ({cnpj_empresa or 'CNPJ não informado'})")
               with col2:
                   if st.button("Remover", key=f"remove_{nome}"):
                       remover_empresa_interesse(nome)
                       st.rerun()

               if noticias_empresa.empty:
                   st.caption(f"Sem notícias recentes sobre {nome}.")
               else:
                   for _, n in noticias_empresa.head(5).iterrows():
                       st.markdown(f"`{n['categoria']}` **[{n['titulo']}]({n['link']})** — _{n['data']}_")
    except Exception as exc:
        st.warning(f"Erro ao carregar Investidas: {exc}")

with carteira_tab:
    st.subheader("Minha carteira")
    try:
        from carteira import ler_carteira, salvar_carteira, gerar_contexto_carteira

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
           use_container_width=True,
           hide_index=True,
           key="carteira_editor",
           num_rows="dynamic",
        )

        if st.button("Salvar carteira"):
           ok = salvar_carteira(df_editado)
           if ok:
               st.success("Carteira atualizada com sucesso!")
               st.rerun()
           else:
               st.error("Não foi possível salvar a carteira.")

        st.markdown("**Resumo da carteira**")
        st.info(gerar_contexto_carteira())
    except Exception as exc:
        st.warning(f"Erro ao carregar carteira: {exc}")

with relatorios_tab:
    st.subheader("Relatórios operacionais")
    try:
        from relatorios import (
           gerar_relatorio_debentures,
           gerar_relatorio_dolar,
           gerar_relatorio_indicadores,
        )

        relatorios = {
           "Debêntures": ("relatorio_debentures.xlsx", gerar_relatorio_debentures),
           "Indicadores": ("relatorio_indicadores.xlsx", gerar_relatorio_indicadores),
           "Dólar": ("relatorio_dolar.xlsx", gerar_relatorio_dolar),
        }

        for nome, (arquivo_nome, export_func) in relatorios.items():
           col1, col2 = st.columns([3, 1])
           with col1:
               st.write(f"**{nome}**")
           with col2:
               if st.button(f"Gerar {nome}", key=f"btn_{arquivo_nome}"):
                   payload, _ = gerar_bytes_relatorio(export_func)
                   if payload is not None:
                       st.session_state[f"download_{arquivo_nome}"] = payload
                       st.success(f"Relatório {nome} preparado.")
               if st.session_state.get(f"download_{arquivo_nome}") is not None:
                   st.download_button(
                       label=f"Baixar {arquivo_nome}",
                       data=st.session_state[f"download_{arquivo_nome}"] ,
                       file_name=arquivo_nome,
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True,
                   )

        if st.button("Gerar todos os relatórios"):
           try:
               from relatorios import exportar_todos_relatorios
               arquivos = exportar_todos_relatorios()
               st.success(f"{len(arquivos)} relatórios gerados.")
               for destino in arquivos:
                   st.caption(destino)
           except Exception as exc:
               st.error(f"Erro ao gerar lote: {exc}")
    except Exception as exc:
        st.warning(f"Erro ao carregar relatórios: {exc}")

with opcoes_tab:
    render_aba_opcoes(selic=ultimo_valor("Selic") / 100)

prompt_ia = st.chat_input("Pergunte à plataforma sobre mercado, taxas e renda fixa...")
if prompt_ia:
    try:
        from analise_ia import responder_pergunta
        from carteira import gerar_contexto_carteira

        contexto = (
           f"Indicadores: Selic {round(ultimo_valor('Selic'), 2)}% a.a., "
           f"IPCA {round(ultimo_valor('IPCA'), 2)}% (mes), IGP-M {round(ultimo_valor('IGP-M'), 2)}% (mes).\n"
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

