# coleta_cvm.py — cadastro de companhias abertas e comunicados (IPE) da CVM.
#
# Duas coletas do portal de dados abertos (mesmo padrao de coleta_debentures.py):
#
# 1. Cadastro (cad_cia_aberta.csv, ~1,5 MB): as companhias registradas. Guardamos
#    so' as ATIVAS - sao 756 de 2.677, e e' o que torna a busca por nome usavel.
# 2. IPE (ipe_cia_aberta_<ano>.zip, ~2,3 MB): comunicados ao mercado, fatos
#    relevantes, avisos aos acionistas.
#
# POR QUE CASAR POR CNPJ E NAO POR NOME. Medido no dado real de 2025: buscar
# "VALE" pelo nome traz 324 registros, quase todos de empresas agricolas
# ("AGRO INDUSTRIAS DO VALE SAO FRANCISCO", "VALE BONITO AGROPECUARIA"); "ITAU"
# traz a "COMPANHIA ITAUNENSE ENERGIA" junto do Itau Unibanco. Filtrando o
# cadastro por ATIVO, "VALE" cai para 2 candidatas e "ITAU" para 3 - ai' o
# usuario escolhe UMA VEZ, o CNPJ fica gravado, e todo casamento seguinte e'
# exato.
#
# Uso:
#     python coleta_cvm.py              # cadastro + IPE do ano corrente
#     python coleta_cvm.py --ano 2024   # IPE de outro ano
#     python coleta_cvm.py --teste      # auto-testes (sem rede)
import io
import unicodedata
import zipfile
from datetime import date

import pandas as pd
import requests

URL_CADASTRO = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
URL_IPE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{ano}.zip"

# Categorias que interessam a quem acompanha a empresa. As demais (ex.:
# "Valores Mobiliarios negociados e detidos", 9.281 registros no ano) sao
# rotina regulatoria e afogariam o que importa.
CATEGORIAS_RELEVANTES = (
    "Fato Relevante",
    "Comunicado ao Mercado",
    "Aviso aos Acionistas",
    "Assembleia",
    "Reuniao da Administracao",   # carrega deliberacao de JCP e dividendo
)
# "Dados Economico-Financeiros" fica de FORA: inspecionando o dado real da
# Itausa, os assuntos ali sao "Versao em ingles" e duplicatas de traducao das
# demonstracoes - ruido, nao comunicado. Os numeros em si viriam do DFP/ITR,
# que e' outra fatia.


def so_digitos(valor) -> str:
    """CNPJ reduzido a digitos.

    O cadastro e o IPE hoje usam o mesmo formato ('08.773.135/0001-00'), mas
    normalizar torna o casamento imune a mudanca de formatacao de um lado so',
    e permite o usuario colar o CNPJ como quiser."""
    return "".join(c for c in str(valor or "") if c.isdigit())


def _normalizar(texto) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).upper()


def filtrar_ativas(cadastro: pd.DataFrame) -> pd.DataFrame:
    """So' as companhias com registro ATIVO na CVM.

    E' o filtro que torna a busca por nome utilizavel: das 2.677 do cadastro,
    756 estao ativas, e o resto sao registros cancelados que so' geram
    candidatas erradas na hora de escolher a empresa."""
    if cadastro.empty or "SIT" not in cadastro:
        return cadastro
    return cadastro[cadastro["SIT"].astype(str).str.strip().str.upper() == "ATIVO"]


def buscar_companhias(termo: str, companhias: pd.DataFrame) -> pd.DataFrame:
    """Companhias cujo nome contem o termo (sem acento, sem caixa).

    Alimenta a escolha do usuario no cadastro de empresa monitorada. Devolve
    varias candidatas de proposito: a desambiguacao e' humana e acontece uma
    vez so'."""
    termo = str(termo or "").strip()
    if not termo or companhias.empty:
        return companhias.head(0)
    alvo = _normalizar(termo)
    colunas = [c for c in ("denom_social", "denom_comerc") if c in companhias]
    if not colunas:
        return companhias.head(0)
    mascara = False
    for coluna in colunas:
        mascara = mascara | companhias[coluna].map(_normalizar).str.contains(alvo, na=False)
    return companhias[mascara]


