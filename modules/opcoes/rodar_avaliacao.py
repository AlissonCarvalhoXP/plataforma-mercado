"""Roda a avaliacao de calibracao do modelo FHS sobre os dados reais.

Este script E' o gate: se o modelo nao vencer o benchmark incondicional e nao
passar na uniformidade do PIT, ele NAO entra em producao e a declaracao manual
de cenarios permanece (secao 5.5 da spec).

Uso:
    python modules/opcoes/rodar_avaliacao.py --horizonte 45
    python modules/opcoes/rodar_avaliacao.py --horizonte 45 --ativos PETR VALE ITUB
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import db_opcoes
import modelo_cenarios as mc
import avaliacao_previsoes as av

TAXA_PADRAO = 0.1415


def avaliar(ativos: list[str], horizonte: int, taxa: float, db_path=None) -> None:
    todos: list[dict] = []
    for ativo in ativos:
        precos = db_opcoes.carregar_precos(ativo, db_path)
        motivo = mc.validar_serie(precos) if precos else "sem serie no banco"
        if motivo:
            print(f"{ativo}: RECUSADO - {motivo}", flush=True)
            continue
        resultados = av.walk_forward(precos, horizonte, taxa, semente=42)
        resumo = av.resumir_avaliacao(resultados)
        print(f"{ativo}: {resumo['n_janelas']} janelas | "
              f"CRPS {resumo['crps_modelo']:.4f} vs {resumo['crps_benchmark']:.4f} "
              f"({resumo['ganho_percentual']:+.1f}%)", flush=True)
        todos.extend(resultados)

    print("\n" + "=" * 70)
    print("VEREDITO AGREGADO (todos os ativos)")
    print("=" * 70)
    resumo_geral = av.resumir_avaliacao(todos)
    print(resumo_geral["veredito"])
    print(f"\njanelas independentes no total: {resumo_geral['n_janelas']}")

    aprovado = (resumo_geral["ganho_percentual"] or 0) > 0 and (
        resumo_geral["pit_ks_valor_p"] is None or resumo_geral["pit_ks_valor_p"] >= 0.05)
    print("\nGATE:", "APROVADO - modelo pode ir para producao" if aprovado
          else "REPROVADO - manter cenario manual, nao integrar o modelo")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizonte", type=int, default=45,
                    help="dias uteis ate' o vencimento (default 45)")
    ap.add_argument("--taxa", type=float, default=TAXA_PADRAO)
    ap.add_argument("--ativos", nargs="*", default=["PETR", "VALE", "ITUB", "BBAS", "BBDC"])
    args = ap.parse_args()
    avaliar(args.ativos, args.horizonte, args.taxa)
