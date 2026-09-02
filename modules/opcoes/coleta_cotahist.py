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

Casamento opcao->acao: pelos 4 primeiros caracteres do CODNEG (raiz do ticker),
NAO por NOMRES - verificado contra dado real (PETR/ITUB, 14/06/2024) que o NOMRES
de um registro de opcao vem truncado/diferente do NOMRES limpo da acao. Em caso de
mais de uma classe com a mesma raiz no mesmo dia, fica a de maior volume (VOLTOT).
"""
from __future__ import annotations
import os, sys, sqlite3
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
# repo root, para "from db import engine" e "from carteira import ..." (nao usado
# aqui, mas mesma necessidade) - mesmo padrao ja usado em coleta_opcoes.py
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import db_opcoes
import analises_opcoes as ao
import coleta_opcoes_historico as coh  # dono da tabela opcoes_historico (init_hist_schema)

CODBDI_CALL = "78"
CODBDI_PUT = "82"
CODBDI_VISTA = "02"


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
    idempotente, aditivo. Linhas existentes (fonte brapi) ficam NULL nelas.

    Pressupoe que a tabela opcoes_historico ja existe - chamar
    coleta_opcoes_historico.init_hist_schema(db_path) antes (essa e' a dona da
    tabela; este modulo so acrescenta colunas nela)."""
    con = sqlite3.connect(db_path or db_opcoes.DB_PATH)
    try:
        for coluna, tipo in (("Bid", "REAL"), ("Ask", "REAL"),
                             ("Volume", "REAL"), ("Num_Negocios", "INTEGER")):
            try:
                con.execute(f"ALTER TABLE opcoes_historico ADD COLUMN {coluna} {tipo}")
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise
        con.commit()
    finally:
        con.close()


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


def montar_linha_historico(opcao_casada: dict, selic: float, iv: float) -> dict:
    """Monta a linha pronta pra gravar em opcoes_historico a partir de uma opcao
    ja casada com o ativo-objeto (casar_opcoes), a Selic do dia, e a IV ja
    calculada. IV entra pronta (nao e' calculada aqui dentro) porque
    processar_ano calcula todas de uma vez, em lote, via
    analises_opcoes.implied_vol_lote() - calcular uma a uma nesta funcao seria
    impraticavel no volume de um backfill COTAHIST (medido: >24ms/chamada da
    versao escalar, ~13h estimadas para 2 milhoes de linhas)."""
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
    coh.init_hist_schema(db_path)
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

    # Selic vem do MESMO SQLite local de opcoes_historico (db_path ou
    # db_opcoes.DB_PATH), nao do Postgres remoto (db.engine/DATABASE_URL).
    # modules/opcoes/ e' deliberadamente isolado do banco remoto do app (ver
    # db_opcoes.py) - usar o engine remoto aqui violava esse isolamento e foi
    # a causa raiz de duas falhas reais num job de ~2 milhoes de linhas: um
    # PendingRollbackError por conexao pooled expirada, e depois um socket
    # preso em CloseWait travando o processo indefinidamente (conexao viva
    # morrendo no meio de uma fase longa de CPU). Ler do arquivo local
    # elimina a dependencia de rede desta etapa por completo. A Selic
    # historica precisa estar previamente carregada nesse mesmo arquivo via
    # `python coleta_bcb_historico.py --db-path <db_path>`.
    con_selic = sqlite3.connect(db_path or db_opcoes.DB_PATH)
    try:
        linhas_selic = con_selic.execute(
            "SELECT data, valor FROM indicadores_bcb WHERE indicador = 'Selic'").fetchall()
    finally:
        con_selic.close()
    selic_por_data = {
        str(data)[:10].replace("-", ""): float(valor) / 100
        for data, valor in linhas_selic
    }
    print(f"{len(selic_por_data)} leituras de Selic disponiveis para taxa livre de risco.")

    # Filtra so as que tem Selic disponivel (nunca inventa taxa) e guarda a
    # selic de cada uma pra usar no calculo de IV em lote logo abaixo.
    com_selic = []
    for opcao in casadas:
        selic = selic_mais_proxima(opcao["data"], selic_por_data)
        if selic is not None:
            com_selic.append((opcao, selic))
    print(f"{len(com_selic)} registros com Selic disponivel (serao gravados).")

    if not com_selic:
        print("Nenhum registro com Selic disponivel - nada gravado.")
        return

    # IV em lote (vetorizado) - calcular uma a uma levaria horas nesse volume
    # (medido: >24ms/chamada da versao escalar implied_vol()).
    tipos = [opcao["tipo"] for opcao, _ in com_selic]
    mkts = [opcao["preult"] for opcao, _ in com_selic]
    spots = [opcao["preco_ativo"] for opcao, _ in com_selic]
    strikes = [opcao["preexe"] for opcao, _ in com_selic]
    prazos = [dias_ate_vencimento(opcao["data"], opcao["datven"]) / 365 for opcao, _ in com_selic]
    taxas = [selic for _, selic in com_selic]
    ivs = ao.implied_vol_lote(tipos, mkts, spots, strikes, prazos, taxas)
    print(f"IV calculada em lote para {len(ivs)} registros.")

    # Newton-Raphson vetorizado com iteracoes fixas nao converge quando vega
    # e' proximo de zero (opcoes fundo ITM/OTM, vistas na pratica com
    # moneyness medio ~0.54 vs ~0.11 nas IVs razoaveis) - o sigma so' fica
    # preso no clip de implied_vol_lote (piso 1e-4 ou teto 5.0), nao e' uma
    # IV real. Medido em 2024: ~11.2% das linhas (10.8% no piso + 0.35% no
    # teto) - descartadas aqui pra nao poluir o backtest/Score com sinal
    # falso. Ver docs/superpowers/plans/2026-08-30-coleta-cotahist-b3.md.
    PISO_IV, TETO_IV = 1e-4, 5.0
    linhas_prontas = []
    n_descartadas_iv = 0
    for (opcao, selic), iv in zip(com_selic, ivs):
        iv = float(iv)
        if iv <= PISO_IV * 1.001 or iv >= TETO_IV * 0.9998:
            n_descartadas_iv += 1
            continue
        linhas_prontas.append(montar_linha_historico(opcao, selic, iv))
    print(f"{n_descartadas_iv} registros descartados (IV presa no piso/teto do solver, nao convergiu).")

    total_gravado = gravar_historico(linhas_prontas, db_path)
    print(f"{total_gravado} linhas gravadas em opcoes_historico (Fonte='b3_cotahist').")


