"""Motor de backtest do screener de opções — varre VÁRIAS séries reais.

Objetivo (pendência do handoff): calibrar os pesos do Score usando dados
históricos reais (tabela opcoes_historico), em vez de valores arbitrários.

Lógica:
  1. Para cada série e cada dia, calcula o score (gap IV×HV + skew do sorriso).
  2. O sinal (COMPRAR_VOL / VENDER_VOL) é uma aposta sobre o comportamento da
     opção nos próximos `horizonte` pregões.
  3. Confere se a aposta se confirmou (retorno da opção no horizonte).
  4. Agrega win rate, retorno médio, expectativa — e faz um sweep 2D de pesos
     (peso_diff × peso_skew).
  5. Compara contra uma linha de base explícita ("sempre vender", que captura
     o decaimento médio de theta sozinho) e reporta o EDGE real acima dela -
     ver seção "viés de theta-decay" abaixo.

Sem dependência de rede: lê tudo de opcoes_historico já coletado.

NOTA (2026-08-30): o score não usa mais "desconto" (preço-espaço) - só
"diff" (IV vs. HV) e "skew" (IV desta opção vs. sorriso do dia, ajustado a
partir de outras séries do mesmo dia/Tipo em opcoes_historico). Ver
docs/superpowers/specs/2026-08-30-score-opcoes-sem-desconto-design.md para o
raciocínio completo - o sweep de peso_diff sozinho nunca convergia porque
desconto e diff são colineares por construção (Black-Scholes é monotônico em
volatilidade).

NOTA (2026-08-30) — viés de theta-decay: ao validar a correção acima, a
combinação "vencedora" do sweep (peso_diff=0, peso_skew=0) era um artefato -
com os dois pesos zerados o score fica exatamente 0.0 pra toda linha,
`score > 0` nunca é verdadeiro, e todo sinal cai em "VENDER_VOL" por padrão.
O "94% de acerto" capturava o decaimento médio do preço da opção com o tempo
(theta), não informação real do Diff/Skew - viés clássico de backtest de
opções (apostar sempre contra o preço "acerta" por decaimento, não por
sinal). Duas correções aplicadas: (1) `score_minimo` exclui pontos com score
~0 da contagem de sinais, em vez de default-ar pra VENDER; (2) toda
`Resultado` agora reporta `expectativa_base_vender` (o que "sempre vender"
teria dado nos MESMOS pontos) e `edge` (expectativa real menos essa base) -
`calibrar()` ranqueia por `edge`, não por `expectativa` bruta, pra não
premiar combinações que só capturam theta.
"""
from __future__ import annotations
import os, sys, sqlite3, math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import db_opcoes
from analises_opcoes import PRECO_MINIMO_RELEVANTE, ajustar_sorriso, calcular_score


def _dias_ate(venc_str, data_str):
    try:
        return max(1, (date.fromisoformat(venc_str[:10]) - date.fromisoformat(data_str[:10])).days)
    except Exception:
        return 30


