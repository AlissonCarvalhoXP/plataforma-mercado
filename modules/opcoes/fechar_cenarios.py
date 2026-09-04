"""Fecha as declaracoes de cenario cujo vencimento ja passou.

Roda como passo do atualizar.py, uma vez por dia. Para cada declaracao vencida
e ainda sem resultado, busca o spot daquela data nos snapshots diarios e grava.

Por que automatico: sem isso, a afericao dependeria de o usuario lembrar de
voltar na tela meses depois para registrar o que aconteceu - e uma medicao que
depende de disciplina humana para existir simplesmente nao acontece.

Uso:
    python modules/opcoes/fechar_cenarios.py
"""
from __future__ import annotations
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_opcoes


def fechar(hoje: str | None = None, db_path=None) -> tuple[int, int]:
    """Fecha o que der. Devolve (fechadas, sem_cotacao).

    Uma declaracao vencida cujo spot daquele dia nao esta' no banco fica em
    aberto de proposito: aproximar com a cotacao de outro dia inventaria o
    resultado que a afericao existe para medir. Ela sera' fechada assim que a
    cotacao aparecer, ou nunca - o que e' melhor que fechar errado."""
    db_opcoes.init_schema_cenarios(db_path)
    hoje = hoje or str(date.today())
    pendentes = db_opcoes.declaracoes_a_fechar(hoje, db_path)

    fechadas = 0
    sem_cotacao = 0
    for ativo, data_declaracao, vencimento in pendentes:
        spot = db_opcoes.spot_na_data(ativo, vencimento, db_path)
        if spot is None:
            sem_cotacao += 1
            print(f"  {ativo} {vencimento}: sem cotacao no banco para essa data - "
                  f"fica em aberto (nao aproximo com outro dia)")
            continue
        db_opcoes.registrar_realizado_cenario(ativo, data_declaracao, vencimento,
                                               spot, db_path)
        fechadas += 1
        print(f"  {ativo} {vencimento}: fechada com spot R$ {spot:.2f}")

    return fechadas, sem_cotacao


if __name__ == "__main__":
    import tempfile

    # Auto-teste com banco temporario, antes de mexer no banco real.
    with tempfile.TemporaryDirectory() as tmp:
        banco = os.path.join(tmp, "teste_fechar.db")
        db_opcoes.init_schema(banco)
        db_opcoes.init_schema_cenarios(banco)

        db_opcoes.gravar_cenario("PETR4", "2026-07-01", "2026-08-15", "base",
                                  35.0, 0.5, "teste", banco, ajustado=True)
        db_opcoes.upsert_underlying([{
            "Ativo_Objeto": "PETR4", "Spot": 37.25, "HV_60d": 0.25,
            "Data_Referencia": "2026-08-15"}], banco)

        # Caso 1: fecha com o spot da data do vencimento
        fechadas, sem = fechar("2026-08-20", banco)
        assert (fechadas, sem) == (1, 0), (fechadas, sem)
        assert db_opcoes.ler_cenarios("PETR4", "2026-08-15", banco)[0]["Preco_Realizado"] == 37.25
        print("[OK] Caso 1: declaracao vencida e' fechada com o spot daquela data.")

        # Caso 2: rodar de novo nao refaz nada (a fila ja esvaziou)
        assert fechar("2026-08-20", banco) == (0, 0)
        print("[OK] Caso 2: rodar de novo e' inocuo - a fila ja esvaziou.")

        # Caso 3: sem cotacao na data, a declaracao fica EM ABERTO em vez de
        # ser fechada com o preco de outro dia. Fechar errado contaminaria a
        # propria medicao que isto existe para fazer.
        db_opcoes.gravar_cenario("VALE3", "2026-07-01", "2026-08-15", "base",
                                  60.0, 0.5, "teste", banco, ajustado=True)
        fechadas2, sem2 = fechar("2026-08-20", banco)
        assert (fechadas2, sem2) == (0, 1), (fechadas2, sem2)
        assert db_opcoes.ler_cenarios("VALE3", "2026-08-15", banco)[0]["Preco_Realizado"] is None
        print("[OK] Caso 3: sem cotacao na data, fica em aberto (nao aproxima).")

        # Caso 4: declaracao ainda nao vencida nao e' tocada
        db_opcoes.gravar_cenario("PETR4", "2026-08-01", "2026-12-19", "base",
                                  40.0, 0.5, "futura", banco, ajustado=True)
        assert fechar("2026-08-20", banco) == (0, 1)   # so' a VALE3 pendente
        assert db_opcoes.ler_cenarios("PETR4", "2026-12-19", banco)[0]["Preco_Realizado"] is None
        print("[OK] Caso 4: declaracao ainda nao vencida nao e' fechada.")

    print("\nTodos os casos passaram.\n")

    # Execucao real
    print("Fechando declaracoes vencidas...")
    fechadas, sem_cotacao = fechar()
    print(f"{fechadas} fechada(s), {sem_cotacao} sem cotacao disponivel.")
