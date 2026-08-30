"""
paginas/relatorios.py - Pagina "Relatorios": geracao/download dos
relatorios Excel operacionais.
"""
import streamlit as st


def _gerar_bytes_relatorio(export_func):
    try:
        caminho = export_func()
        if not caminho:
            return None, None
        with open(caminho, "rb") as arquivo:
            return arquivo.read(), caminho
    except Exception as exc:
        st.error(f"Erro ao preparar relatório: {exc}")
        return None, None


def pagina_relatorios():
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
                    payload, _ = _gerar_bytes_relatorio(export_func)
                    if payload is not None:
                        st.session_state[f"download_{arquivo_nome}"] = payload
                        st.success(f"Relatório {nome} preparado.")
                if st.session_state.get(f"download_{arquivo_nome}") is not None:
                    st.download_button(
                        label=f"Baixar {arquivo_nome}",
                        data=st.session_state[f"download_{arquivo_nome}"],
                        file_name=arquivo_nome,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        width="stretch",
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
