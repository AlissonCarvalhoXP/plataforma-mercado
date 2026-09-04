"""
paginas/investidas.py - Pagina "Empresas monitoradas": comunicados oficiais
das empresas que voce acompanha, vindos do IPE da CVM.

Deixou de listar noticias de imprensa: isso agora vive na pagina de Noticias,
com filtro por empresa. Aqui e' o que a EMPRESA comunicou oficialmente - fato
relevante, aviso aos acionistas, deliberacao de JCP - com link para o
documento na CVM.

O vinculo com a CVM e' por CNPJ, nao por nome. Medido no dado real: buscar
"VALE" por nome traz 324 registros, quase todos de empresas agricolas; "ITAU"
traz a "Companhia Itaunense Energia" junto do Itau Unibanco. Por isso a tela
pede que voce escolha a companhia UMA VEZ, e grava o CNPJ.
"""
import streamlit as st

from componentes import estado_vazio, kpi_card


def pagina_investidas():
    st.subheader("🏢 Empresas monitoradas")

    try:
        from investidas import (
            adicionar_empresa_interesse,
            buscar_companhias_cvm,
            criar_tabela_empresas_interesse,
            criar_tabela_investidas,
            empresas_sem_vinculo,
            ler_comunicados,
            listar_empresas_interesse,
            remover_empresa_interesse,
        )
    except Exception as exc:
        st.error(f"Erro ao carregar o módulo de empresas: {exc}")
        return

    criar_tabela_empresas_interesse()
    criar_tabela_investidas()

    # ---------------- Vincular empresa ----------------
    with st.expander("➕ Monitorar uma empresa", expanded=False):
        st.caption(
            "Busque pela razão social ou nome comercial. A lista traz apenas "
            "companhias com registro **ativo** na CVM — é o que evita vincular "
            "à empresa errada."
        )
        termo = st.text_input("Buscar companhia", placeholder="Ex.: Itausa, Petrobras, Vale")
        if termo.strip():
            candidatas = buscar_companhias_cvm(termo)
            if candidatas.empty:
                st.warning(
                    "Nenhuma companhia ativa encontrada. Rode `python coleta_cvm.py` "
                    "para baixar o cadastro da CVM, ou tente outro termo."
                )
            else:
                rotulos = {
                    f"{linha['denom_social']} — {linha.get('cnpj_formatado') or linha['cnpj']}"
                    f" ({linha.get('setor') or 'setor n/d'})": linha
                    for _, linha in candidatas.iterrows()
                }
                escolha = st.selectbox("Companhia", list(rotulos.keys()))
                if st.button("Monitorar esta empresa"):
                    linha = rotulos[escolha]
                    ok = adicionar_empresa_interesse(linha["denom_social"], linha["cnpj"])
                    if ok:
                        st.success(f"{linha['denom_social']} agora é monitorada.")
                        st.rerun()
                    else:
                        st.warning("Não foi possível salvar.")

    # ---------------- Pendencias de vinculo ----------------
    pendentes = empresas_sem_vinculo()
    if pendentes:
        st.warning(
            f"**{len(pendentes)} empresa(s) sem CNPJ vinculado**: "
            + ", ".join(pendentes)
            + ". Elas ficam fora da coleta de comunicados — sem CNPJ não dá para "
            "casar com a CVM sem risco de trazer a empresa errada. Vincule-as "
            "pela busca acima."
        )

    empresas = listar_empresas_interesse()
    if empresas.empty:
        st.markdown(estado_vazio(
            "Nenhuma empresa monitorada ainda",
            "Use a busca acima para vincular uma companhia pelo CNPJ."),
            unsafe_allow_html=True)
        return

    # ---------------- Comunicados ----------------
    nomes = list(empresas["nome_empresa"])
    escolhida = st.selectbox("Empresa", nomes, key="empresa_comunicados")
    linha_empresa = empresas[empresas["nome_empresa"] == escolhida].iloc[0]
    cnpj = str(linha_empresa.get("cnpj") or "")

    if not "".join(c for c in cnpj if c.isdigit()):
        st.markdown(estado_vazio(
            f"{escolhida} não tem CNPJ vinculado",
            "Sem CNPJ não dá para casar com a CVM sem risco de trazer a empresa "
            "errada. Adicione-a novamente pela busca acima para criar o vínculo."),
            unsafe_allow_html=True)
    else:
        comunicados = ler_comunicados(cnpj=cnpj)
        if comunicados.empty:
            st.markdown(estado_vazio(
                f"Nenhum comunicado de {escolhida} coletado ainda",
                "Rode <code>python coleta_cvm.py</code> — a coleta também roda "
                "sozinha no <code>atualizar.py</code>."), unsafe_allow_html=True)
        else:
            categorias = sorted(
                {str(c) for c in comunicados["categoria"].dropna() if str(c).strip()}
            )
            filtro = st.selectbox("Categoria", ["(todas)"] + categorias)
            exibir = comunicados if filtro == "(todas)" else comunicados[
                comunicados["categoria"].astype(str) == filtro]

            k1, k2 = st.columns(2)
            k1.markdown(kpi_card("Comunicados", str(len(comunicados))), unsafe_allow_html=True)
            k2.markdown(kpi_card("No filtro", str(len(exibir))), unsafe_allow_html=True)
            for _, c in exibir.head(60).iterrows():
                assunto = str(c.get("fato_relevante") or "").strip()
                if not assunto or assunto.lower() == "nan":
                    assunto = "(sem assunto informado)"
                data = str(c.get("data_arquivamento") or "")[:10]
                link = c.get("link_cvm")
                categoria = str(c.get("categoria") or "")
                texto = f"`{categoria}` **{assunto}** — _{data}_"
                if link and str(link).strip().lower() != "nan":
                    texto += f" · [documento]({link})"
                st.markdown(texto)

    # ---------------- Remover ----------------
    with st.expander("Deixar de monitorar"):
        alvo = st.selectbox("Empresa a remover", nomes, key="remover_empresa")
        if st.button("Remover do monitoramento"):
            if remover_empresa_interesse(alvo):
                st.success(f"{alvo} removida.")
                st.rerun()
            else:
                st.warning("Não foi possível remover.")
