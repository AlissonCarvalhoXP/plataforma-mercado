# Coleta de Histórico de Opções via COTAHIST (B3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Coletar histórico de opções da B3 (2024-2025, todos os ativos com opções negociadas) via os arquivos oficiais gratuitos COTAHIST, e gravar em `opcoes_historico` no mesmo formato que `backtest_opcoes.py` já consome — resolvendo a limitação de amostra pequena que bloqueia qualquer calibração confiável do Score de Opções.

**Architecture:** Novo módulo standalone `modules/opcoes/coleta_cotahist.py`, mesmo padrão de `coleta_opcoes_historico.py`. Duas passadas sobre o arquivo anual descompactado: (1) indexar os registros de ação à vista por `(data, raiz do ticker)`, guardando o de maior volume em caso de mais de uma classe; (2) para cada registro de opção, casar pela raiz do ticker, calcular IV via Black-Scholes (função já existente) usando a Selic do dia, e gravar em `opcoes_historico` (schema estendido com Bid/Ask/Volume/Num_Negocios, colunas novas e nulas para linhas antigas).

**Tech Stack:** Python, `zipfile`/`requests` (download e descompactação em memória), `sqlite3` (mesmo padrão de `db_opcoes.py`/`coleta_opcoes_historico.py`), `analises_opcoes.implied_vol()` (já existe).

**Spec:** [docs/superpowers/specs/2026-08-30-coleta-cotahist-b3-design.md](../specs/2026-08-30-coleta-cotahist-b3-design.md)

## Verificação já feita (não repetir)

A spec original previa um "spike de verificação" antes de implementar — já foi feito e a spec já reflete o resultado:
- **URL confirmada:** `https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{ANO}.ZIP` (testada via HTTP HEAD, `200 OK`, arquivos de 2024 e 2025 existem).
- **Casamento opção↔ação por `NOMRES` NÃO FUNCIONA** — verificado contra dado real (PETR e ITUB, 14/06/2024): o `NOMRES` de um registro de opção vem truncado (`"PETR    /EDJ"`), não bate com o `NOMRES` limpo da ação (`"PETROBRAS"`). A abordagem correta, também já verificada com dado real, é casar pelos **4 primeiros caracteres do `CODNEG`** (raiz do ticker), com **maior `VOLTOT` como desempate** quando mais de uma classe do emissor compartilha a raiz (verificado: ITUB3 R$ 984 milhões vs. ITUB4 R$ 48 bilhões no mesmo dia — a diferença de liquidez nunca é um empate ambíguo de verdade).

## Global Constraints

- Layout do arquivo: registros de 245 bytes fixos. Campos e posições (1-indexed, inclusive) usados neste plano — **usar exatamente estas posições**, já confirmadas contra o PDF oficial da B3 (revisão 01, 13/04/2017):
  - `TIPREG` 1-2, `DATA_PREGAO` 3-10 (AAAAMMDD), `CODBDI` 11-12, `CODNEG` 13-24, `TPMERC` 25-27, `NOMRES` 28-39, `PREULT` 109-121, `PREOFC` 122-134, `PREOFV` 135-147, `TOTNEG` 148-152, `VOLTOT` 171-188, `PREEXE` 189-201, `DATVEN` 203-210.
- `CODBDI`: `"78"` = opção de CALL, `"82"` = opção de PUT, `"02"` = ação em lote padrão (mercado à vista).
- Campos de preço/volume (`PREULT`, `PREOFC`, `PREOFV`, `PREEXE`, `VOLTOT`) são inteiros de largura fixa com 2 casas decimais implícitas (sem ponto no texto) — dividir por 100 para obter o valor real.
- Casamento opção↔ação: pelos 4 primeiros caracteres de `CODNEG` (raiz do ticker), não por `NOMRES`. Em caso de mais de uma classe com a mesma raiz no mesmo dia, usar a de maior `VOLTOT`.
- Sem correspondência de raiz no mesmo dia → descartar a linha da opção (nunca inventar `Preco_Ativo`).
- Schema `opcoes_historico`: adicionar colunas `Bid REAL`, `Ask REAL`, `Volume REAL`, `Num_Negocios INTEGER` (nulas, aditivo — linhas existentes de fonte `brapi` continuam `NULL` nessas colunas). `Fonte='b3_cotahist'` para linhas deste pipeline.
- Escrita idempotente: `INSERT ... ON CONFLICT(Codigo_Opcao, Data) DO UPDATE` — mesmo padrão de `coleta_opcoes_historico.py::coletar_serie()`.
- Sem framework de teste automatizado no projeto: `assert`s em `if __name__ == "__main__":`, mesmo padrão de `analises_opcoes.py`.
- Linha malformada (menos de 245 caracteres, campo numérico não parseável) → pular e seguir, nunca abortar o arquivo inteiro.

