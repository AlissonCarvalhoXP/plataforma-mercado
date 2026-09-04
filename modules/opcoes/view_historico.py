"""Pagina 'Historico Opcoes': o registro do que voce declarou e do que registrou.

Duas tabelas que medem coisas DIFERENTES, e a tela diz isso:

- Declaracoes: mede sua PREVISAO. O que voce achava que ia acontecer, quando
  achou, e o que de fato aconteceu.
- Operacoes: mede sua EXECUCAO. Quais estruturas voce registrou e quanto elas
  deram no vencimento.

A segunda so' existe se voce marcar operacoes na aba de Opcoes - sem marcacao
nao ha' o que medir, e a ausencia de registro NAO significa ausencia de
resultado. A tela avisa isso em vez de deixar a tabela vazia sugerir que nada
deu certo.
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

DISCLAIMER = ("⚠️ Ferramenta de apoio à decisão e estudo quantitativo. "
              "NÃO constitui recomendação de investimento.")


def render_pagina_historico(db_path: str | None = None):
    import streamlit as st
    import pandas as pd
    import db_opcoes
    import afericao_cenarios as af

    st.subheader("📒 Histórico de Opções")
    st.caption(
        "Registro do que você declarou e do que registrou, com o resultado "
        "quando o vencimento chega. O fechamento é automático, pelo passo "
        "diário de atualização. " + DISCLAIMER
    )

    db_opcoes.init_schema_cenarios(db_path)
    db_opcoes.init_schema_operacoes(db_path)

    declaracoes = db_opcoes.ler_declaracoes(db_path=db_path)
    operacoes = db_opcoes.ler_operacoes(db_path=db_path)

    ativos = sorted({d["Ativo"] for d in declaracoes} | {o["Ativo"] for o in operacoes})
    if ativos:
        escolha = st.selectbox("Ativo", ["(todos)"] + ativos, key="hist_ativo")
        if escolha != "(todos)":
            declaracoes = [d for d in declaracoes if d["Ativo"] == escolha]
            operacoes = [o for o in operacoes if o["Ativo"] == escolha]

    # ---------------- Declaracoes ----------------
    st.markdown("### Declarações de cenário")
    st.caption("Mede sua **previsão**: o que você achava, quando achou, e o que ocorreu.")

    if not declaracoes:
        st.info("Nenhum cenário declarado ainda. Declare na aba Opções.")
    else:
        st.dataframe(pd.DataFrame([{
            "Ativo": d["Ativo"],
            "Declarado em": d["Data_Declaracao"],
            "Vencimento": d["Data_Vencimento"],
            "Cenário": d["Cenario"],
            "Alvo": f"R$ {d['Preco_Alvo']:.2f}",
            "Probabilidade": f"{d['Probabilidade']:.0%}",
            "Ajustado": "sim" if d.get("Ajustado") else "não",
            "Realizado": ("—" if d.get("Preco_Realizado") is None
                          else f"R$ {d['Preco_Realizado']:.2f}"),
            "Premissa": d.get("Premissa") or "",
        } for d in declaracoes]), use_container_width=True, hide_index=True)

        nao_ajustadas = sum(1 for d in declaracoes if not d.get("Ajustado")) // 3
        if nao_ajustadas:
            st.caption(
                f"{nao_ajustadas} declaração(ões) marcada(s) como *não ajustada*: "
                "reproduziam a distribuição implícita sem alteração sua. A aferição "
                "as exclui, porque medi-las mediria o preço, não você."
            )

    # ---------------- Operacoes ----------------
    st.markdown("### Operações registradas")
    st.caption(
        "Mede sua **execução**: quais estruturas você registrou e quanto deram. "
        "*Executada* usa o prêmio que você de fato pagou; *acompanhada* usa o "
        "preço de tela — em opção ilíquida a diferença pode ser grande."
    )

    if not operacoes:
        st.info(
            "Nenhuma operação registrada ainda. Use o botão **Registrar** na tabela "
            "de estruturas, na aba Opções. Sem marcação não há o que medir — e uma "
            "tabela vazia aqui significa que nada foi registrado, **não** que nada "
            "deu certo."
        )
        return

    executadas = [o for o in operacoes if o.get("Preco_Executado") is not None]
    acompanhadas = [o for o in operacoes if o.get("Preco_Executado") is None]

    def _tabela(lista):
        return pd.DataFrame([{
            "Ativo": o["Ativo"],
            "Registrada em": o["Data_Registro"],
            "Vencimento": o["Data_Vencimento"],
            "Estrutura": o["Estrutura"],
            "Prêmio tela": f"R$ {o['Premio_Tela']:,.2f}",
            "Prêmio executado": ("—" if o.get("Preco_Executado") is None
                                 else f"R$ {o['Preco_Executado']:,.2f}"),
            "Perda máx.": ("ILIMITADA" if o.get("Perda_Maxima") is None
                           else f"R$ {o['Perda_Maxima']:,.2f}"),
            "Ganho máx.": ("ILIMITADO" if o.get("Ganho_Maximo") is None
                           else f"R$ {o['Ganho_Maximo']:,.2f}"),
            "Resultado": ("em aberto" if o.get("Resultado_Realizado") is None
                          else f"R$ {o['Resultado_Realizado']:,.2f}"),
        } for o in lista])

    if executadas:
        st.markdown("**Executadas**")
        st.dataframe(_tabela(executadas), use_container_width=True, hide_index=True)
        fechadas = [o for o in executadas if o.get("Resultado_Realizado") is not None]
        if fechadas:
            total = sum(o["Resultado_Realizado"] for o in fechadas)
            positivas = sum(1 for o in fechadas if o["Resultado_Realizado"] > 0)
            st.caption(
                f"{len(fechadas)} operação(ões) apurada(s): resultado somado "
                f"R$ {total:,.2f}, com {positivas} positiva(s). "
                "Soma de resultados não é retorno — não pondera capital nem tempo."
            )

    if acompanhadas:
        st.markdown("**Acompanhadas** (preço de tela, sem execução informada)")
        st.dataframe(_tabela(acompanhadas), use_container_width=True, hide_index=True)

    st.caption(DISCLAIMER)
