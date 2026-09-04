"""Camada de persistência do Módulo de Opções — ADITIVA ao mercado.db do MIH.

Cria apenas tabelas novas (opcoes_series, opcoes_underlying) seguindo a convenção
de nomenclatura das debêntures: snake_case com iniciais maiúsculas, datas AAAA-MM-DD,
campo Status_Validacao. NÃO altera nenhuma tabela existente.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import date

# Caminho padrão do MIH — ajuste se necessário no seu ambiente
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "mercado.db"


def _conn(db_path: str | Path | None = None) -> sqlite3.Connection:
    p = Path(db_path) if db_path else DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(p)


def init_schema(db_path: str | Path | None = None) -> None:
    """Cria as tabelas de opções se ainda não existirem (idempotente e aditivo)."""
    con = _conn(db_path)
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS opcoes_underlying (
            Ativo_Objeto     TEXT NOT NULL,
            Spot             REAL,
            HV_60d           REAL,
            Data_Referencia  TEXT NOT NULL,
            Fonte            TEXT,
            Status_Validacao TEXT DEFAULT 'OK',
            PRIMARY KEY (Ativo_Objeto, Data_Referencia)
        )""")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS opcoes_series (
            Codigo_Opcao     TEXT NOT NULL,
            Ativo_Objeto     TEXT NOT NULL,
            Tipo             TEXT NOT NULL,          -- CALL | PUT
            Strike           REAL NOT NULL,
            Data_Vencimento  TEXT NOT NULL,          -- AAAA-MM-DD
            Bid              REAL,
            Ask              REAL,
            Ultimo           REAL,
            Volume           INTEGER,
            Open_Interest    INTEGER,
            IV_Fonte         REAL,                   -- NULL se calculada localmente
            Data_Referencia  TEXT NOT NULL,          -- AAAA-MM-DD (pregão)
            Fonte            TEXT,
            Status_Validacao TEXT DEFAULT 'OK',
            PRIMARY KEY (Codigo_Opcao, Data_Referencia)
        )""")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_opc_ativo_ref "
                "ON opcoes_series (Ativo_Objeto, Data_Referencia)")
    con.commit()
    con.close()


def upsert_underlying(rows: list[dict], db_path: str | Path | None = None) -> int:
    """Insere/atualiza dados do ativo-objeto. rows: dicts com as colunas da tabela."""
    con = _conn(db_path)
    cur = con.cursor()
    n = 0
    for r in rows:
        cur.execute("""
            INSERT INTO opcoes_underlying
                (Ativo_Objeto, Spot, HV_60d, Data_Referencia, Fonte, Status_Validacao)
            VALUES (:Ativo_Objeto, :Spot, :HV_60d, :Data_Referencia, :Fonte, :Status_Validacao)
            ON CONFLICT(Ativo_Objeto, Data_Referencia) DO UPDATE SET
                Spot=excluded.Spot, HV_60d=excluded.HV_60d,
                Fonte=excluded.Fonte, Status_Validacao=excluded.Status_Validacao
        """, {**{"Fonte": None, "Status_Validacao": "OK"}, **r})
        n += 1
    con.commit()
    con.close()
    return n


def upsert_series(rows: list[dict], db_path: str | Path | None = None) -> int:
    """Insere/atualiza séries de opções (uma foto por Data_Referencia)."""
    con = _conn(db_path)
    cur = con.cursor()
    n = 0
    for r in rows:
        cur.execute("""
            INSERT INTO opcoes_series
                (Codigo_Opcao, Ativo_Objeto, Tipo, Strike, Data_Vencimento,
                 Bid, Ask, Ultimo, Volume, Open_Interest, IV_Fonte,
                 Data_Referencia, Fonte, Status_Validacao)
            VALUES
                (:Codigo_Opcao, :Ativo_Objeto, :Tipo, :Strike, :Data_Vencimento,
                 :Bid, :Ask, :Ultimo, :Volume, :Open_Interest, :IV_Fonte,
                 :Data_Referencia, :Fonte, :Status_Validacao)
            ON CONFLICT(Codigo_Opcao, Data_Referencia) DO UPDATE SET
                Bid=excluded.Bid, Ask=excluded.Ask, Ultimo=excluded.Ultimo,
                Volume=excluded.Volume, Open_Interest=excluded.Open_Interest,
                IV_Fonte=excluded.IV_Fonte, Status_Validacao=excluded.Status_Validacao
        """, {**{"Fonte": None, "Status_Validacao": "OK", "IV_Fonte": None}, **r})
        n += 1
    con.commit()
    con.close()
    return n


def read_latest_chain(ativo: str, db_path: str | Path | None = None):
    """Lê a cadeia mais recente de um ativo (para a camada de análise/front)."""
    con = _conn(db_path)
    con.row_factory = sqlite3.Row
    ref = con.execute(
        "SELECT MAX(Data_Referencia) FROM opcoes_series WHERE Ativo_Objeto=?",
        (ativo,)).fetchone()[0]
    if not ref:
        con.close()
        return None, []
    und = con.execute(
        "SELECT * FROM opcoes_underlying WHERE Ativo_Objeto=? AND Data_Referencia=?",
        (ativo, ref)).fetchone()
    series = con.execute(
        "SELECT * FROM opcoes_series WHERE Ativo_Objeto=? AND Data_Referencia=? ORDER BY Strike",
        (ativo, ref)).fetchall()
    con.close()
    return (dict(und) if und else None), [dict(s) for s in series]


def init_schema_cenarios(db_path: str | Path | None = None) -> None:
    """Tabela de cenarios declarados pelo usuario (idempotente e aditivo).

    Data_Declaracao e' o que torna a afericao posterior possivel: com o tempo,
    da' pra medir se os cenarios do usuario acertam mais que o preco implicito.
    Isso e' genuinamente calibravel, ao contrario do Score (ver secao 4.4c do
    ROADMAP_MIH_Opcoes_Handoff.md)."""
    con = _conn(db_path)
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS opcoes_cenarios (
                Ativo TEXT NOT NULL,
                Data_Declaracao TEXT NOT NULL,
                Data_Vencimento TEXT NOT NULL,
                Cenario TEXT NOT NULL CHECK(Cenario IN ('alta','base','baixa')),
                Preco_Alvo REAL NOT NULL,
                Probabilidade REAL NOT NULL,
                Premissa TEXT,
                Ajustado INTEGER DEFAULT 0,
                Preco_Realizado REAL,
                PRIMARY KEY (Ativo, Data_Declaracao, Data_Vencimento, Cenario)
            )
        """)
        # Aditivo para bancos que ja tinham a tabela sem estas colunas.
        for coluna, tipo in (("Ajustado", "INTEGER DEFAULT 0"),
                             ("Preco_Realizado", "REAL")):
            try:
                con.execute(f"ALTER TABLE opcoes_cenarios ADD COLUMN {coluna} {tipo}")
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise

        # Distribuicao implicita do MOMENTO da declaracao, uma linha por
        # declaracao. Guardada aqui porque reconstrui-la depois seria fragil:
        # dependeria de a cadeia daquele dia ainda existir no banco.
        con.execute("""
            CREATE TABLE IF NOT EXISTS opcoes_implicitas (
                Ativo TEXT NOT NULL,
                Data_Declaracao TEXT NOT NULL,
                Data_Vencimento TEXT NOT NULL,
                Q10 REAL NOT NULL, Q25 REAL NOT NULL, Q50 REAL NOT NULL,
                Q75 REAL NOT NULL, Q90 REAL NOT NULL,
                PRIMARY KEY (Ativo, Data_Declaracao, Data_Vencimento)
            )
        """)
        con.commit()
    finally:
        con.close()