def _campo_teste(valor, largura, alinhar="direita"):
    """So para montar linhas sinteticas de teste (nao faz parte da coleta real) -
    largura fixa, preenchida com '0' a direita ou com espaco a esquerda, igual ao
    layout oficial do COTAHIST."""
    texto = str(valor)
    return texto.rjust(largura, "0") if alinhar == "direita" else texto.ljust(largura, " ")


if __name__ == "__main__":
    # Linha sintetica de opcao CALL (245 bytes), montada campo a campo com a largura
    # exata do layout oficial. PETRA153, CODBDI=78 (CALL), strike 15.34,
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
    linha_pronta = montar_linha_historico(opcao_exemplo, selic=0.1050, iv=0.32)
    assert linha_pronta["Codigo_Opcao"] == "PETRA153"
    assert linha_pronta["Ativo_Objeto"] == "PETR"
    assert linha_pronta["Tipo"] == "CALL"
    assert linha_pronta["Strike"] == 15.34
    assert linha_pronta["Preco_Ativo"] == 35.50
    assert linha_pronta["Preco_Opcao"] == 2.23
    assert linha_pronta["Bid"] == 2.22 and linha_pronta["Ask"] == 2.24
    assert linha_pronta["Fonte"] == "b3_cotahist"
    assert linha_pronta["IV"] == 0.32  # IV entra pronta (calculada em lote fora desta funcao)
    print("[OK] Caso 9: montar_linha_historico monta a linha com a IV recebida e Fonte correta.")

    # Caso 10: gravar_historico e idempotente (rodar duas vezes nao duplica)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        db_teste = os.path.join(tmp, "teste_cotahist.db")
        coh.init_hist_schema(db_teste)
        garantir_schema_estendido(db_teste)
        n1 = gravar_historico([linha_pronta], db_teste)
        n2 = gravar_historico([linha_pronta], db_teste)
        assert n1 == 1 and n2 == 1
        con = sqlite3.connect(db_teste)
        total = con.execute("SELECT COUNT(*) FROM opcoes_historico").fetchone()[0]
        con.close()
        assert total == 1  # nao duplicou
    print("[OK] Caso 10: gravar_historico e idempotente (ON CONFLICT DO UPDATE).")

    print("\nTodos os casos passaram.")

    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ano", type=int, action="append",
                    help="ano a processar (pode repetir --ano varias vezes)")
    args = ap.parse_args()
    anos = args.ano or [2024, 2025]
    for ano in anos:
        processar_ano(ano)
