"""
paginas/resumo.py - Pagina "Resumo": o que se moveu, o que as empresas
monitoradas comunicaram, e as manchetes de mercado.

Montada sobre dado que ATUALIZA SOZINHO todo dia. A versao anterior dependia
de duas fontes que nao atualizam: texto gerado por IA (a cota da API estoura e
o texto congela) e "sinais do dia" derivados da carteira - que produziam ZERO
sinais, sempre, porque exposicao.py entende indexadores de renda fixa (CDI,
Prefixado, IPCA, Dolar) e a carteira usa "Ibov". A secao de sinais foi removida;
exposicao.py continua no repositorio para quando a carteira voltar a ser usada.

Os "drivers" aqui sao FATOS, nao previsoes: um fato relevante da CVM e' algo
que pode mexer com o papel, esta' datado e tem link. Nao ha' tentativa de
estimar impacto - essa distincao e' deliberada.

Visual: usa kpi_card e estado_vazio do tema (mesma familia da pagina Macro).
Esta pagina era a mais visivel e a que mais ignorava o sistema de design.
"""
import pandas as pd
import streamlit as st

from componentes import estado_vazio, kpi_card
from dados_app import (calcular_delta_indicador, carregar_dolar,
                       carregar_indicadores, carregar_noticias, ultimo_valor)
from db import engine

SETA_CIMA = "▲"
SETA_BAIXO = "▼"


def _texto_com_data(tabela: str):
    """Devolve (texto, gerado_em) da tabela, ou (None, None).

    A data importa: com a cota da API de IA estourada, o texto para de ser
    regerado e fica antigo. Exibi-lo sem data o faria passar por atual."""
    try:
        df = pd.read_sql(f"SELECT * FROM {tabela}", engine)
    except Exception:
        return None, None
    if df.empty:
        return None, None
    linha = df.iloc[0]
    return linha.get("texto"), (linha.get("gerado_em") if "gerado_em" in df.columns else None)


def _kpi_indicador(ind, nome, label, casas=2, sufixo="%"):
    """Card de KPI de 'o que se moveu', ou None se nao houver leitura.

    Sentido "neutro" de proposito: variacao de indicador macro nao tem leitura
    de bom/ruim universal - juro subindo e' bom pra aplicador e ruim pra
    tomador. Mesma decisao ja tomada na pagina Macro (avaliar=False)."""
    try:
        valor = ultimo_valor(ind, nome)
    except Exception:
        return None
    if valor is None:
        return None
    valor_texto = f"{valor:.{casas}f}{sufixo}"
    delta = calcular_delta_indicador(ind, nome)
    if delta in (None, 0):
        return kpi_card(label, valor_texto)
    seta = SETA_CIMA if delta > 0 else SETA_BAIXO
    return kpi_card(label, valor_texto, f"{seta} {delta:+.{casas}f} p.p.", "neutro")


def _kpi_dolar(dolar):
    """Card do USD/BRL com a variacao contra o pregao anterior."""
    if dolar.empty or "close" not in dolar:
        return None
    serie = dolar.sort_values("date")
    atual = float(serie["close"].iloc[-1])
    delta_texto = None
    if len(serie) > 1:
        anterior = float(serie["close"].iloc[-2])
        if anterior:
            variacao = (atual - anterior) / anterior * 100
            seta = SETA_CIMA if variacao > 0 else (SETA_BAIXO if variacao < 0 else "•")
            delta_texto = f"{seta} {variacao:+.2f}%"
    return kpi_card("USD/BRL", f"R$ {atual:.2f}", delta_texto, "neutro")


def pagina_resumo():
    st.subheader("Resumo executivo")

    # ---------------- O que se moveu ----------------
    ind = carregar_indicadores()
    dolar = carregar_dolar()

    st.markdown("**📊 O que se moveu**")
    cards = [
        _kpi_indicador(ind, "Selic", "Selic", 2),
        _kpi_indicador(ind, "CDI", "CDI", 4),
        _kpi_indicador(ind, "IPCA", "IPCA (mês)", 2),
        _kpi_indicador(ind, "IGP-M", "IGP-M (mês)", 2),
        _kpi_dolar(dolar),
    ]
    presentes = [card for card in cards if card]
    if presentes:
        for coluna, card in zip(st.columns(len(presentes)), presentes):
            coluna.markdown(card, unsafe_allow_html=True)
    else:
        st.markdown(estado_vazio(
            "Sem indicadores coletados",
            "Rode <code>python atualizar.py</code> para trazer Selic, CDI, IPCA, "
            "IGP-M e dólar."), unsafe_allow_html=True)

    # ---------------- Drivers: comunicados das monitoradas ----------------
    st.markdown("**🏢 Comunicados recentes das empresas monitoradas**")
    st.caption(
        "Fatos relevantes e avisos publicados na CVM. São **fatos datados**, "
        "não previsão de impacto."
    )
    try:
        from investidas import ler_comunicados
        comunicados = ler_comunicados()
    except Exception:
        comunicados = pd.DataFrame()

    if comunicados.empty:
        st.markdown(estado_vazio(
            "Nenhum comunicado coletado ainda",
            "Vincule as empresas pelo CNPJ em <b>Empresas monitoradas</b> e rode "
            "<code>python coleta_cvm.py</code>."), unsafe_allow_html=True)
    else:
        for _, c in comunicados.head(6).iterrows():
            assunto = str(c.get("fato_relevante") or "").strip()
            if not assunto or assunto.lower() == "nan":
                assunto = "(sem assunto informado)"
            empresa = str(c.get("nome_empresa") or "")
            data = str(c.get("data_arquivamento") or "")[:10]
            link = c.get("link_cvm")
            categoria = str(c.get("categoria") or "")
            texto = f"`{categoria}` **{empresa}** — {assunto[:110]} _{data}_"
            if link and str(link).strip().lower() != "nan":
                texto += f" · [documento]({link})"
            st.markdown(texto)

    # ---------------- Manchetes ----------------
    st.markdown("**📰 Manchetes de mercado**")
    noticias = carregar_noticias()
    if noticias.empty:
        st.markdown(estado_vazio(
            "Nenhuma notícia coletada",
            "Rode <code>python coleta_noticias.py</code> — a coleta também roda "
            "sozinha no <code>atualizar.py</code>."), unsafe_allow_html=True)
    else:
        for _, n in noticias.head(6).iterrows():
            st.markdown(f"[{n['titulo']}]({n['link']}) — _{n['data']}_")

    # ---------------- Texto gerado por IA ----------------
    st.divider()
    briefing, data_briefing = _texto_com_data("briefing")
    if briefing:
        st.markdown("**🧠 Briefing do dia**")
        st.info(briefing)
        if data_briefing:
            st.caption(f"Gerado em {data_briefing}.")
        else:
            st.caption(
                "Data de geração não registrada — pode estar desatualizado. "
                "A partir da próxima execução de `briefing.py` a data aparece aqui."
            )

    destaques, data_destaques = _texto_com_data("destaques")
    if destaques:
        st.markdown("**⚡ Destaques do dia**")
        st.markdown(destaques)
        if data_destaques:
            st.caption(f"Gerado em {data_destaques}.")

    if not briefing and not destaques:
        st.markdown(estado_vazio(
            "Sem briefing gerado",
            "Rode <code>python briefing.py</code>. Ele depende da API de IA — se a "
            "cota estiver esgotada, o texto anterior é mantido em vez de sobrescrito."
        ), unsafe_allow_html=True)