def gravar_cenario(ativo: str, data_declaracao: str, vencimento: str,
                    cenario: str, preco_alvo: float, probabilidade: float,
                    premissa: str, db_path: str | Path | None = None,
                    ajustado: bool = False) -> None:
    """Idempotente: regravar o mesmo (ativo, data, vencimento, cenario)
    atualiza os valores em vez de duplicar a linha.

    `ajustado` registra se o usuario MEXEU nos valores pre-preenchidos pela
    distribuicao implicita. Importa para a afericao: um cenario aceito sem
    alteracao e' a visao do MERCADO, nao a do usuario - conta-lo como
    previsao propria mediria a coisa errada."""
    con = _conn(db_path)
    try:
        con.execute("""
            INSERT INTO opcoes_cenarios
                (Ativo, Data_Declaracao, Data_Vencimento, Cenario,
                 Preco_Alvo, Probabilidade, Premissa, Ajustado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(Ativo, Data_Declaracao, Data_Vencimento, Cenario)
            DO UPDATE SET Preco_Alvo=excluded.Preco_Alvo,
                          Probabilidade=excluded.Probabilidade,
                          Premissa=excluded.Premissa,
                          Ajustado=excluded.Ajustado
        """, (ativo, data_declaracao, vencimento, cenario,
              preco_alvo, probabilidade, premissa, 1 if ajustado else 0))
        con.commit()
    finally:
        con.close()