def filtrar_ipe(ipe: pd.DataFrame, cnpjs, categorias=CATEGORIAS_RELEVANTES) -> pd.DataFrame:
    """Comunicados das empresas monitoradas, nas categorias que interessam.

    Filtrar na coleta e' o que evita gravar ~45 mil linhas por ano para
    guardar as poucas dezenas que voce acompanha."""
    if ipe.empty:
        return ipe
    alvos = {so_digitos(c) for c in (cnpjs or []) if so_digitos(c)}
    if not alvos:
        return ipe.head(0)
    resultado = ipe[ipe["CNPJ_Companhia"].map(so_digitos).isin(alvos)]
    if categorias:
        # Compara SEM acento: a categoria vem do CSV em latin-1 e depende de
        # grafia exata ("Reuniao" vs "Reuniao"). Normalizar evita que o filtro
        # falhe em silencio por um acento - o tipo de erro que so' aparece
        # quando alguem estranha a tabela vazia.
        alvos_cat = {_normalizar(c) for c in categorias}
        resultado = resultado[resultado["Categoria"].map(_normalizar).isin(alvos_cat)]
    return resultado


def baixar_cadastro() -> pd.DataFrame:
    """Cadastro de companhias abertas, ja normalizado e so' com as ativas."""
    resposta = requests.get(URL_CADASTRO, timeout=180)
    resposta.raise_for_status()
    bruto = pd.read_csv(io.BytesIO(resposta.content), sep=";", encoding="latin-1")
    ativas = filtrar_ativas(bruto)
    return pd.DataFrame({
        "cnpj": ativas["CNPJ_CIA"].map(so_digitos),
        "cnpj_formatado": ativas["CNPJ_CIA"],
        "denom_social": ativas["DENOM_SOCIAL"],
        "denom_comerc": ativas.get("DENOM_COMERC"),
        "setor": ativas.get("SETOR_ATIV"),
        "codigo_cvm": ativas.get("CD_CVM"),
    }).drop_duplicates(subset=["cnpj"])


def baixar_ipe(ano: int) -> pd.DataFrame:
    """Comunicados do ano, sem filtro (quem chama filtra)."""
    resposta = requests.get(URL_IPE.format(ano=ano), timeout=300)
    resposta.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resposta.content)) as z:
        nome = z.namelist()[0]
        return pd.read_csv(z.open(nome), sep=";", encoding="latin-1")


