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


def list_existing_tables(db_path: str | Path | None = None) -> list[str]:
    """Diagnóstico: lista todas as tabelas do banco (prova de que nada foi apagado)."""
    con = _conn(db_path)
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    con.close()
    return [r[0] for r in rows]