def ler_cenarios(ativo: str, vencimento: str,
                  db_path: str | Path | None = None) -> list[dict]:
    """Cenarios da declaracao MAIS RECENTE para o par (ativo, vencimento).

    Declaracoes antigas ficam na tabela de proposito - sao o registro do que o
    usuario pensava naquela data, base da afericao futura."""
    con = _conn(db_path)
    con.row_factory = sqlite3.Row
    try:
        linhas = con.execute("""
            SELECT * FROM opcoes_cenarios
            WHERE Ativo = ? AND Data_Vencimento = ?
              AND Data_Declaracao = (
                  SELECT MAX(Data_Declaracao) FROM opcoes_cenarios
                  WHERE Ativo = ? AND Data_Vencimento = ?)
            ORDER BY Cenario
        """, (ativo, vencimento, ativo, vencimento)).fetchall()
        return [dict(linha) for linha in linhas]
    finally:
        con.close()


def gravar_implicita(ativo: str, data_declaracao: str, vencimento: str,
                      q10: float, q25: float, q50: float, q75: float, q90: float,
                      db_path: str | Path | None = None) -> None:
    """Guarda a distribuicao implicita do momento da declaracao (idempotente)."""
    con = _conn(db_path)
    try:
        con.execute("""
            INSERT INTO opcoes_implicitas
                (Ativo, Data_Declaracao, Data_Vencimento, Q10, Q25, Q50, Q75, Q90)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(Ativo, Data_Declaracao, Data_Vencimento) DO UPDATE SET
                Q10=excluded.Q10, Q25=excluded.Q25, Q50=excluded.Q50,
                Q75=excluded.Q75, Q90=excluded.Q90
        """, (ativo, data_declaracao, vencimento, q10, q25, q50, q75, q90))
        con.commit()
    finally:
        con.close()


def ler_implicita(ativo: str, data_declaracao: str, vencimento: str,
                   db_path: str | Path | None = None) -> dict | None:
    """A implicita guardada naquela declaracao, ou None se nao houver."""
    con = _conn(db_path)
    con.row_factory = sqlite3.Row
    try:
        linha = con.execute(
            "SELECT * FROM opcoes_implicitas WHERE Ativo=? AND Data_Declaracao=? "
            "AND Data_Vencimento=?", (ativo, data_declaracao, vencimento)).fetchone()
        return dict(linha) if linha else None
    finally:
        con.close()


def declaracoes_a_fechar(hoje: str, db_path: str | Path | None = None) -> list[tuple]:
    """Declaracoes cujo vencimento ja passou e que ainda nao tem realizado.

    E' a fila que o passo diario do atualizar.py consome - fecha o ciclo sem
    depender de o usuario lembrar de voltar na tela."""
    con = _conn(db_path)
    try:
        return [tuple(r) for r in con.execute("""
            SELECT DISTINCT Ativo, Data_Declaracao, Data_Vencimento
            FROM opcoes_cenarios
            WHERE Data_Vencimento <= ? AND Preco_Realizado IS NULL
            ORDER BY Data_Vencimento
        """, (hoje,)).fetchall()]
    finally:
        con.close()