def _auto_teste() -> None:
    cadastro = pd.DataFrame([
        {"CNPJ_CIA": "33.000.167/0001-01", "DENOM_SOCIAL": "PETROLEO BRASILEIRO S.A. - PETROBRAS",
         "DENOM_COMERC": "PETROBRAS", "SIT": "ATIVO", "SETOR_ATIV": "Petroleo", "CD_CVM": 9512},
        {"CNPJ_CIA": "33.592.510/0001-54", "DENOM_SOCIAL": "VALE S.A.",
         "DENOM_COMERC": "VALE", "SIT": "ATIVO", "SETOR_ATIV": "Mineracao", "CD_CVM": 4170},
        {"CNPJ_CIA": "11.111.111/0001-11", "DENOM_SOCIAL": "VALE BONITO AGROPECUARIA S/A",
         "DENOM_COMERC": None, "SIT": "CANCELADA", "SETOR_ATIV": "Agro", "CD_CVM": 1},
    ])

    # Caso 1: so' as ativas sobrevivem - e' o que faz a busca por nome ser
    # usavel. Sem isso, "VALE" traria empresas agricolas canceladas junto.
    ativas = filtrar_ativas(cadastro)
    assert len(ativas) == 2
    assert "VALE BONITO AGROPECUARIA S/A" not in set(ativas["DENOM_SOCIAL"])
    print("[OK] Caso 1: filtrar_ativas descarta registro cancelado.")

    companhias = pd.DataFrame({
        "cnpj": ativas["CNPJ_CIA"].map(so_digitos),
        "denom_social": ativas["DENOM_SOCIAL"],
        "denom_comerc": ativas["DENOM_COMERC"],
    })

    # Caso 2: busca acha por razao social E por nome comercial, sem acento/caixa
    assert len(buscar_companhias("petrobras", companhias)) == 1
    assert len(buscar_companhias("VALE", companhias)) == 1
    assert len(buscar_companhias("petroleo", companhias)) == 1   # razao social
    assert len(buscar_companhias("inexistente", companhias)) == 0
    assert len(buscar_companhias("", companhias)) == 0
    print("[OK] Caso 2: busca por nome cobre razao social e nome comercial.")

    # Caso 3: CNPJ normalizado para digitos - casa mesmo com formatacao
    # diferente dos dois lados
    assert so_digitos("33.000.167/0001-01") == "33000167000101"
    assert so_digitos("33000167000101") == "33000167000101"
    assert so_digitos(None) == ""
    print("[OK] Caso 3: so_digitos normaliza CNPJ de qualquer formatacao.")

    ipe = pd.DataFrame([
        {"CNPJ_Companhia": "33.000.167/0001-01", "Categoria": "Fato Relevante",
         "Assunto": "Payout 2025"},
        {"CNPJ_Companhia": "33.000.167/0001-01", "Categoria": "Valores Mobiliarios negociados e detidos",
         "Assunto": "rotina"},
        {"CNPJ_Companhia": "99.999.999/0001-99", "Categoria": "Fato Relevante",
         "Assunto": "de outra empresa"},
    ])

    # Caso 4: filtra por CNPJ monitorado E por categoria relevante.
    # A linha de "Valores Mobiliarios" e' rotina regulatoria - 9.281 registros
    # no ano real - e afogaria o que importa.
    filtrado = filtrar_ipe(ipe, ["33000167000101"])
    assert len(filtrado) == 1
    assert filtrado["Assunto"].iloc[0] == "Payout 2025"
    print("[OK] Caso 4: filtra por CNPJ monitorado e por categoria relevante.")

    # Caso 5: sem CNPJ monitorado, devolve VAZIO - nao o arquivo inteiro.
    # Empresa cadastrada sem vinculo de CNPJ nao pode virar "coletar tudo".
    assert len(filtrar_ipe(ipe, [])) == 0
    assert len(filtrar_ipe(ipe, None)) == 0
    print("[OK] Caso 5: sem CNPJ vinculado, nao coleta nada (em vez de tudo).")

    print("\nTodos os casos passaram.")


if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser()
    ap.add_argument("--ano", type=int, default=date.today().year)
    ap.add_argument("--teste", action="store_true")
    args = ap.parse_args()

    if args.teste:
        _auto_teste()
        sys.exit(0)

    from investidas import (cnpjs_monitorados, criar_tabela_investidas,
                            gravar_companhias_cvm, gravar_comunicados)

    criar_tabela_investidas()

    print("Baixando cadastro de companhias abertas...")
    companhias = baixar_cadastro()
    gravar_companhias_cvm(companhias)
    print(f"{len(companhias)} companhia(s) ativa(s) no cadastro.")

    cnpjs = cnpjs_monitorados()
    if not cnpjs:
        print("Nenhuma empresa monitorada tem CNPJ vinculado - nada a coletar.")
        print("Vincule as empresas na pagina 'Empresas monitoradas'.")
        sys.exit(0)

    print(f"Baixando comunicados de {args.ano} para {len(cnpjs)} empresa(s)...")
    ipe = baixar_ipe(args.ano)
    relevantes = filtrar_ipe(ipe, cnpjs)
    print(f"{len(relevantes)} comunicado(s) das empresas monitoradas "
          f"(de {len(ipe)} no arquivo).")

    novos = gravar_comunicados(relevantes)
    print(f"{novos} novo(s) gravado(s).")
