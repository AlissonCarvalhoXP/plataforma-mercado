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
    import componentes
    import tema

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

    # Coleta sob demanda. A coleta tambem roda sozinha no atualizar.py (uma vez
    # por dia); este botao existe para forcar quando voce quiser, sem esperar o
    # agendamento. A fonte gratuita da brapi entrega dado de FECHAMENTO, entao
    # apertar varias vezes no mesmo dia traz o mesmo numero - o valor esta' em
    # coletar depois do pregao, ou quando a base ainda nao tem a foto de hoje.
    if st.button("🔄 Atualizar cadeia agora", key="coletar_agora"):
        import subprocess
        from pathlib import Path as _Path
        raiz = _Path(__file__).resolve().parents[2]
        with st.spinner(f"Coletando cadeia de {ativo}..."):
            resultado = subprocess.run(
                [sys.executable, str(raiz / "modules" / "opcoes" / "coleta_opcoes.py"), ativo],
                capture_output=True, text=True, cwd=str(raiz))
        if resultado.returncode == 0:
            st.success(f"Cadeia de {ativo} atualizada.")
            st.rerun()
        else:
            # Mostra a saida real do coletor: sem isso a falha viraria um
            # "nao funcionou" mudo, e a causa mais comum (token ausente para
            # ativo fora do sandbox da brapi) fica invisivel.
            st.error(f"A coleta de {ativo} falhou (codigo {resultado.returncode}).")
            saida = (resultado.stderr or resultado.stdout or "").strip()
            if saida:
                st.code(saida[-1500:])

    und, series = db_opcoes.read_latest_chain(ativo, db_path)
    if not und or not series:
        st.warning(f"Sem dados para {ativo}.")
        return

    rank = ao.analisar(und, series, selic=selic, peso_diff=peso_diff, liquidez_min=int(liq_min))
    regime = ao.regime_volatilidade(series, und["HV_60d"])

    # KPIs
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.markdown(componentes.kpi_card("Spot", f"R$ {und['Spot']:.2f}"), unsafe_allow_html=True)
    k2.markdown(componentes.kpi_card("HV 60d", f"{und['HV_60d']:.1%}"), unsafe_allow_html=True)
    k3.markdown(componentes.kpi_card("Séries", str(len(series))), unsafe_allow_html=True)
    k4.markdown(componentes.kpi_card("Regime vol", regime), unsafe_allow_html=True)
    k5.markdown(componentes.kpi_card("Oportunidades", str(sum(1 for l in rank if abs(l["Diff_pp"]) >= 8))), unsafe_allow_html=True)
    st.caption(f"Taxa livre de risco (Selic): {selic:.2%} · Data ref.: {und['Data_Referencia']}")

    # Top oportunidades - destaque da melhor compra e da melhor venda de vol
    # do ranking ja calculado (nao substitui a tabela completa abaixo, so
    # poupa o usuario de precisar achar a melhor linha sozinho).
    st.markdown("**🎯 Top oportunidades**")
    destaques = ao.destacar_oportunidades(rank)
    oc1, oc2 = st.columns(2)
    if destaques["compra"] is not None:
        oc1.markdown(
            componentes.card_oportunidade("Melhor compra de vol", destaques["compra"]["texto"], "compra"),
            unsafe_allow_html=True,
        )
    else:
        oc1.caption("Sem oportunidade de compra de vol no momento.")
    if destaques["venda"] is not None:
        oc2.markdown(
            componentes.card_oportunidade("Melhor venda de vol", destaques["venda"]["texto"], "venda"),
            unsafe_allow_html=True,
        )
    else:
        oc2.caption("Sem oportunidade de venda de vol no momento.")
    st.caption(DISCLAIMER)

    aba1, aba2, aba3 = st.tabs(["📊 Ranking", "⛓️ Cadeia", "🎯 Estratégias"])

    with aba1:
        if rank:
            import tabelas

            df = pd.DataFrame(rank)[["Codigo_Opcao", "Tipo", "Strike", "Dias",
                "Preco_Mercado", "Justo_BS", "Desconto", "IV", "HV", "Diff_pp",
                "Skew_pp", "Delta", "Sinal"]]
            st.dataframe(tabelas.destacar_ranking_opcoes(df), use_container_width=True, height=380)
            # IV x HV por strike
            calls = [l for l in rank if l["Tipo"] == "CALL"]
            if calls:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=[c["Strike"] for c in calls],
                                         y=[c["IV"] for c in calls],
                                         mode="lines+markers", name="IV (calls)"))
                fig.add_hline(y=und["HV_60d"], line_dash="dash", annotation_text="HV 60d")
                fig.update_layout(title="IV × HV por strike", template=tema.NOME_TEMPLATE_PLOTLY,
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
                        tipo_card = "venda" if "venda" in sugestao["tipo_estrutura"] else "compra"
                        titulo_card = f"{sugestao['ativo']} — {sugestao['tipo_estrutura']}"
                        st.markdown(
                            componentes.card_oportunidade(titulo_card, sugestao["texto"], tipo_card),
                            unsafe_allow_html=True,
                        )
                except Exception as exc:
                    st.warning(f"{ticker}: não foi possível calcular a sugestão de hedge ({exc}).")

    # ---------------- Montar operacao a partir de um cenario ----------------
    # Secao aditiva. A direcao da operacao vem do CENARIO declarado pelo
    # usuario, nunca da ferramenta: o backtest sobre 3,87 milhoes de linhas do
    # COTAHIST mostrou que o Score nao preve retorno (secao 4.4c do
    # ROADMAP_MIH_Opcoes_Handoff.md). O que a ferramenta faz de util aqui e'
    # quantificar o risco exato e mostrar onde o cenario diverge do preco.
    import estruturas_opcoes as eo
    import distribuicao_opcoes as dop
    from datetime import date as _date

    st.markdown("---")
    st.subheader("🧩 Montar operação a partir de um cenário")
    st.caption(
        "O desvio de preço observado (IV vs. HV e vs. o sorriso) **não prevê "
        "retorno** — o backtest sobre 3,87 milhões de linhas não encontrou "
        "vantagem estatística nos ativos líquidos. A direção vem do seu cenário, "
        "não da ferramenta. " + DISCLAIMER
    )

    vencimentos = sorted({linha["Data_Vencimento"] for linha in rank})
    if not vencimentos:
        st.info("Sem vencimentos na cadeia atual.")
        return

    vencimento_escolhido = st.selectbox("Vencimento", vencimentos, key="venc_cenario")
    spot = float(und["Spot"])

    # A distribuicao implicita e' calculada ANTES do formulario porque ela
    # pre-preenche os campos. Ancorar num numero observavel produz cenario
    # melhor calibrado que digitar da intuicao - e' a diferenca entre partir
    # de uma taxa-base e partir do zero.
    do_vencimento = [linha for linha in rank
                     if linha["Data_Vencimento"] == vencimento_escolhido]
    strikes = [linha["Strike"] for linha in do_vencimento]
    ivs = [linha["IV"] for linha in do_vencimento]
    dias = do_vencimento[0]["Dias"] if do_vencimento else 30

    faixas = dop.distribuicao_implicita(strikes, ivs, spot, dias / 365, selic)

    if faixas is not None:
        import numpy as _np
        centros = _np.array([(f.limite_inferior + f.limite_superior) / 2 for f in faixas])
        pesos = _np.array([f.probabilidade for f in faixas])
        pesos = pesos / pesos.sum() if pesos.sum() > 0 else pesos
        acumulado = _np.cumsum(pesos)
        quantis = {q: float(_np.interp(q, acumulado, centros)) for q in (0.1, 0.25, 0.5, 0.75, 0.9)}
        padroes = (("alta", quantis[0.9], 0.25),
                   ("base", quantis[0.5], 0.50),
                   ("baixa", quantis[0.1], 0.25))
        st.markdown("**Seu cenário** — pré-preenchido com o que está embutido no preço")
        st.caption(
            "Os campos vêm da distribuição implícita nas opções deste vencimento. "
            "Ela é **neutra ao risco**: mostra o que está *embutido no preço*, não o "
            "que o mercado *acredita* — parte da diferença é prêmio de risco. "
            "**Edite onde você discorda**: um cenário aceito sem alteração é a visão "
            "do mercado, não a sua, e a aferição registra isso separadamente."
        )
    else:
        quantis = None
        padroes = (("alta", spot * 1.15, 0.25),
                   ("base", spot, 0.50),
                   ("baixa", spot * 0.85, 0.25))
        st.markdown("**Seu cenário** — preço-alvo e probabilidade que você atribui")
        st.caption(
            "Sem distribuição implícita neste vencimento (poucos strikes ou ajuste "
            "inconsistente), então os campos vêm de um padrão simples em torno do spot."
        )

    colunas = st.columns(3)
    entradas = []
    for coluna, (nome, alvo_padrao, prob_padrao) in zip(colunas, padroes):
        with coluna:
            st.markdown(f"*{nome.capitalize()}*")
            entradas.append({
                "Cenario": nome,
                "_alvo_padrao": float(round(alvo_padrao, 2)),
                "_prob_padrao": float(prob_padrao),
                "Preco_Alvo": st.number_input(
                    f"Alvo ({nome})", value=float(round(alvo_padrao, 2)),
                    key=f"alvo_{nome}"),
                "Probabilidade": st.number_input(
                    f"Probabilidade ({nome})", 0.0, 1.0, float(prob_padrao), 0.05,
                    key=f"prob_{nome}"),
                "Premissa": st.text_input(f"Premissa ({nome})", key=f"premissa_{nome}"),
            })

    # Voce mexeu em algo? A afericao precisa distinguir "formei uma visao" de
    # "aceitei o que veio pronto" - medir uma copia da implicita mediria o
    # mercado, nao voce.
    ajustado = any(
        abs(e["Preco_Alvo"] - e["_alvo_padrao"]) > 1e-9
        or abs(e["Probabilidade"] - e["_prob_padrao"]) > 1e-9
        for e in entradas
    )

    soma = sum(e["Probabilidade"] for e in entradas)
    if abs(soma - 1.0) > 0.01:
        st.warning(f"As probabilidades somam {soma:.0%} — ajuste para 100%.")
    else:
        if not ajustado and quantis is not None:
            st.info(
                "Você ainda não alterou nenhum valor. Pode salvar assim, mas o "
                "cenário será registrado como *não ajustado* — ele reproduz o preço, "
                "então a aferição não o conta como visão sua."
            )
        if st.button("Salvar cenário"):
            db_opcoes.init_schema_cenarios(db_path)
            for cenario in entradas:
                db_opcoes.gravar_cenario(
                    ativo, str(_date.today()), vencimento_escolhido, cenario["Cenario"],
                    cenario["Preco_Alvo"], cenario["Probabilidade"],
                    cenario["Premissa"], db_path, ajustado=ajustado)
            if quantis is not None:
                db_opcoes.gravar_implicita(
                    ativo, str(_date.today()), vencimento_escolhido,
                    quantis[0.1], quantis[0.25], quantis[0.5], quantis[0.75], quantis[0.9],
                    db_path)
            st.success(
                "Cenário salvo com a data de declaração e a implícita do momento — "
                "é o que permite comparar depois se você foi melhor calibrado que o preço."
            )

    db_opcoes.init_schema_cenarios(db_path)
    cenarios_salvos = db_opcoes.ler_cenarios(ativo, vencimento_escolhido, db_path)
    if not cenarios_salvos:
        st.info("Declare e salve um cenário acima para ver as operações.")
        return

    if faixas is None:
        st.info(
            "Não foi possível extrair a distribuição implícita deste vencimento "
            "(menos de 4 strikes distintos, ou o ajuste do sorriso ficou "
            "inconsistente com não-arbitragem). As estruturas abaixo continuam "
            "válidas — só a comparação de probabilidades fica indisponível."
        )
    else:
        st.markdown("**Embutido no preço vs. seu cenário**")
        st.caption(
            "A distribuição implícita é **neutra ao risco**: ela embute prêmio de "
            "risco de variância, que para ações infla a cauda de baixa. Mostra o "
            "que está *embutido no preço*, não o que o mercado *acredita* — parte "
            "da divergência é remuneração de risco, não discordância de opinião."
        )
        comparacao = dop.comparar_distribuicoes(faixas, cenarios_salvos)
        st.dataframe(pd.DataFrame([{
            "Faixa": f"R$ {linha['limite_inferior']:.2f} – {linha['limite_superior']:.2f}",
            "Embutido no preço": f"{linha['implicita']:.1%}",
            "Seu cenário": f"{linha['cenario']:.1%}",
            "Divergência (p.p.)": f"{linha['divergencia'] * 100:+.1f}",
        } for linha in comparacao]), use_container_width=True, hide_index=True)

    # A direcao vem do CENARIO declarado, nunca da ferramenta.
    alvo_base = next((float(c["Preco_Alvo"]) for c in cenarios_salvos
                      if c["Cenario"] == "base"), spot)
    if alvo_base > spot * 1.02:
        tese_direcao = "alta"
    elif alvo_base < spot * 0.98:
        tese_direcao = "baixa"
    else:
        tese_direcao = "neutra"

    iv_media = sum(ivs) / len(ivs) if ivs else 0.0
    tese_vol = "cara" if iv_media > float(und["HV_60d"]) else "barata"

    # Posicao na carteira entra como VIABILIDADE (habilita venda coberta),
    # nunca como visao direcional inferida: estar long por razao estrutural,
    # querendo proteger, e' o oposto de estar long por achar que sobe.
    tem_posicao = False
    if carteira_df is not None and not carteira_df.empty and "ativo" in carteira_df:
        tickers = {str(t).strip().upper() for t in carteira_df["ativo"]}
        tem_posicao = any(t.startswith(ativo[:4].upper()) for t in tickers)

    montadas, recusas = eo.montar_estruturas(
        do_vencimento, spot, vencimento_escolhido, tese_vol, tese_direcao,
        liquidez_min=int(liq_min), tem_posicao=tem_posicao)

    st.markdown(
        f"**Operações viáveis** — vol {tese_vol}, direção *{tese_direcao}* (do seu cenário)"
    )

    def _ve_implicito_texto(dop_mod, estrutura, faixas_calc):
        """Um traco quando o VE implicito seria enganoso - ver
        distribuicao_opcoes.valor_esperado_implicito()."""
        if faixas_calc is None:
            return "—"
        valor = dop_mod.valor_esperado_implicito(
            estrutura.pernas, faixas_calc, estrutura.perfil)
        return "—" if valor is None else f"R$ {valor:,.2f}"

    linhas_tabela = []
    for estrutura in montadas:
        perfil = estrutura.perfil
        linhas_tabela.append({
            "Estrutura": estrutura.nome,
            "Pernas": " / ".join(f"{p.lado} {p.tipo} {p.strike:.2f}"
                                 for p in estrutura.pernas),
            "Prêmio líquido": f"R$ {perfil.premio_liquido:,.2f}",
            "Perda máxima": ("ILIMITADA" if perfil.perda_maxima is None
                             else f"R$ {perfil.perda_maxima:,.2f}"),
            "Ganho máximo": ("ILIMITADO" if perfil.ganho_maximo is None
                             else f"R$ {perfil.ganho_maximo:,.2f}"),
            "Breakevens": ", ".join(f"{b:.2f}" for b in perfil.breakevens),
            "VE sob seu cenário": f"R$ {dop.valor_esperado(estrutura.pernas, cenarios_salvos):,.2f}",
            "VE embutido no preço": _ve_implicito_texto(dop, estrutura, faixas),
        })

    if linhas_tabela:
        st.dataframe(pd.DataFrame(linhas_tabela), use_container_width=True, hide_index=True)
        st.caption(
            "As duas últimas colunas mostram o mesmo payoff sob as duas visões — a "
            "diferença é o ganho que existe **se a sua premissa estiver certa**. A "
            "ferramenta não elege uma estrutura vencedora. **Perda máxima é no "
            "vencimento**: não protege de marcação a mercado adversa nem de chamada "
            "de margem antes disso. Margem exigida não é calculada aqui — consulte "
            "sua corretora."
        )
        if faixas is not None and dop.massa_total(faixas) < dop.MASSA_MINIMA_CONFIAVEL:
            st.caption(
                f"A distribuição implícita cobre {dop.massa_total(faixas):.1%} da "
                "probabilidade — o resto está nas caudas, fora do intervalo de "
                "strikes listados. Por isso o VE embutido no preço aparece como "
                "«—» nas estruturas de risco ilimitado: a cauda que falta é "
                "exatamente onde elas perdem, e o número ficaria inflado."
            )
    else:
        st.info("Nenhuma estrutura do catálogo é viável nesta cadeia.")

    if recusas:
        with st.expander(f"{len(recusas)} estruturas não puderam ser montadas"):
            for motivo in recusas:
                st.write(f"- {motivo}")

    # ---------------- Afericao dos cenarios ja fechados ----------------
    # Mede o DECLARANTE, nao o mercado: "quando voce diz 25%, acontece 25% das
    # vezes?" e' pergunta bem-posta, ao contrario de "o Score preve retorno?".
    # As declaracoes sao fechadas automaticamente pelo passo diario
    # fechar_cenarios.py, usando o spot da data do vencimento.
    import afericao_cenarios as af
    import sqlite3 as _sqlite3

    st.markdown("---")
    st.subheader("📈 Aferição — seus cenários contra o que aconteceu")

    con_af = _sqlite3.connect(db_path or db_opcoes.DB_PATH)
    con_af.row_factory = _sqlite3.Row
    try:
        linhas_af = [dict(r) for r in con_af.execute(
            "SELECT * FROM opcoes_cenarios WHERE Ativo=? AND Preco_Realizado IS NOT NULL "
            "ORDER BY Data_Declaracao, Data_Vencimento", (ativo,)).fetchall()]
    finally:
        con_af.close()

    # Agrupa as tres linhas de cada declaracao
    por_declaracao = {}
    for linha in linhas_af:
        chave = (linha["Data_Declaracao"], linha["Data_Vencimento"])
        por_declaracao.setdefault(chave, {"cenarios": [], "Preco_Realizado": None,
                                           "Ajustado": linha.get("Ajustado", 0)})
        por_declaracao[chave]["cenarios"].append(linha)
        por_declaracao[chave]["Preco_Realizado"] = linha["Preco_Realizado"]

    completas = [d for d in por_declaracao.values() if len(d["cenarios"]) == 3]
    ajustadas = [d for d in completas if d.get("Ajustado")]
    nao_ajustadas = [d for d in completas if not d.get("Ajustado")]

    if not completas:
        st.info(
            f"Nenhuma declaração de {ativo} chegou ao vencimento ainda. A aferição "
            "aparece aqui conforme os cenários vencem — o fechamento é automático, "
            "pelo passo diário de atualização."
        )
    else:
        tabela_af = af.tabela_calibracao(ajustadas)
        st.caption(af.resumir_afericao(tabela_af, len(ajustadas)))
        if tabela_af:
            st.dataframe(pd.DataFrame([{
                "Região": l["regiao"],
                "Você declarou": f"{l['prob_declarada']:.0%}",
                "Ocorreu": f"{l['frequencia']:.0%}",
                "Vezes": f"{l['ocorrencias']} de {l['n']}",
            } for l in tabela_af]), use_container_width=True, hide_index=True)
        if nao_ajustadas:
            st.caption(
                f"{len(nao_ajustadas)} declaração(ões) fora desta conta por não terem "
                "sido ajustadas: reproduziam a distribuição implícita, então medi-las "
                "mediria o preço, não você."
            )
        st.caption(
            "Calibração não implica lucro: acertar a distribuição diz que sua "
            "descrição do futuro foi honesta, não que havia vantagem a capturar."
        )