def registrar_realizado_cenario(ativo: str, data_declaracao: str, vencimento: str,
                                 preco_realizado: float,
                                 db_path: str | Path | None = None) -> None:
    """Fecha uma declaracao com o preco que de fato ocorreu."""
    con = _conn(db_path)
    try:
        con.execute("""
            UPDATE opcoes_cenarios SET Preco_Realizado = ?
            WHERE Ativo=? AND Data_Declaracao=? AND Data_Vencimento=?
        """, (preco_realizado, ativo, data_declaracao, vencimento))
        con.commit()
    finally:
        con.close()


def spot_na_data(ativo: str, data: str, db_path: str | Path | None = None) -> float | None:
    """Spot do ativo naquela data de referencia, dos snapshots diarios.

    Devolve None se nao houver snapshot - nunca aproxima com a data mais
    proxima: fechar uma declaracao com o preco de outro dia seria inventar o
    resultado que a afericao existe para medir."""
    con = _conn(db_path)
    try:
        linha = con.execute(
            "SELECT Spot FROM opcoes_underlying WHERE Ativo_Objeto=? AND Data_Referencia=?",
            (ativo, data)).fetchone()
        return float(linha[0]) if linha and linha[0] is not None else None
    finally:
        con.close()


def init_schema_operacoes(db_path: str | Path | None = None) -> None:
    """Tabela das operacoes que o usuario registrou para acompanhar.

    As PERNAS ficam guardadas em JSON, nao so' o nome da estrutura: e' o que
    permite recalcular o resultado meses depois sem depender de a cadeia
    daquele dia ainda existir.

    Preco_Executado nulo significa "estou acompanhando" (registro pelo preco de
    tela); preenchido significa "montei de verdade" por aquele premio liquido.
    Sao medidas diferentes - a primeira mede o que a FERRAMENTA produziu, a
    segunda o que voce conseguiu EXECUTAR - e a tela as separa."""
    con = _conn(db_path)
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS opcoes_operacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                Ativo TEXT NOT NULL,
                Data_Registro TEXT NOT NULL,
                Data_Vencimento TEXT NOT NULL,
                Estrutura TEXT NOT NULL,
                Pernas_Json TEXT NOT NULL,
                Premio_Tela REAL NOT NULL,
                Preco_Executado REAL,
                Perda_Maxima REAL,
                Ganho_Maximo REAL,
                Resultado_Realizado REAL
            )
        """)
        con.commit()
    finally:
        con.close()


def gravar_operacao(ativo: str, data_registro: str, vencimento: str,
                     estrutura: str, pernas_json: str, premio_tela: float,
                     preco_executado: float | None, perda_maxima: float | None,
                     ganho_maximo: float | None,
                     db_path: str | Path | None = None) -> int:
    """Registra uma operacao e devolve o id gerado.

    perda_maxima/ganho_maximo em None significam ILIMITADO, mesma convencao de
    estruturas_opcoes.PerfilRisco."""
    con = _conn(db_path)
    try:
        cur = con.execute("""
            INSERT INTO opcoes_operacoes
                (Ativo, Data_Registro, Data_Vencimento, Estrutura, Pernas_Json,
                 Premio_Tela, Preco_Executado, Perda_Maxima, Ganho_Maximo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (ativo, data_registro, vencimento, estrutura, pernas_json,
              premio_tela, preco_executado, perda_maxima, ganho_maximo))
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()


def ler_operacoes(ativo: str | None = None,
                   db_path: str | Path | None = None) -> list[dict]:
    """Operacoes registradas, mais recentes primeiro. ativo=None traz todas."""
    con = _conn(db_path)
    con.row_factory = sqlite3.Row
    try:
        if ativo:
            linhas = con.execute(
                "SELECT * FROM opcoes_operacoes WHERE Ativo=? "
                "ORDER BY Data_Registro DESC, id DESC", (ativo,)).fetchall()
        else:
            linhas = con.execute(
                "SELECT * FROM opcoes_operacoes "
                "ORDER BY Data_Registro DESC, id DESC").fetchall()
        return [dict(l) for l in linhas]
    finally:
        con.close()


