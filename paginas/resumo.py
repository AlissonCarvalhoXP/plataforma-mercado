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
"""
import pandas as pd
import streamlit as st

from dados_app import (calcular_delta_indicador, carregar_dolar,
                       carregar_indicadores, carregar_noticias, ultimo_valor)
from db import engine


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


def _linha_indicador(ind, nome, label, casas=2, sufixo="%"):
    """Uma linha de 'o que se moveu', ou None se nao houver leitura."""
    try:
        valor = ultimo_valor(ind, nome)
    except Exception:
        return None
    if valor is None:
        return None
    delta = calcular_delta_indicador(ind, nome)
    seta = "" if delta in (None, 0) else ("▲" if delta > 0 else "▼")
    variacao = "" if delta in (None, 0) else f" {seta} {delta:+.{casas}f} p.p."
    return f"**{label}** {valor:.{casas}f}{sufixo}{variacao}"


def pagina_resumo():
    st.subheader("Resumo executivo")

    # ---------------- O que se moveu ----------------
    ind = carregar_indicadores()
    dolar = carregar_dolar()

    st.markdown("**📊 O que se moveu**")
    linhas = [
        _linha_indicador(ind, "Selic", "Selic", 2),
        _linha_indicador(ind, "CDI", "CDI", 4),
        _linha_indicador(ind, "IPCA", "IPCA (mês)", 2),
        _linha_indicador(ind, "IGP-M", "IGP-M (mês)", 2),
    ]
    if not dolar.empty and "close" in dolar:
        serie = dolar.sort_values("date")
        atual = float(serie["close"].iloc[-1])
        texto_dolar = f"**USD/BRL** R$ {atual:.2f}"
        if len(serie) > 1:
            anterior = float(serie["close"].iloc[-2])
            if anterior:
                variacao = (atual - anterior) / anterior * 100
                seta = "▲" if variacao > 0 else ("▼" if variacao < 0 else "")
                texto_dolar += f" {seta} {variacao:+.2f}%"
        linhas.append(texto_dolar)

    presentes = [linha for linha in linhas if linha]
    if presentes:
        st.markdown(" · ".join(presentes))
    else:
        st.info("Sem indicadores coletados. Rode `python atualizar.py`.")

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
        st.caption(
            "Nenhum comunicado coletado ainda. Vincule as empresas pelo CNPJ em "
            "*Empresas monitoradas* e rode `python coleta_cvm.py`."
        )
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
        st.caption("Nenhuma notícia coletada.")
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
        st.caption("Sem briefing gerado. Rode `python briefing.py`.")
