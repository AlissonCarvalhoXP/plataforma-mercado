"""Motor de backtest do screener de opções — varre VÁRIAS séries reais.

Objetivo (pendência do handoff): calibrar o peso do Diff no score usando dados
históricos reais (tabela opcoes_historico), em vez do 0,6 arbitrário.

Lógica:
  1. Para cada série e cada dia, calcula o score (desconto + assimetria IV-HV).
  2. O sinal (COMPRAR_VOL / VENDER_VOL) é uma aposta sobre o comportamento da
     opção nos próximos `horizonte` pregões.
  3. Confere se a aposta se confirmou (retorno da opção no horizonte).
  4. Agrega win rate, retorno médio, expectativa — e faz um sweep de pesos.

Sem dependência de rede: lê tudo de opcoes_historico já coletado.
"""
from __future__ import annotations
import os, sys, sqlite3, math
from dataclasses import dataclass
from datetime import date
import numpy as np
from scipy.stats import norm
sys.path.insert(0, os.path.dirname(__file__))
import db_opcoes


def _bs(tipo, S, K, T, r, sig):
    """Preço Black-Scholes para reprecificar a opção com a HV (preço justo)."""
    if T <= 0 or sig <= 0:
        return max(S - K, 0) if tipo == "CALL" else max(K - S, 0)
    d1 = (math.log(S / K) + (r + sig * sig / 2) * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    if tipo == "CALL":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


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


# ---------------- score (mesma fórmula do screener) ----------------
def score_linha(preco_opcao, preco_justo, iv, hv, liq, peso_diff, peso_liq=0.0):
    desconto = (preco_justo - preco_opcao) / preco_justo if preco_justo > 0 else 0.0
    diff = (iv - hv) * 100
    return desconto * 100 - diff * peso_diff + math.log1p(max(0, liq)) * peso_liq


# ---------------- backtest de um peso ----------------
@dataclass
class Resultado:
    peso_diff: float
    n_sinais: int
    win_rate: float
    retorno_medio: float
    expectativa: float
    retorno_buy: float
    retorno_sell: float


def rodar_backtest(hist: list[dict], peso_diff: float,
                   horizonte: int = 5, hv_janela: int = 60) -> Resultado:
    """Roda o backtest para UM valor de peso_diff sobre todas as séries."""
    from collections import defaultdict
    por_serie = defaultdict(list)
    for h in hist:
        por_serie[h["Codigo_Opcao"]].append(h)

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
            # preço justo pela HV via Black-Scholes real (mesma escolha do screener)
            iv = p["IV"]
            po = p["Preco_Opcao"]
            S_now = p["Preco_Ativo"]
            K = p.get("Strike") or S_now
            r_now = p.get("Taxa_Livre_Risco") or 0.1415
            T = _dias_ate(p.get("Data_Vencimento", ""), p["Data"]) / 365
            preco_justo = _bs(p.get("Tipo", "CALL"), S_now, K, T, r_now, hv)
            liq = 0  # histórico analytics não traz volume; peso_liq=0 aqui
            s = score_linha(po, preco_justo, iv, hv, liq, peso_diff)

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
        return Resultado(peso_diff, 0, 0, 0, 0, 0, 0)

    wr = float(np.mean(acertos))
    rm = float(np.mean(retornos))
    # expectativa = média ponderada (win*ganho_medio + loss*perda_media)
    ganhos = [r for r in retornos if r > 0]
    perdas = [r for r in retornos if r <= 0]
    exp = (wr * (np.mean(ganhos) if ganhos else 0)
           + (1 - wr) * (np.mean(perdas) if perdas else 0))
    return Resultado(
        peso_diff=peso_diff, n_sinais=len(retornos), win_rate=round(wr, 4),
        retorno_medio=round(rm, 4), expectativa=round(float(exp), 4),
        retorno_buy=round(float(np.mean(ret_buy)) if ret_buy else 0, 4),
        retorno_sell=round(float(np.mean(ret_sell)) if ret_sell else 0, 4),
    )


# ---------------- sweep de pesos (calibração) ----------------
def calibrar(ativo="PETR4", pesos=None, horizonte=5, db_path=None):
    """Testa vários pesos e retorna o ranking por expectativa."""
    hist = carregar_historico(ativo, db_path)
    if not hist:
        return [], 0
    pesos = pesos or [0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2]
    resultados = [rodar_backtest(hist, w, horizonte) for w in pesos]
    resultados = [r for r in resultados if r.n_sinais > 0]
    resultados.sort(key=lambda r: r.expectativa, reverse=True)
    return resultados, len({h["Codigo_Opcao"] for h in hist})


def imprimir(resultados, n_series):
    print(f"\n{'='*72}\nCALIBRAÇÃO DO SCORE — {n_series} séries reais\n{'='*72}")
    print(f"{'peso_diff':>10}{'n_sinais':>10}{'win_rate':>10}"
          f"{'ret_medio':>11}{'expectativa':>13}{'ret_buy':>9}{'ret_sell':>10}")
    for r in resultados:
        print(f"{r.peso_diff:>10.1f}{r.n_sinais:>10}{r.win_rate:>9.1%}"
              f"{r.retorno_medio:>10.2%}{r.expectativa:>12.3%}"
              f"{r.retorno_buy:>8.1%}{r.retorno_sell:>9.1%}")
    if resultados:
        best = resultados[0]
        print(f"\n>>> Melhor peso_diff = {best.peso_diff} "
              f"(expectativa {best.expectativa:.3%}, win rate {best.win_rate:.1%})")


if __name__ == "__main__":
    res, n = calibrar()
    if not res:
        print("Sem histórico. Rode coleta_opcoes_historico.py primeiro.")
    else:
        imprimir(res, n)