---

## Task 1: Parser da linha COTAHIST + extensão do schema

**Files:**
- Create: `modules/opcoes/coleta_cotahist.py`

**Interfaces:**
- Produces: `parsear_linha(linha: str) -> dict | None` — devolve um dict com chaves `tipreg, data, codbdi, codneg, tpmerc, nomres, preult, preofc, preofv, totneg, voltot, preexe, datven` (todas já convertidas: datas como string `AAAAMMDD` sem alteração, preços/volume já divididos por 100 como `float`, `totneg` como `int`). Devolve `None` se a linha não for um registro de dado (`tipreg != "01"`) ou estiver malformada (curta demais, campo numérico não parseável).
- Produces: `raiz_ticker(codneg: str) -> str` — os 4 primeiros caracteres de um `CODNEG` já sem espaços (`.strip()`), maiúsculos.
- Produces: `garantir_schema_estendido(db_path=None)` — roda `ALTER TABLE opcoes_historico ADD COLUMN ...` para `Bid`, `Ask`, `Volume`, `Num_Negocios` (idempotente: ignora erro "duplicate column" se a coluna já existir).

- [ ] **Step 1: Escrever o teste (assert) antes da implementação**

Criar `modules/opcoes/coleta_cotahist.py` com o cabeçalho, imports, e o bloco de teste
no final (as funções ainda não existem — vai falhar):

```python
"""Coleta de historico de opcoes via COTAHIST (arquivos oficiais e gratuitos da B3).

Resolve a limitacao de amostra pequena do backtest de Opcoes (so PETR4 via brapi,
poucas series qualificadas) - ver docs/superpowers/specs/
2026-08-30-coleta-cotahist-b3-design.md para o raciocinio completo.

Uso:
    python modules/opcoes/coleta_cotahist.py --ano 2024
    python modules/opcoes/coleta_cotahist.py --ano 2024 --ano 2025

Fonte: https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{ANO}.ZIP
(gratuito, sem token, sem limite de requisicao - confirmado via HTTP HEAD em
2026-08-30). Layout do arquivo: 245 bytes fixos por linha, confirmado contra o
PDF oficial da B3 (SeriesHistoricas_Layout.pdf, revisao 01, 13/04/2017).
"""
from __future__ import annotations
import os, sys, sqlite3
sys.path.insert(0, os.path.dirname(__file__))
import db_opcoes

CODBDI_CALL = "78"
CODBDI_PUT = "82"
CODBDI_VISTA = "02"


def _campo_teste(valor, largura, alinhar="direita"):
    """So para montar linhas sinteticas de teste (nao faz parte do modulo real) -
    largura fixa, preenchida com '0' a direita ou com espaco a esquerda, igual ao
    layout oficial do COTAHIST."""
    texto = str(valor)
    return texto.rjust(largura, "0") if alinhar == "direita" else texto.ljust(largura, " ")


if __name__ == "__main__":
    # Linha sintetica de opcao CALL (245 bytes), montada campo a campo com a largura
    # exata do layout oficial (nao digitada como literal - um literal de 245
    # caracteres digitado a mao e' dificil de auditar; verificado programaticamente
    # antes de entrar neste plano). PETRA153, CODBDI=78 (CALL), strike 15.34,
    # vencimento 2025-01-17, preult=2.23, preofc/preofv=2.22/2.24, totneg=10.
    linha_call = (
        _campo_teste("01", 2) + _campo_teste("20240614", 8) + _campo_teste("78", 2)
        + _campo_teste("PETRA153", 12, "esquerda") + _campo_teste("070", 3)
        + _campo_teste("PETR    /EDJ", 12, "esquerda") + _campo_teste("ON      N2", 10, "esquerda")
        + _campo_teste("", 3, "esquerda") + _campo_teste("R$", 4, "esquerda")
        + _campo_teste(223, 13) + _campo_teste(223, 13) + _campo_teste(218, 13) + _campo_teste(220, 13)
        + _campo_teste(223, 13)   # PREULT = 2.23
        + _campo_teste(222, 13)   # PREOFC = 2.22
        + _campo_teste(224, 13)   # PREOFV = 2.24
        + _campo_teste(10, 5)     # TOTNEG
        + _campo_teste(100000, 18)   # QUATOT
        + _campo_teste(5000000, 18)  # VOLTOT = 50000.00
        + _campo_teste(1534, 13)     # PREEXE = 15.34
        + _campo_teste("1", 1) + _campo_teste("20250117", 8)  # INDOPC + DATVEN
        + _campo_teste("0000001", 7) + _campo_teste(0, 13)     # FATCOT + PTOEXE
        + _campo_teste("", 12, "esquerda") + _campo_teste("0", 3)  # CODISI + DISMES
    )
    assert len(linha_call) == 245, f"linha sintetica com {len(linha_call)} bytes, esperado 245"

    resultado = parsear_linha(linha_call)
    assert resultado is not None
    assert resultado["codbdi"] == "78"
    assert resultado["codneg"] == "PETRA153"
    assert resultado["preexe"] == 15.34
    assert resultado["datven"] == "20250117"
    assert resultado["preult"] == 2.23
    print("[OK] Caso 1: parsear_linha extrai um registro de opcao CALL corretamente.")

    # Linha malformada (curta demais) -> None, sem excecao
    assert parsear_linha("linha muito curta") is None
    print("[OK] Caso 2: linha malformada -> None, sem excecao.")

    # Linha de header/trailer (TIPREG != "01") -> None
    linha_header = "00" + " " * 243
    assert parsear_linha(linha_header) is None
    print("[OK] Caso 3: linha de header/trailer (TIPREG != 01) -> None.")

    # raiz_ticker
    assert raiz_ticker("PETRA153    ") == "PETR"
    assert raiz_ticker("ITUB4       ") == "ITUB"
    print("[OK] Caso 4: raiz_ticker extrai os 4 primeiros caracteres, sem espacos.")

    print("\nTodos os casos passaram.")
```