# ---------------- carga do histórico ----------------
def carregar_historico(ativo="PETR4", db_path=None):
    con = sqlite3.connect(db_path or db_opcoes.DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM opcoes_historico WHERE Ativo_Objeto=? ORDER BY Codigo_Opcao, Data",
        (ativo,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


def _hv_movel(precos_ativo, i, janela=60):
    """HV anualizada dos últimos `janela` retornos até o índice i."""
    if i < 2:
        return None
    serie = precos_ativo[max(0, i - janela):i + 1]
    if len(serie) < 3:
        return None
    r = np.diff(np.log(serie))
    return float(np.std(r, ddof=1) * math.sqrt(252))


def _construir_sorrisos_por_dia(hist: list[dict]):
    """Agrupa o histórico por (Data, Tipo) e ajusta o sorriso (strike->iv) de
    cada grupo com pontos suficientes - mesma função usada pelo screener ao
    vivo (analises_opcoes.ajustar_sorriso), pra manter o backtest fiel ao que
    roda em produção. Chave ausente/None = sem sorriso ajustável naquele
    dia/tipo (poucos strikes negociando)."""
    pontos = defaultdict(list)
    for h in hist:
        if h.get("IV") and h.get("Strike"):
            pontos[(h["Data"], h.get("Tipo", "CALL"))].append((h["Strike"], h["IV"]))
    return {chave: ajustar_sorriso(pts) for chave, pts in pontos.items()}


# ---------------- backtest de uma combinação de pesos ----------------
@dataclass
class Resultado:
    peso_diff: float
    peso_skew: float
    n_sinais: int
    win_rate: float
    retorno_medio: float
    expectativa: float
    retorno_buy: float
    retorno_sell: float
    expectativa_base_vender: float
    edge: float


def rodar_backtest(hist: list[dict], peso_diff: float, peso_skew: float = 0.6,
                    horizonte: int = 5, hv_janela: int = 60,
                    score_minimo: float = 1e-6) -> Resultado:
    """Roda o backtest para UMA combinação (peso_diff, peso_skew) sobre todas
    as séries, usando a mesma calcular_score() do screener ao vivo.

    `score_minimo`: pontos com |score| <= score_minimo são excluídos da
    contagem de sinais (nem comprar, nem vender) - sem isso, quando os pesos
    zeram o score pra toda linha, tudo cairia em "vender" por padrão e o
    resultado mediria só o decaimento médio de theta, não informação real
    (ver nota do módulo sobre o viés de theta-decay)."""
    por_serie = defaultdict(list)
    for h in hist:
        por_serie[h["Codigo_Opcao"]].append(h)

    sorrisos = _construir_sorrisos_por_dia(hist)

    retornos, acertos = [], []
    ret_buy, ret_sell = [], []
    retornos_brutos = []  # ret_opcao de TODO ponto que gerou sinal, sem aplicar direcao - base "sempre vender"

    for symbol, pts in por_serie.items():
        pts = [p for p in pts if p.get("Preco_Opcao") and p.get("IV")]
        if len(pts) < horizonte + 3:
            continue
        precos_ativo = [p["Preco_Ativo"] for p in pts]

        for i in range(2, len(pts) - horizonte):
            p = pts[i]
            hv = _hv_movel(precos_ativo, i, hv_janela)
            if not hv or hv <= 0:
                continue
            iv = p["IV"]
            po = p["Preco_Opcao"]
            if not po or po < PRECO_MINIMO_RELEVANTE:
                continue  # residual de fim de vida - mesma guarda do screener (analisar())

            diff = (iv - hv) * 100
            sorriso = sorrisos.get((p["Data"], p.get("Tipo", "CALL")))
            strike = p.get("Strike")
            skew = (iv - sorriso(strike)) * 100 if (sorriso and strike) else 0.0

            liq = 0  # histórico analytics não traz volume; peso_liq=0 aqui
            s = calcular_score(diff, skew, liq, peso_diff, peso_skew, peso_liq=0.0)
            if abs(s) <= score_minimo:
                continue  # sem sinal de verdade - nao conta nem como compra nem como venda

            # retorno futuro da OPÇÃO no horizonte
            fut = pts[i + horizonte]["Preco_Opcao"]
            ret_opcao = (fut - po) / po if po > 0 else 0.0
            retornos_brutos.append(ret_opcao)

            # sinal: score>0 => COMPRAR vol (aposta que a opção sobe)
            #        score<0 => VENDER vol  (aposta que a opção cai)
            if s > 0:
                pnl = ret_opcao          # comprado ganha se subir
                ret_buy.append(pnl)
            else:
                pnl = -ret_opcao         # vendido ganha se cair
                ret_sell.append(pnl)

            retornos.append(pnl)
            acertos.append(1 if pnl > 0 else 0)

    if not retornos:
        return Resultado(peso_diff, peso_skew, 0, 0, 0, 0, 0, 0, 0, 0)

    wr = float(np.mean(acertos))
    rm = float(np.mean(retornos))
    # expectativa = média ponderada (win*ganho_medio + loss*perda_media)
    ganhos = [r for r in retornos if r > 0]
    perdas = [r for r in retornos if r <= 0]
    exp = (wr * (np.mean(ganhos) if ganhos else 0)
           + (1 - wr) * (np.mean(perdas) if perdas else 0))

    # linha de base: "sempre vender" nos MESMOS pontos que geraram sinal aqui -
    # isola o que e' decaimento medio de theta do que e' informacao real do score
    exp_base_vender = -float(np.mean(retornos_brutos))
    edge = round(float(exp) - exp_base_vender, 4)

    return Resultado(
        peso_diff=peso_diff, peso_skew=peso_skew, n_sinais=len(retornos), win_rate=round(wr, 4),
        retorno_medio=round(rm, 4), expectativa=round(float(exp), 4),
        retorno_buy=round(float(np.mean(ret_buy)) if ret_buy else 0, 4),
        retorno_sell=round(float(np.mean(ret_sell)) if ret_sell else 0, 4),
        expectativa_base_vender=round(exp_base_vender, 4), edge=edge,
    )


# ---------------- sweep de pesos (calibração) ----------------
def calibrar(ativo="PETR4", pesos_diff=None, pesos_skew=None, horizonte=5, db_path=None):
    """Testa uma grade (peso_diff × peso_skew) e devolve o ranking por EDGE
    (expectativa acima da linha de base "sempre vender"), não por expectativa
    bruta - ranquear pela bruta premiaria combinações que só capturam
    decaimento de theta (ver nota do módulo). Grade 2D porque agora são 2
    eixos genuinamente independentes a calibrar - o sweep antigo (só
    peso_diff) nunca convergia porque desconto e diff eram colineares."""
    hist = carregar_historico(ativo, db_path)
    if not hist:
        return [], 0
    pesos_diff = pesos_diff or [0.0, 0.3, 0.6, 1.0]
    pesos_skew = pesos_skew or [0.0, 0.3, 0.6, 1.0]
    resultados = [rodar_backtest(hist, wd, ws, horizonte)
                  for wd in pesos_diff for ws in pesos_skew]
    resultados = [r for r in resultados if r.n_sinais > 0]
    resultados.sort(key=lambda r: r.edge, reverse=True)
    return resultados, len({h["Codigo_Opcao"] for h in hist})


def imprimir(resultados, n_series):
    print(f"\n{'='*104}\nCALIBRAÇÃO DO SCORE — {n_series} séries reais\n{'='*104}")
    print(f"{'peso_diff':>10}{'peso_skew':>11}{'n_sinais':>10}{'win_rate':>10}"
          f"{'ret_medio':>11}{'expectativa':>13}{'base_vender':>14}{'edge':>10}")
    for r in resultados:
        print(f"{r.peso_diff:>10.1f}{r.peso_skew:>11.1f}{r.n_sinais:>10}{r.win_rate:>9.1%}"
              f"{r.retorno_medio:>10.2%}{r.expectativa:>12.3%}"
              f"{r.expectativa_base_vender:>13.3%}{r.edge:>10.3%}")
    if resultados:
        best = resultados[0]
        print(f"\n>>> Melhor combinação por EDGE: peso_diff={best.peso_diff}, peso_skew={best.peso_skew} "
              f"(edge {best.edge:.3%} acima de 'sempre vender', expectativa {best.expectativa:.3%}, "
              f"win rate {best.win_rate:.1%})")


if __name__ == "__main__":
    # Auto-teste: confere que o viés de theta-decay foi corrigido, com um
    # historico sintetico controlado (sem depender de rede nem do banco real).
    # Uma unica serie com preco caindo por decaimento de theta e o ativo
    # oscilando de leve (pra HV nao ficar zerada) - sem outras series no
    # mesmo dia/Tipo, entao skew fica sempre 0 (isola o teste no eixo diff).
    precos_opcao = [1.00, 0.97, 0.94, 0.91, 0.88, 0.85, 0.82, 0.79,
                    0.76, 0.73, 0.70, 0.67, 0.64, 0.61, 0.58, 0.55]
    precos_ativo_teste = [40.0, 40.2, 39.8, 40.1, 39.9, 40.3, 39.7, 40.0,
                          40.2, 39.9, 40.1, 39.8, 40.0, 40.2, 39.9, 40.1]
    ivs_teste = [0.30, 0.31, 0.29, 0.30, 0.32, 0.29, 0.31, 0.30,
                 0.29, 0.31, 0.30, 0.32, 0.29, 0.30, 0.31, 0.30]
    hist_teste = [
        {"Codigo_Opcao": "TESTE1", "Ativo_Objeto": "TESTE", "Tipo": "CALL", "Strike": 40.0,
         "Data_Vencimento": "2026-12-01", "Data": f"2026-10-{dia:02d}",
         "Preco_Ativo": preco_ativo, "Preco_Opcao": preco_opcao, "IV": iv,
         "Taxa_Livre_Risco": 0.14}
        for dia, (preco_ativo, preco_opcao, iv)
        in enumerate(zip(precos_ativo_teste, precos_opcao, ivs_teste), start=1)
    ]

    # Caso 1: pesos zerados -> score sempre 0.0 -> score_minimo exclui todo
    # mundo (nem compra, nem vende) em vez de tudo cair em VENDER por padrao
    r_zerado = rodar_backtest(hist_teste, peso_diff=0.0, peso_skew=0.0)
    assert r_zerado.n_sinais == 0
    print("[OK] Caso 1: pesos zerados -> score_minimo exclui os pontos (nao finge sinal de venda).")

    # Caso 2: com peso real, sinais aparecem e o edge e' calculado de forma
    # autoconsistente (expectativa - base_vender)
    r_real = rodar_backtest(hist_teste, peso_diff=0.6, peso_skew=0.6)
    assert r_real.n_sinais > 0
    assert round(r_real.expectativa - r_real.expectativa_base_vender, 4) == r_real.edge
    print("[OK] Caso 2: com peso real, sinais aparecem e edge = expectativa - base_vender.")

    print("\nTodos os casos passaram.\n")

    res, n = calibrar()
    if not res:
        print("Sem histórico. Rode coleta_opcoes_historico.py primeiro.")
    else:
        imprimir(res, n)
