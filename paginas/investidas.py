"""
paginas/investidas.py - Pagina "Investidas": monitor de fatos relevantes
por empresa cadastrada.
"""
import streamlit as st


def pagina_investidas():
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
