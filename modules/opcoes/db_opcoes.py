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
                PRIMARY KEY (Ativo, Data_Declaracao, Data_Vencimento, Cenario)
            )
        """)
        con.commit()
    finally:
        con.close()


def gravar_cenario(ativo: str, data_declaracao: str, vencimento: str,
                    cenario: str, preco_alvo: float, probabilidade: float,
                    premissa: str, db_path: str | Path | None = None) -> None:
    """Idempotente: regravar o mesmo (ativo, data, vencimento, cenario)
    atualiza os valores em vez de duplicar a linha."""
    con = _conn(db_path)
    try:
        con.execute("""
            INSERT INTO opcoes_cenarios
                (Ativo, Data_Declaracao, Data_Vencimento, Cenario,
                 Preco_Alvo, Probabilidade, Premissa)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(Ativo, Data_Declaracao, Data_Vencimento, Cenario)
            DO UPDATE SET Preco_Alvo=excluded.Preco_Alvo,
                          Probabilidade=excluded.Probabilidade,
                          Premissa=excluded.Premissa
        """, (ativo, data_declaracao, vencimento, cenario,
              preco_alvo, probabilidade, premissa))
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

    print("\nTodos os casos passaram.")
