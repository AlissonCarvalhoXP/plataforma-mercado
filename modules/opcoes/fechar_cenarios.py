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
import estruturas_opcoes as eo


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


def fechar_operacoes(hoje: str | None = None, db_path=None) -> tuple[int, int]:
    """Apura o resultado das operacoes registradas cujo vencimento ja passou.

    Devolve (fechadas, sem_cotacao). Usa payoff_estrutura sobre as pernas
    guardadas em JSON - por isso nao depende de a cadeia daquele dia ainda
    existir no banco. Quando ha preco executado, o resultado e' ajustado por
    ele; sem preco executado, mede o payoff nos precos de tela."""
    db_opcoes.init_schema_operacoes(db_path)
    hoje = hoje or str(date.today())
    pendentes = db_opcoes.operacoes_a_fechar(hoje, db_path)

    fechadas = 0
    sem_cotacao = 0
    for id_op, ativo, vencimento, pernas_json, preco_executado in pendentes:
        spot = db_opcoes.spot_na_data(ativo, vencimento, db_path)
        if spot is None:
            sem_cotacao += 1
            print(f"  operacao {id_op} ({ativo} {vencimento}): sem cotacao no banco - "
                  f"fica em aberto")
            continue
        pernas = eo.pernas_de_json(pernas_json)
        resultado = eo.resultado_no_vencimento(pernas, spot, preco_executado)
        db_opcoes.registrar_resultado_operacao(id_op, resultado, db_path)
        fechadas += 1
        rotulo = "executada" if preco_executado is not None else "acompanhada"
        print(f"  operacao {id_op} ({ativo} {vencimento}, {rotulo}): "
              f"spot R$ {spot:.2f} -> resultado R$ {resultado:,.2f}")

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

        # Caso 5: operacao vencida e' apurada com o payoff no spot daquele dia.
        # Trava de alta 30/35 comprada por 1,50 de debito: acima de 35 o ganho
        # e' travado em (35-30-1,50)*100 = 350.
        db_opcoes.init_schema_operacoes(banco)
        pernas = [eo.Perna(lado="comprar", tipo="CALL", strike=30.0, premio=2.00),
                  eo.Perna(lado="vender", tipo="CALL", strike=35.0, premio=0.50)]
        id_op = db_opcoes.gravar_operacao(
            "PETR4", "2026-07-01", "2026-08-15", "trava de alta com calls",
            eo.pernas_para_json(pernas), 150.0, None, -150.0, 350.0, banco)
        fechadas_op, sem_op = fechar_operacoes("2026-08-20", banco)
        assert (fechadas_op, sem_op) == (1, 0), (fechadas_op, sem_op)
        # spot daquele dia foi 37,25 (gravado no Caso 1), acima de 35
        assert db_opcoes.ler_operacoes("PETR4", banco)[0]["Resultado_Realizado"] == 350.0
        print("[OK] Caso 5: operacao vencida e' apurada pelo payoff no spot realizado.")

        # Caso 6: com preco EXECUTADO pior que a tela, o resultado cai a
        # diferenca - e' o que separa medir a ferramenta de medir a execucao.
        id_op2 = db_opcoes.gravar_operacao(
            "PETR4", "2026-07-01", "2026-08-15", "trava de alta com calls",
            eo.pernas_para_json(pernas), 150.0, 200.0, -200.0, 300.0, banco)
        fechar_operacoes("2026-08-20", banco)
        resultado2 = [o for o in db_opcoes.ler_operacoes("PETR4", banco)
                      if o["id"] == id_op2][0]["Resultado_Realizado"]
        assert resultado2 == 300.0, resultado2
        print("[OK] Caso 6: preco executado pior que a tela reduz o resultado apurado.")

    print("\nTodos os casos passaram.\n")

    # Execucao real
    print("Fechando declaracoes de cenario vencidas...")
    fechadas, sem_cotacao = fechar()
    print(f"{fechadas} declaracao(oes) fechada(s), {sem_cotacao} sem cotacao.")

    print("Apurando operacoes registradas vencidas...")
    fechadas_op, sem_op = fechar_operacoes()
    print(f"{fechadas_op} operacao(oes) apurada(s), {sem_op} sem cotacao.")