def operacoes_a_fechar(hoje: str, db_path: str | Path | None = None) -> list[tuple]:
    """Operacoes vencidas e ainda sem resultado: a fila do passo diario."""
    con = _conn(db_path)
    try:
        return [tuple(r) for r in con.execute("""
            SELECT id, Ativo, Data_Vencimento, Pernas_Json, Preco_Executado
            FROM opcoes_operacoes
            WHERE Data_Vencimento <= ? AND Resultado_Realizado IS NULL
            ORDER BY Data_Vencimento
        """, (hoje,)).fetchall()]
    finally:
        con.close()


def registrar_resultado_operacao(id_operacao: int, resultado: float,
                                  db_path: str | Path | None = None) -> None:
    """Fecha uma operacao com o resultado apurado no vencimento."""
    con = _conn(db_path)
    try:
        con.execute("UPDATE opcoes_operacoes SET Resultado_Realizado=? WHERE id=?",
                    (resultado, id_operacao))
        con.commit()
    finally:
        con.close()


def ler_declaracoes(ativo: str | None = None,
                     db_path: str | Path | None = None) -> list[dict]:
    """Todas as declaracoes de cenario, para a pagina de historico."""
    con = _conn(db_path)
    con.row_factory = sqlite3.Row
    try:
        if ativo:
            linhas = con.execute(
                "SELECT * FROM opcoes_cenarios WHERE Ativo=? "
                "ORDER BY Data_Declaracao DESC, Data_Vencimento DESC, Cenario",
                (ativo,)).fetchall()
        else:
            linhas = con.execute(
                "SELECT * FROM opcoes_cenarios "
                "ORDER BY Data_Declaracao DESC, Data_Vencimento DESC, Cenario").fetchall()
        return [dict(l) for l in linhas]
    finally:
        con.close()


def list_existing_tables(db_path: str | Path | None = None) -> list[str]:
    """Diagnóstico: lista todas as tabelas do banco (prova de que nada foi apagado)."""
    con = _conn(db_path)
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    con.close()
    return [r[0] for r in rows]


def carregar_precos(ativo: str, db_path: str | Path | None = None) -> list[float]:
    """Serie de preco diario do ativo-objeto, a partir do historico COTAHIST."""
    con = _conn(db_path)
    try:
        linhas = con.execute("""
            SELECT Data, MAX(Preco_Ativo) FROM opcoes_historico
            WHERE Ativo_Objeto = ? AND Preco_Ativo > 0
            GROUP BY Data ORDER BY Data
        """, (ativo,)).fetchall()
    finally:
        con.close()
    return [float(v) for _data, v in linhas]


