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

        st.divider()
        # "Gerar todos" antes so' escrevia os arquivos no disco do servidor e
        # imprimia os caminhos - nenhum botao de download aparecia, entao pela
        # tela o lote parecia nao funcionar. Agora ele alimenta os MESMOS
        # session_state dos botoes individuais (fazendo os tres downloads
        # aparecerem) e ainda oferece um ZIP unico.
        if st.button("Gerar todos os relatórios"):
            gerados = {}
            for nome, (arquivo_nome, export_func) in relatorios.items():
                payload, _ = _gerar_bytes_relatorio(export_func)
                if payload is not None:
                    st.session_state[f"download_{arquivo_nome}"] = payload
                    gerados[arquivo_nome] = payload
            if gerados:
                import io as _io
                import zipfile as _zipfile
                buffer = _io.BytesIO()
                with _zipfile.ZipFile(buffer, "w", _zipfile.ZIP_DEFLATED) as zip_arquivo:
                    for arquivo_nome, payload in gerados.items():
                        zip_arquivo.writestr(arquivo_nome, payload)
                st.session_state["download_todos_zip"] = buffer.getvalue()
                st.success(
                    f"{len(gerados)} relatório(s) preparado(s). Baixe em conjunto "
                    "abaixo, ou individualmente nos botões acima."
                )
            else:
                st.warning("Nenhum relatório pôde ser gerado.")

        if st.session_state.get("download_todos_zip") is not None:
            st.download_button(
                label="Baixar todos (.zip)",
                data=st.session_state["download_todos_zip"],
                file_name="relatorios.zip",
                mime="application/zip",
                width="stretch",
            )
    except Exception as exc:
        st.warning(f"Erro ao carregar relatórios: {exc}")