- [ ] **Step 2: Rodar para confirmar que falha**

Run: `python modules\opcoes\coleta_cotahist.py`
Expected: `NameError: name 'parsear_linha' is not defined`

- [ ] **Step 3: Implementar o mínimo necessário**

Inserir antes do bloco `if __name__ == "__main__":`:

```python
def _decimal(texto: str) -> float:
    """Campos COTAHIST de preco/volume sao inteiros de largura fixa com 2 casas
    decimais implicitas (sem ponto no texto) - ex.: '0000000000223' -> 2.23."""
    return int(texto) / 100.0


def parsear_linha(linha: str) -> dict | None:
    """Extrai os campos relevantes de uma linha de 245 bytes do COTAHIST.
    Devolve None se nao for um registro de dado (TIPREG != '01') ou se a linha
    estiver malformada - nunca lanca excecao por linha ruim."""
    try:
        if len(linha) < 245:
            return None
        if linha[0:2] != "01":
            return None
        return {
            "data": linha[2:10],
            "codbdi": linha[10:12],
            "codneg": linha[12:24].strip(),
            "tpmerc": linha[24:27],
            "nomres": linha[27:39].strip(),
            "preult": _decimal(linha[108:121]),
            "preofc": _decimal(linha[121:134]),
            "preofv": _decimal(linha[134:147]),
            "totneg": int(linha[147:152]),
            "voltot": _decimal(linha[170:188]),
            "preexe": _decimal(linha[188:201]),
            "datven": linha[202:210],
        }
    except (ValueError, IndexError):
        return None


def raiz_ticker(codneg: str) -> str:
    """Os 4 primeiros caracteres de um CODNEG (raiz do ticker, ex. 'PETR' de
    'PETRA153') - chave de casamento opcao->acao (NOMRES nao e' confiavel pra
    isso em registros de opcao, ver docstring do modulo)."""
    return codneg.strip().upper()[:4]


def garantir_schema_estendido(db_path=None) -> None:
    """Adiciona as colunas novas em opcoes_historico (Bid/Ask/Volume/Num_Negocios) -
    idempotente, aditivo. Linhas existentes (fonte brapi) ficam NULL nelas."""
    con = sqlite3.connect(db_path or db_opcoes.DB_PATH)
    for coluna, tipo in (("Bid", "REAL"), ("Ask", "REAL"),
                         ("Volume", "REAL"), ("Num_Negocios", "INTEGER")):
        try:
            con.execute(f"ALTER TABLE opcoes_historico ADD COLUMN {coluna} {tipo}")
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise
    con.commit()
    con.close()
```

- [ ] **Step 4: Rodar para confirmar que passa**

