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

Sem dependência de rede: lê tudo de opcoes_historico já coletado.

NOTA (2026-08-30): o score não usa mais "desconto" (preço-espaço) - só
"diff" (IV vs. HV) e "skew" (IV desta opção vs. sorriso do dia, ajustado a
partir de outras séries do mesmo dia/Tipo em opcoes_historico). Ver
docs/superpowers/specs/2026-08-30-score-opcoes-sem-desconto-design.md para o
raciocínio completo - o sweep de peso_diff sozinho nunca convergia porque
desconto e diff são colineares por construção (Black-Scholes é monotônico em
volatilidade).
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


def rodar_backtest(hist: list[dict], peso_diff: float, peso_skew: float = 0.6,
                    horizonte: int = 5, hv_janela: int = 60) -> Resultado:
    """Roda o backtest para UMA combinação (peso_diff, peso_skew) sobre todas
    as séries, usando a mesma calcular_score() do screener ao vivo."""
    por_serie = defaultdict(list)
    for h in hist:
        por_serie[h["Codigo_Opcao"]].append(h)

    sorrisos = _construir_sorrisos_por_dia(hist)

    retornos, acertos = [], []
    ret_buy, ret_sell = [], []

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

            # retorno futuro da OPÇÃO no horizonte
            fut = pts[i + horizonte]["Preco_Opcao"]
            ret_opcao = (fut - po) / po if po > 0 else 0.0

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
        return Resultado(peso_diff, peso_skew, 0, 0, 0, 0, 0, 0)

    wr = float(np.mean(acertos))
    rm = float(np.mean(retornos))
    # expectativa = média ponderada (win*ganho_medio + loss*perda_media)
    ganhos = [r for r in retornos if r > 0]
    perdas = [r for r in retornos if r <= 0]
    exp = (wr * (np.mean(ganhos) if ganhos else 0)
           + (1 - wr) * (np.mean(perdas) if perdas else 0))
    return Resultado(
        peso_diff=peso_diff, peso_skew=peso_skew, n_sinais=len(retornos), win_rate=round(wr, 4),
        retorno_medio=round(rm, 4), expectativa=round(float(exp), 4),
        retorno_buy=round(float(np.mean(ret_buy)) if ret_buy else 0, 4),
        retorno_sell=round(float(np.mean(ret_sell)) if ret_sell else 0, 4),
    )


# ---------------- sweep de pesos (calibração) ----------------
def calibrar(ativo="PETR4", pesos_diff=None, pesos_skew=None, horizonte=5, db_path=None):
    """Testa uma grade (peso_diff × peso_skew) e devolve o ranking por
    expectativa. Grade 2D porque agora são 2 eixos genuinamente independentes
    a calibrar - o sweep antigo (só peso_diff) nunca convergia porque
    desconto e diff eram colineares (ver módulo docstring)."""
    hist = carregar_historico(ativo, db_path)
    if not hist:
        return [], 0
    pesos_diff = pesos_diff or [0.0, 0.3, 0.6, 1.0]
    pesos_skew = pesos_skew or [0.0, 0.3, 0.6, 1.0]
    resultados = [rodar_backtest(hist, wd, ws, horizonte)
                  for wd in pesos_diff for ws in pesos_skew]
    resultados = [r for r in resultados if r.n_sinais > 0]
    resultados.sort(key=lambda r: r.expectativa, reverse=True)
    return resultados, len({h["Codigo_Opcao"] for h in hist})


def imprimir(resultados, n_series):
    print(f"\n{'='*94}\nCALIBRAÇÃO DO SCORE — {n_series} séries reais\n{'='*94}")
    print(f"{'peso_diff':>10}{'peso_skew':>11}{'n_sinais':>10}{'win_rate':>10}"
          f"{'ret_medio':>11}{'expectativa':>13}{'ret_buy':>9}{'ret_sell':>10}")
    for r in resultados:
        print(f"{r.peso_diff:>10.1f}{r.peso_skew:>11.1f}{r.n_sinais:>10}{r.win_rate:>9.1%}"
              f"{r.retorno_medio:>10.2%}{r.expectativa:>12.3%}"
              f"{r.retorno_buy:>8.1%}{r.retorno_sell:>9.1%}")
    if resultados:
        best = resultados[0]
        print(f"\n>>> Melhor combinação: peso_diff={best.peso_diff}, peso_skew={best.peso_skew} "
              f"(expectativa {best.expectativa:.3%}, win rate {best.win_rate:.1%})")


if __name__ == "__main__":
    res, n = calibrar()
    if not res:
        print("Sem histórico. Rode coleta_opcoes_historico.py primeiro.")
    else:
        imprimir(res, n)