if __name__ == "__main__":
    import tempfile, os as _os

    with tempfile.TemporaryDirectory() as tmp:
        banco = _os.path.join(tmp, "teste_cenarios.db")
        init_schema_cenarios(banco)

        gravar_cenario("PETR4", "2026-09-02", "2026-10-16", "alta",
                       42.0, 0.25, "Selic cai, Brent > 80", banco)
        gravar_cenario("PETR4", "2026-09-02", "2026-10-16", "base",
                       35.0, 0.55, "cenario atual se mantem", banco)
        lidos = ler_cenarios("PETR4", "2026-10-16", banco)
        assert len(lidos) == 2
        assert {linha["Cenario"] for linha in lidos} == {"alta", "base"}
        alta = [linha for linha in lidos if linha["Cenario"] == "alta"][0]
        assert alta["Preco_Alvo"] == 42.0 and alta["Probabilidade"] == 0.25
        assert alta["Premissa"] == "Selic cai, Brent > 80"
        print("[OK] Caso 1: cenario gravado e lido com premissa preservada.")

        # regravar o mesmo (ativo, data, vencimento, cenario) atualiza, nao duplica
        gravar_cenario("PETR4", "2026-09-02", "2026-10-16", "alta",
                       44.0, 0.30, "revisado", banco)
        lidos2 = ler_cenarios("PETR4", "2026-10-16", banco)
        assert len(lidos2) == 2
        alta2 = [linha for linha in lidos2 if linha["Cenario"] == "alta"][0]
        assert alta2["Preco_Alvo"] == 44.0 and alta2["Premissa"] == "revisado"
        print("[OK] Caso 2: regravar o mesmo cenario atualiza em vez de duplicar.")

    with tempfile.TemporaryDirectory() as tmp3:
        banco3 = _os.path.join(tmp3, "teste_afericao.db")
        init_schema_cenarios(banco3)

        # Caso 3: gravar cenario com a implicita do momento e o flag Ajustado.
        # Guardar a implicita e' o que permite comparar depois "eu fui melhor
        # calibrado que o preco?" - reconstruir a implicita do passado seria
        # fragil, porque depende de a cadeia daquele dia ainda existir.
        gravar_cenario("PETR4", "2026-09-03", "2026-10-16", "base",
                       35.0, 0.50, "cenario base", banco3, ajustado=True)
        gravar_implicita("PETR4", "2026-09-03", "2026-10-16",
                         28.0, 31.0, 34.0, 37.0, 40.0, banco3)
        lidos = ler_cenarios("PETR4", "2026-10-16", banco3)
        assert lidos[0]["Ajustado"] == 1
        assert lidos[0]["Preco_Realizado"] is None
        imp = ler_implicita("PETR4", "2026-09-03", "2026-10-16", banco3)
        assert imp is not None and imp["Q50"] == 34.0
        print("[OK] Caso 3: cenario guarda o flag Ajustado e a implicita do momento.")

        # Caso 4: declaracoes vencidas e sem realizado entram na fila de
        # fechamento; as ja fechadas saem dela.
        pendentes = declaracoes_a_fechar("2026-10-20", banco3)
        assert ("PETR4", "2026-09-03", "2026-10-16") in pendentes
        assert declaracoes_a_fechar("2026-10-01", banco3) == []
        registrar_realizado_cenario("PETR4", "2026-09-03", "2026-10-16", 36.5, banco3)
        assert declaracoes_a_fechar("2026-10-20", banco3) == []
        assert ler_cenarios("PETR4", "2026-10-16", banco3)[0]["Preco_Realizado"] == 36.5
        print("[OK] Caso 4: fila de fechamento respeita o vencimento e esvazia ao registrar.")

    with tempfile.TemporaryDirectory() as tmp4:
        banco4 = _os.path.join(tmp4, "teste_ops.db")
        init_schema_operacoes(banco4)

        pernas_json = '[{"lado": "comprar", "tipo": "CALL", "strike": 30.0, "premio": 2.0, "quantidade": 1, "vencimento": "2026-10-16"}]'

        # Caso 5: operacao ACOMPANHADA (sem preco executado) e EXECUTADA
        # (com preco) convivem e sao distinguiveis - medem coisas diferentes:
        # o que a ferramenta produziu vs o que voce conseguiu executar.
        id_acomp = gravar_operacao("PETR4", "2026-09-03", "2026-10-16",
                                    "trava de alta com calls", pernas_json,
                                    150.0, None, -150.0, 350.0, banco4)
        id_exec = gravar_operacao("PETR4", "2026-09-03", "2026-10-16",
                                   "compra de straddle", pernas_json,
                                   250.0, 265.0, -250.0, None, banco4)
        ops = ler_operacoes("PETR4", banco4)
        assert len(ops) == 2
        por_id = {o["id"]: o for o in ops}
        assert por_id[id_acomp]["Preco_Executado"] is None
        assert por_id[id_exec]["Preco_Executado"] == 265.0
        assert por_id[id_acomp]["Ganho_Maximo"] == 350.0
        assert por_id[id_exec]["Ganho_Maximo"] is None   # ilimitado
        print("[OK] Caso 5: operacoes acompanhadas e executadas convivem e se distinguem.")

        # Caso 6: fila de fechamento das operacoes respeita o vencimento
        assert len(operacoes_a_fechar("2026-10-20", banco4)) == 2
        assert operacoes_a_fechar("2026-10-01", banco4) == []
        registrar_resultado_operacao(id_acomp, 480.0, banco4)
        pendentes = operacoes_a_fechar("2026-10-20", banco4)
        assert len(pendentes) == 1 and pendentes[0][0] == id_exec
        assert ler_operacoes("PETR4", banco4)[0]["Resultado_Realizado"] in (480.0, None)
        print("[OK] Caso 6: fila de operacoes esvazia conforme o resultado e' registrado.")

    print("\nTodos os casos passaram.")