Run: `python modules\opcoes\coleta_cotahist.py`
Expected: as 4 linhas `[OK] Caso N: ...` impressas em ordem, seguidas de
`Todos os casos passaram.`, sem `AssertionError` nem traceback.

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/coleta_cotahist.py
git commit -m "feat: adicionar parser de linha COTAHIST e extensao do schema opcoes_historico"
```

---

## Task 2: Indexação de ações à vista e casamento com opções

**Files:**
- Modify: `modules/opcoes/coleta_cotahist.py`

**Interfaces:**
- Consumes: `parsear_linha`, `raiz_ticker`, `CODBDI_CALL`, `CODBDI_PUT`, `CODBDI_VISTA` (Task 1).
- Produces: `indexar_vista(linhas_parseadas: list[dict]) -> dict[tuple[str, str], tuple[float, float]]` — chave `(data, raiz)`, valor `(preult, voltot)` da ação de maior `voltot` entre as que compartilham a raiz naquele dia.
- Produces: `casar_opcoes(linhas_parseadas: list[dict], indice_vista: dict) -> list[dict]` — para cada linha de opção (`codbdi` em `CODBDI_CALL`/`CODBDI_PUT`), acrescenta a chave `"preco_ativo"` (do índice) e `"tipo"` (`"CALL"`/`"PUT"`). Descarta silenciosamente as sem correspondência no índice.

- [ ] **Step 1: Escrever o teste (assert) antes da implementação**

Adicionar ao final do bloco `if __name__ == "__main__":`, antes do
`print("\nTodos os casos passaram.")`:

```python
    # Caso 5: indexar_vista mantem a classe de maior volume quando ha mais de uma
    # com a mesma raiz no mesmo dia (ex.: ON e PN do mesmo emissor)
    linhas_vista = [
        {"data": "20240614", "codbdi": "02", "codneg": "PETR3", "voltot": 1000.0, "preult": 37.10},
        {"data": "20240614", "codbdi": "02", "codneg": "PETR4", "voltot": 50000.0, "preult": 35.50},
    ]
    indice = indexar_vista(linhas_vista)
    assert indice[("20240614", "PETR")] == (35.50, 50000.0)  # PETR4 venceu por volume
    print("[OK] Caso 5: indexar_vista mantem a classe de maior volume por (data, raiz).")

    # Caso 6: casar_opcoes acrescenta preco_ativo e tipo; sem correspondencia -> descarta
    linhas_opcoes = [
        {"data": "20240614", "codbdi": "78", "codneg": "PETRA153", "preexe": 15.34, "datven": "20250117"},
        {"data": "20240614", "codbdi": "82", "codneg": "PETRP200", "preexe": 20.00, "datven": "20250117"},
        {"data": "20240614", "codbdi": "78", "codneg": "XXXXA100", "preexe": 10.00, "datven": "20250117"},  # sem raiz no indice
    ]
    casadas = casar_opcoes(linhas_opcoes, indice)
    assert len(casadas) == 2  # a terceira (raiz "XXXX") foi descartada
    assert all(c["preco_ativo"] == 35.50 for c in casadas)
    assert {c["tipo"] for c in casadas} == {"CALL", "PUT"}
    print("[OK] Caso 6: casar_opcoes junta preco_ativo pela raiz e descarta sem correspondencia.")
```

- [ ] **Step 2: Rodar para confirmar que falha**

Run: `python modules\opcoes\coleta_cotahist.py`
Expected: `NameError: name 'indexar_vista' is not defined`

- [ ] **Step 3: Implementar o mínimo necessário**

Inserir depois de `garantir_schema_estendido` (antes do `if __name__`):

```python
def indexar_vista(linhas_parseadas: list[dict]) -> dict[tuple[str, str], tuple[float, float]]:
    """Indexa registros de acao a vista (CODBDI='02') por (data, raiz do ticker),
    mantendo o de maior volume quando mais de uma classe do emissor compartilha a
    raiz no mesmo dia (ex.: ON e PN) - opcoes quase sempre sao escritas na classe
    mais liquida, entao essa e' a candidata certa."""
    indice: dict[tuple[str, str], tuple[float, float]] = {}
    for linha in linhas_parseadas:
        if linha["codbdi"] != CODBDI_VISTA:
            continue
        chave = (linha["data"], raiz_ticker(linha["codneg"]))
        atual = indice.get(chave)
        if atual is None or linha["voltot"] > atual[1]:
            indice[chave] = (linha["preult"], linha["voltot"])
    return indice


