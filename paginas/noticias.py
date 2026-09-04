"""
paginas/noticias.py - Pagina "Noticias": manchetes com filtro por empresa
monitorada, texto livre e categoria.

O filtro NAO depende da classificacao por IA para funcionar: empresa e texto
livre operam sobre o titulo. O seletor de categoria so' aparece quando ha'
noticia de fato classificada - hoje a classificacao vem falhando (503 da API
do Gemini), e oferecer o filtro sugeriria uma capacidade que nao existe.

A ordem continua cronologica de proposito. Ordenar por "relevancia" exigiria
um criterio de relevancia, que e' facil de inventar e dificil de sustentar.
"""
import streamlit as st

from dados_app import carregar_carteira, carregar_noticias


def _opcoes_monitoradas():
    """Empresas e ativos que o usuario ja declarou acompanhar.

    Vem da lista de empresas de interesse e da carteira - nao e' digitacao.
    O filtro oferece o que voce ja disse que importa, em vez de exigir que
    voce lembre de escrever."""
    opcoes = set()
    try:
        from investidas import listar_empresas_interesse
        empresas = listar_empresas_interesse()
        opcoes.update(str(n).strip() for n in empresas.get("nome_empresa", []) if str(n).strip())
    except Exception:
        pass
    try:
        carteira = carregar_carteira()
        if not carteira.empty and "ativo" in carteira:
            opcoes.update(str(a).strip().upper() for a in carteira["ativo"] if str(a).strip())
    except Exception:
        pass
    return sorted(opcoes)


def pagina_noticias():
    st.subheader("Notícias do mercado")

    noticias = carregar_noticias()
    if noticias.empty:
        st.info("Nenhuma notícia disponível no momento.")
        return

    from investidas import categorias_disponiveis, filtrar_noticias

    monitoradas = _opcoes_monitoradas()
    categorias = categorias_disponiveis(noticias)

    col1, col2 = st.columns([2, 2])
    with col1:
        escolhidas = st.multiselect(
            "Empresas monitoradas", monitoradas,
            help="Vem da sua carteira e das empresas cadastradas em Investidas.",
        ) if monitoradas else []
        if not monitoradas:
            st.caption("Cadastre empresas em *Investidas* para filtrar por elas aqui.")
    with col2:
        texto = st.text_input("Buscar no título", placeholder="Ex.: Copom, dividendo, PETR4")

    # O seletor de categoria some quando nada foi classificado, em vez de
    # oferecer um filtro que nao filtra nada.
    categoria = None
    if categorias:
        escolha = st.selectbox("Categoria", ["(todas)"] + categorias)
        categoria = None if escolha == "(todas)" else escolha
    else:
        st.caption(
            "Nenhuma notícia classificada por categoria ainda — o filtro por "
            "categoria aparece quando houver. Rode `classificar_noticias.py` "
            "para tentar classificar."
        )

    termos = list(escolhidas) + ([texto] if texto.strip() else [])
    filtradas = filtrar_noticias(noticias, termos=termos, categoria=categoria)

    total, restantes = len(noticias), len(filtradas)
    if termos or categoria:
        st.caption(f"{restantes} de {total} notícias correspondem ao filtro.")
        if restantes == 0:
            st.info(
                "Nenhuma notícia bate com esse filtro. A busca é por menção "
                "literal no título — tente um termo mais curto, ou o nome como "
                "aparece na manchete."
            )
            return
    else:
        st.caption(f"{total} notícias coletadas. Use os filtros acima para restringir.")

    for _, n in filtradas.head(50).iterrows():
        categoria_txt = str(n.get("categoria") or "").strip()
        prefixo = f"`{categoria_txt}` " if categoria_txt and categoria_txt.lower() != "nan" else ""
        st.markdown(f"{prefixo}**[{n['titulo']}]({n['link']})** — _{n['data']}_")
