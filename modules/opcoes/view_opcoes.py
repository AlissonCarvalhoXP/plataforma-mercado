"""Aba 'Opções B3' do MIH (Fase D do handoff).

Componente Streamlit para plugar no app.py do Hub, no padrão Cenário B (tela única
com abas). Não roda sozinho — é chamado pelo app.py principal via render_aba_opcoes().

No app.py do MIH:
    from modules.opcoes.view_opcoes import render_aba_opcoes
    abas = st.tabs(["Visão Geral", "Gestão de Caixa", "Debêntures", "Opções B3"])
    with abas[3]:
        render_aba_opcoes(selic=selic_atual)   # selic vinda de coleta_bcb
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

DISCLAIMER = ("⚠️ Ferramenta de apoio à decisão e estudo quantitativo. "
              "NÃO constitui recomendação de investimento.")


def render_aba_opcoes(selic: float = 0.1415, db_path: str | None = None,
                       carteira_df: "pd.DataFrame | None" = None):
    import streamlit as st
    import pandas as pd
    import plotly.graph_objects as go
    import db_opcoes
    import analises_opcoes as ao
    import coleta_opcoes as co

    st.subheader("🎯 Opções B3 · Screener de Assimetria IV × HV")
    st.caption("Fonte: brapi.dev (EOD) · Preço justo via Black-Scholes · " + DISCLAIMER)

    # ativos disponíveis no banco
    db_opcoes.init_schema(db_path)
    import sqlite3
    con = sqlite3.connect(db_path or db_opcoes.DB_PATH)
    ativos = [r[0] for r in con.execute(
        "SELECT DISTINCT Ativo_Objeto FROM opcoes_series ORDER BY Ativo_Objeto").fetchall()]
    con.close()

    if not ativos:
        st.info("Nenhuma cadeia coletada ainda. Rode `python coleta_opcoes.py` para popular.")
        return

    c1, c2, c3 = st.columns([1, 1, 1])
    ativo = c1.selectbox("Ativo-objeto", ativos)
    liq_min = c2.number_input("Liquidez mínima (vol+OI)", 0, step=1000, value=5000)
    peso_diff = c3.slider("Peso do Diff no score", 0.0, 1.5, 0.6, 0.1)

    und, series = db_opcoes.read_latest_chain(ativo, db_path)
    if not und or not series:
        st.warning(f"Sem dados para {ativo}.")
        return

    rank = ao.analisar(und, series, selic=selic, peso_diff=peso_diff, liquidez_min=int(liq_min))
    regime = ao.regime_volatilidade(series, und["HV_60d"])

    # KPIs
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Spot", f"R$ {und['Spot']:.2f}")
    k2.metric("HV 60d", f"{und['HV_60d']:.1%}")
    k3.metric("Séries", len(series))
    k4.metric("Regime vol", regime)
    k5.metric("Oportunidades", sum(1 for l in rank if abs(l["Diff_pp"]) >= 8))
    st.caption(f"Taxa livre de risco (Selic): {selic:.2%} · Data ref.: {und['Data_Referencia']}")

    aba1, aba2, aba3 = st.tabs(["📊 Ranking", "⛓️ Cadeia", "🎯 Estratégias"])

    with aba1:
        if rank:
            df = pd.DataFrame(rank)[["Codigo_Opcao", "Tipo", "Strike", "Dias",
                "Preco_Mercado", "Justo_BS", "Desconto", "IV", "HV", "Diff_pp",
                "Delta", "Sinal"]]
            st.dataframe(df, use_container_width=True, height=380)
            # IV x HV por strike
            calls = [l for l in rank if l["Tipo"] == "CALL"]
            if calls:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=[c["Strike"] for c in calls],
                                         y=[c["IV"] for c in calls],
                                         mode="lines+markers", name="IV (calls)"))
                fig.add_hline(y=und["HV_60d"], line_dash="dash", annotation_text="HV 60d")
                fig.update_layout(title="IV × HV por strike", template="plotly_dark",
                                  height=320, xaxis_title="Strike", yaxis_title="Vol")
                st.plotly_chart(fig, use_container_width=True)

    with aba2:
        st.dataframe(pd.DataFrame(series), use_container_width=True, height=420)

    with aba3:
        st.markdown(f"**Regime de volatilidade: `{regime}`**")
        if regime == "ALTA":
            st.write("IV cara → **vender prêmio**: venda coberta, trava de alta de "
                     "crédito, Iron Condor (theta a favor).")
        elif regime == "BAIXA":
            st.write("IV barata → **comprar volatilidade**: long call/put, straddle, calendar.")
        else:
            st.write("Sem distorção clara → **travas de débito direcionais** ou aguardar assimetria.")
        st.caption(DISCLAIMER)

    # Sugestoes de hedge para a carteira do usuario - secao aditiva, nao
    # substitui nem depende do ranking/screener acima (que continua cobrindo
    # qualquer ativo coletado, com ou sem posicao na carteira).
    if carteira_df is not None and not carteira_df.empty:
        st.markdown("---")
        st.subheader("🛡️ Sugestões de hedge para sua carteira")
        st.caption(DISCLAIMER)

        posicoes_acoes = [
            row for row in carteira_df.to_dict("records")
            if co.PADRAO_TICKER_B3.match(str(row.get("ativo", "")).strip().upper())
        ]
        if not posicoes_acoes:
            st.info("Nenhuma posição em ações reconhecida na carteira.")
        else:
            for posicao in posicoes_acoes:
                ticker = str(posicao["ativo"]).strip().upper()
                try:
                    posicao_norm = {**posicao, "ativo": ticker}
                    und_pos, series_pos = db_opcoes.read_latest_chain(ticker, db_path)
                    if not und_pos or not series_pos:
                        st.warning(
                            f"Sem dados de opções disponíveis para {ticker} "
                            "(requer plano Pro da brapi)."
                        )
                        continue
                    rank_pos = ao.analisar(und_pos, series_pos, selic=selic, liquidez_min=5000)
                    regime_pos = ao.regime_volatilidade(series_pos, und_pos["HV_60d"])
                    sugestao = ao.sugerir_hedge(posicao_norm, rank_pos, und_pos["Spot"], regime_pos)
                    if sugestao is None:
                        st.caption(
                            f"{ticker}: sem sugestão de hedge no momento "
                            f"(regime `{regime_pos}` sem série OTM adequada)."
                        )
                    else:
                        st.markdown(f"- {sugestao['texto']}")
                except Exception as exc:
                    st.warning(f"{ticker}: não foi possível calcular a sugestão de hedge ({exc}).")