def casar_opcoes(linhas_parseadas: list[dict], indice_vista: dict) -> list[dict]:
    """Para cada registro de opcao, busca o preco do ativo-objeto pela raiz do
    ticker no mesmo dia. Sem correspondencia -> descarta a linha (nunca inventa
    Preco_Ativo)."""
    casadas = []
    for linha in linhas_parseadas:
        if linha["codbdi"] == CODBDI_CALL:
            tipo = "CALL"
        elif linha["codbdi"] == CODBDI_PUT:
            tipo = "PUT"
        else:
            continue
        chave = (linha["data"], raiz_ticker(linha["codneg"]))
        entrada = indice_vista.get(chave)
        if entrada is None:
            continue
        preco_ativo, _voltot = entrada
        casadas.append({**linha, "tipo": tipo, "preco_ativo": preco_ativo})
    return casadas
```

- [ ] **Step 4: Rodar para confirmar que passa**

Run: `python modules\opcoes\coleta_cotahist.py`
Expected: `[OK] Caso 5` e `[OK] Caso 6` impressos, seguidos de `Todos os casos passaram.`,
sem erro.

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/coleta_cotahist.py
git commit -m "feat: indexar acoes a vista e casar opcoes pela raiz do ticker"
```

---

## Task 3: Cálculo de IV, gravação e orquestração (download + CLI)

**Files:**
- Modify: `modules/opcoes/coleta_cotahist.py`

**Interfaces:**
- Consumes: `parsear_linha`, `indexar_vista`, `casar_opcoes`, `garantir_schema_estendido` (Tasks 1-2); `analises_opcoes.implied_vol(tipo, mkt, S, K, T, r)` (já existe, mesma assinatura usada em `analisar()`).
- Produces: `dias_ate_vencimento(data: str, datven: str) -> int` — dias corridos entre `data` e `datven` (formato `AAAAMMDD`), mínimo 1.
- Produces: `montar_linha_historico(opcao_casada: dict, selic: float) -> dict` — monta o dict pronto para `INSERT` em `opcoes_historico` (colunas: `Codigo_Opcao, Ativo_Objeto, Tipo, Strike, Data_Vencimento, Data, Preco_Ativo, Preco_Opcao, IV, Delta, Gamma, Theta, Vega, Taxa_Livre_Risco, Bid, Ask, Volume, Num_Negocios, Fonte`); `Ativo_Objeto` = raiz do ticker; `Delta/Gamma/Theta/Vega` ficam `None` (COTAHIST não traz gregas, só a IV é recalculada); `Fonte='b3_cotahist'`.
- Produces: `selic_mais_proxima(data: str, selic_por_data: dict[str, float]) -> float | None` — busca a leitura de Selic de data igual ou mais próxima disponível (nunca inventa, `None` se a lista estiver vazia).
- Produces: `gravar_historico(linhas: list[dict], db_path=None) -> int` — grava em `opcoes_historico` via `INSERT ... ON CONFLICT(Codigo_Opcao, Data) DO UPDATE`, devolve a contagem gravada.
- Produces: `baixar_e_extrair(ano: int) -> str` — baixa o ZIP de
  `https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{ano}.ZIP` e devolve o
  conteúdo do `.TXT` decodificado (`latin-1`) como um único `str` (o arquivo cabe em
  memória - ~300-400MB de texto por ano, aceitável para um backfill manual).
- Produces: `processar_ano(ano: int, db_path=None) -> None` — orquestra tudo: baixar,
  parsear todas as linhas, indexar vista, casar opções, calcular IV (usando a Selic de
  `indicadores_bcb`), gravar, imprimir progresso.

- [ ] **Step 1: Escrever o teste (assert) antes da implementação**

Adicionar ao bloco de teste, antes do `print("\nTodos os casos passaram.")`:

```python
    # Caso 7: dias_ate_vencimento
    assert dias_ate_vencimento("20240614", "20250117") == 217
    assert dias_ate_vencimento("20240614", "20240614") == 1  # minimo 1, nunca 0
    print("[OK] Caso 7: dias_ate_vencimento calcula a diferenca em dias corridos, minimo 1.")

    # Caso 8: selic_mais_proxima - pega a leitura de data igual ou mais proxima disponivel
    selic_por_data = {"20240610": 10.50, "20240617": 10.25}
    assert selic_mais_proxima("20240614", selic_por_data) in (10.50, 10.25)  # uma das duas, nunca inventada
    assert selic_mais_proxima("20240610", selic_por_data) == 10.50  # bate exato
    assert selic_mais_proxima("20240614", {}) is None  # sem leituras -> None, nao inventa
    print("[OK] Caso 8: selic_mais_proxima nunca inventa uma leitura que nao existe.")

    # Caso 9: montar_linha_historico monta o dict com os campos certos
    opcao_exemplo = {
        "data": "20240614", "codneg": "PETRA153", "tipo": "CALL", "preexe": 15.34,
        "datven": "20250117", "preco_ativo": 35.50, "preult": 2.23,
        "preofc": 2.22, "preofv": 2.24, "voltot": 50000.0, "totneg": 10,
    }
    linha_pronta = montar_linha_historico(opcao_exemplo, selic=0.1050)
    assert linha_pronta["Codigo_Opcao"] == "PETRA153"
    assert linha_pronta["Ativo_Objeto"] == "PETR"
    assert linha_pronta["Tipo"] == "CALL"
    assert linha_pronta["Strike"] == 15.34
    assert linha_pronta["Preco_Ativo"] == 35.50
    assert linha_pronta["Preco_Opcao"] == 2.23
    assert linha_pronta["Bid"] == 2.22 and linha_pronta["Ask"] == 2.24
    assert linha_pronta["Fonte"] == "b3_cotahist"
    assert 0.0 <= linha_pronta["IV"] <= 5.0  # implied_vol() sempre devolve algo nessa faixa
    print("[OK] Caso 9: montar_linha_historico monta a linha com IV calculada e Fonte correta.")

    # Caso 10: gravar_historico e idempotente (rodar duas vezes nao duplica)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        db_teste = os.path.join(tmp, "teste_cotahist.db")
        garantir_schema_estendido(db_teste)
        n1 = gravar_historico([linha_pronta], db_teste)
        n2 = gravar_historico([linha_pronta], db_teste)
        assert n1 == 1 and n2 == 1
        con = sqlite3.connect(db_teste)
        total = con.execute("SELECT COUNT(*) FROM opcoes_historico").fetchone()[0]
        con.close()
        assert total == 1  # nao duplicou
    print("[OK] Caso 10: gravar_historico e idempotente (ON CONFLICT DO UPDATE).")
```

Nota: o Caso 10 chama `garantir_schema_estendido(db_teste)` antes de gravar, mas
`opcoes_historico` só é criada por `db_opcoes.init_schema()` — inclua essa chamada
também:

```python
        db_opcoes.init_schema(db_teste)
        garantir_schema_estendido(db_teste)
```

(ajuste o Caso 10 acima para chamar `db_opcoes.init_schema(db_teste)` logo antes de
`garantir_schema_estendido(db_teste)`.)

- [ ] **Step 2: Rodar para confirmar que falha**

Run: `python modules\opcoes\coleta_cotahist.py`
Expected: `NameError: name 'dias_ate_vencimento' is not defined`

- [ ] **Step 3: Implementar o mínimo necessário**

Adicionar aos imports do topo do arquivo:

```python
from datetime import date
import analises_opcoes as ao
```

Inserir depois de `casar_opcoes` (antes do `if __name__`):

```python
def dias_ate_vencimento(data: str, datven: str) -> int:
    """Dias corridos entre duas datas AAAAMMDD, minimo 1 (nunca 0 - protege
    contra divisao por T=0 no calculo de IV)."""
    d1 = date(int(data[0:4]), int(data[4:6]), int(data[6:8]))
    d2 = date(int(datven[0:4]), int(datven[4:6]), int(datven[6:8]))
    return max(1, (d2 - d1).days)


def selic_mais_proxima(data: str, selic_por_data: dict[str, float]) -> float | None:
    """Leitura de Selic de data igual ou mais proxima disponivel. None se nao
    houver nenhuma leitura - nunca inventa um valor."""
    if not selic_por_data:
        return None
    if data in selic_por_data:
        return selic_por_data[data]
    mais_proxima = min(selic_por_data.keys(), key=lambda d: abs(int(d) - int(data)))
    return selic_por_data[mais_proxima]


def montar_linha_historico(opcao_casada: dict, selic: float) -> dict:
    """Monta a linha pronta pra gravar em opcoes_historico a partir de uma opcao
    ja casada com o ativo-objeto (casar_opcoes) e a Selic do dia."""
    dias = dias_ate_vencimento(opcao_casada["data"], opcao_casada["datven"])
    T = dias / 365
    iv = ao.implied_vol(
        opcao_casada["tipo"], opcao_casada["preult"], opcao_casada["preco_ativo"],
        opcao_casada["preexe"], T, selic,
    )
    return {
        "Codigo_Opcao": opcao_casada["codneg"],
        "Ativo_Objeto": raiz_ticker(opcao_casada["codneg"]),
        "Tipo": opcao_casada["tipo"],
        "Strike": opcao_casada["preexe"],
        "Data_Vencimento": (f"{opcao_casada['datven'][0:4]}-{opcao_casada['datven'][4:6]}"
                            f"-{opcao_casada['datven'][6:8]}"),
        "Data": (f"{opcao_casada['data'][0:4]}-{opcao_casada['data'][4:6]}"
                f"-{opcao_casada['data'][6:8]}"),
        "Preco_Ativo": opcao_casada["preco_ativo"],
        "Preco_Opcao": opcao_casada["preult"],
        "IV": iv,
        "Delta": None, "Gamma": None, "Theta": None, "Vega": None,
        "Taxa_Livre_Risco": selic,
        "Bid": opcao_casada["preofc"],
        "Ask": opcao_casada["preofv"],
        "Volume": opcao_casada["voltot"],
        "Num_Negocios": opcao_casada["totneg"],
        "Fonte": "b3_cotahist",
    }


def gravar_historico(linhas: list[dict], db_path=None) -> int:
    """Grava as linhas em opcoes_historico (idempotente, mesmo padrao de
    coleta_opcoes_historico.py::coletar_serie())."""
    con = sqlite3.connect(db_path or db_opcoes.DB_PATH)
    n = 0
    for linha in linhas:
        con.execute("""
            INSERT INTO opcoes_historico
                (Codigo_Opcao, Ativo_Objeto, Tipo, Strike, Data_Vencimento, Data,
                 Preco_Ativo, Preco_Opcao, IV, Delta, Gamma, Theta, Vega,
                 Taxa_Livre_Risco, Bid, Ask, Volume, Num_Negocios, Fonte)
            VALUES
                (:Codigo_Opcao, :Ativo_Objeto, :Tipo, :Strike, :Data_Vencimento, :Data,
                 :Preco_Ativo, :Preco_Opcao, :IV, :Delta, :Gamma, :Theta, :Vega,
                 :Taxa_Livre_Risco, :Bid, :Ask, :Volume, :Num_Negocios, :Fonte)
            ON CONFLICT(Codigo_Opcao, Data) DO UPDATE SET
                Preco_Ativo=excluded.Preco_Ativo, Preco_Opcao=excluded.Preco_Opcao,
                IV=excluded.IV, Taxa_Livre_Risco=excluded.Taxa_Livre_Risco,
                Bid=excluded.Bid, Ask=excluded.Ask, Volume=excluded.Volume,
                Num_Negocios=excluded.Num_Negocios
        """, linha)
        n += 1
    con.commit()
    con.close()
    return n


def baixar_e_extrair(ano: int) -> str:
    """Baixa o ZIP anual da B3 e devolve o conteudo do .TXT como string."""
    import io, zipfile, requests
    url = f"https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{ano}.ZIP"
    print(f"Baixando {url} ...")
    resposta = requests.get(url, timeout=180)
    resposta.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resposta.content)) as z:
        nome_arquivo = f"COTAHIST_A{ano}.TXT"
        with z.open(nome_arquivo) as f:
            return f.read().decode("latin-1")


def processar_ano(ano: int, db_path=None) -> None:
    """Orquestra a coleta de um ano: baixa, parseia, indexa, casa, calcula IV e
    grava em opcoes_historico."""
    db_opcoes.init_schema(db_path)
    garantir_schema_estendido(db_path)

    texto = baixar_e_extrair(ano)
    print(f"Arquivo de {ano} baixado, parseando linhas...")

    linhas_parseadas = []
    for linha in texto.splitlines():
        resultado = parsear_linha(linha)
        if resultado is not None:
            linhas_parseadas.append(resultado)
    print(f"{len(linhas_parseadas)} linhas de dado parseadas.")

    indice_vista = indexar_vista(linhas_parseadas)
    print(f"{len(indice_vista)} combinacoes (data, raiz) indexadas no mercado a vista.")

    casadas = casar_opcoes(linhas_parseadas, indice_vista)
    print(f"{len(casadas)} registros de opcao casados com o ativo-objeto.")

    from db import engine
    import pandas as pd
    selic_df = pd.read_sql(
        "SELECT data, valor FROM indicadores_bcb WHERE indicador = 'Selic'", engine)
    selic_por_data = {
        str(row["data"])[:10].replace("-", ""): float(row["valor"]) / 100
        for _, row in selic_df.iterrows()
    }
    print(f"{len(selic_por_data)} leituras de Selic disponiveis para taxa livre de risco.")

    linhas_prontas = []
    for opcao in casadas:
        selic = selic_mais_proxima(opcao["data"], selic_por_data)
        if selic is None:
            continue  # sem nenhuma leitura de Selic disponivel - nao inventa taxa
        linhas_prontas.append(montar_linha_historico(opcao, selic))

    total_gravado = gravar_historico(linhas_prontas, db_path)
    print(f"{total_gravado} linhas gravadas em opcoes_historico (Fonte='b3_cotahist').")
```

Adicionar o bloco de execução real, **depois** do bloco de asserts existente
(dentro do mesmo `if __name__ == "__main__":`, ao final):

```python
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ano", type=int, action="append",
                    help="ano a processar (pode repetir --ano varias vezes)")
    args = ap.parse_args()
    anos = args.ano or [2024, 2025]
    for ano in anos:
        processar_ano(ano)
```

- [ ] **Step 4: Rodar para confirmar que os asserts passam**

Run: `python modules\opcoes\coleta_cotahist.py --ano 2024`
Expected: as linhas `[OK] Caso 7` a `[OK] Caso 10` impressas, seguidas de
`Todos os casos passaram.` — e **depois disso**, o script segue pra execução real
(baixa e processa 2024, pode levar alguns minutos; arquivo tem dezenas de MB).
Confirmar que não há traceback nem nos asserts, nem na execução real, e que a
mensagem final `N linhas gravadas em opcoes_historico (Fonte='b3_cotahist')` aparece
com `N > 0`.

- [ ] **Step 5: Verificação manual contra dado real (spec, seção 7)**

Depois do Step 4 passar, comparar uma série conhecida da PETR4 entre as duas fontes,
pra checar que os números fazem sentido (mesma ordem de grandeza, não necessariamente
idênticos - a brapi e a B3 podem ter pequenas diferenças de metodologia):

```python
import sqlite3
con = sqlite3.connect("data/mercado.db")
print(con.execute(
    "SELECT Fonte, COUNT(*), MIN(Data), MAX(Data) FROM opcoes_historico "
    "WHERE Ativo_Objeto='PETR' GROUP BY Fonte").fetchall())
con.close()
```

Confirmar que aparecem linhas com `Fonte='b3_cotahist'` e `Fonte='brapi'` (ou similar),
ambas com contagens plausíveis, e que a faixa de datas da fonte B3 cobre 2024
inteiro (não só alguns dias).

- [ ] **Step 6: Rodar o backtest com a amostra ampliada**

Run: `python modules\opcoes\backtest_opcoes.py`
Expected: sem traceback; `n_sinais` na tabela de calibração deve ser sensivelmente
maior que antes desta mudança (63 séries/51 sinais era o número anterior, só com
PETR4 via brapi). Reportar o resultado ao usuário — não aplicar nenhum peso
automaticamente (mesma cautela da spec de 2026-08-30-score-opcoes-sem-desconto-design.md:
só aplicar peso calibrado se algum `edge` real aparecer).

- [ ] **Step 7: Commit**

```bash
git add modules/opcoes/coleta_cotahist.py
git commit -m "feat: coletar historico de opcoes via COTAHIST (B3) - 2024-2025"
```

Rodar `--ano 2025` também (mesmo comando, `--ano 2025`) antes ou depois do commit,
conforme preferir - é uma execução de dados, não uma mudança de código.

---

## Self-Review

**Spec coverage:**
- Seção 3 (arquitetura: baixar, parsear, indexar, casar, IV, gravar) → Tasks 1-3.
- Seção 4 (layout do arquivo, posições exatas) → Global Constraints + Task 1.
- Seção 4.2 (extensão do schema) → Task 1 (`garantir_schema_estendido`).
- Seção 5 (erros e casos vazios: sem correspondência, linha malformada, Selic
  ausente, idempotência) → Tasks 1-3, casos de teste 2, 3, 6, 8, 10.
- Seção 6 (verificação de URL e casamento) → já feita antes deste plano, registrada
  em "Verificação já feita" e nas Global Constraints.
- Seção 7 (teste unitário + verificação real) → Tasks 1-3 (unitário) + Task 3 Steps
  5-6 (real).

**Placeholder scan:** nenhum "TBD"/"TODO" — todos os steps têm código completo.

**Type consistency:** `parsear_linha`/`raiz_ticker` (Task 1) usados com a mesma
assinatura em `indexar_vista`/`casar_opcoes` (Task 2) e em `processar_ano` (Task 3).
Chaves do dict de `parsear_linha` (`data, codbdi, codneg, tpmerc, nomres, preult,
preofc, preofv, totneg, voltot, preexe, datven`) usadas de forma consistente em
`indexar_vista`, `casar_opcoes` e `montar_linha_historico` em todas as tasks.
