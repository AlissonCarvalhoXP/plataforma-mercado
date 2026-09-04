# coleta_noticias.py — coleta manchetes dos feeds e grava so' as novas.
#
# FILTRAGEM NA ORIGEM. Antes, os dois veiculos eram lidos pelo feed GERAL do
# portal, que traz politica, esporte e internacional junto com mercado -
# medido: das 191 primeiras noticias, praticamente nenhuma citava Copom ou
# Selic no titulo, e o topo era Bolsonaro, Trump e futebol.
#
# Duas estrategias, conforme o que cada veiculo oferece:
#
# - Money Times publica feeds por EDITORIA (/mercados/, /economia/), e eles
#   funcionam. Consumir a editoria e' filtragem feita pelo proprio veiculo,
#   sem heuristica nossa - de longe a melhor opcao.
# - InfoMoney NAO expoe feed por secao (testados /mercados/feed/,
#   /categoria/.../feed/, /category/.../feed/, ?cat= - todos devolvem o feed
#   geral). So' para ele aplicamos uma lista de descarte.
#
# A lista e' de DESCARTE, nao de permissao: descartar o obviamente irrelevante
# erra pouco, enquanto exigir palavra-chave de mercado jogaria fora noticia boa
# com manchete criativa. E o script REPORTA quantas descartou, para a regra ser
# auditavel - se comecar a cortar demais, aparece.
import unicodedata

import feedparser
import pandas as pd

# nome -> (url, aplica_descarte)
FEEDS = {
    "InfoMoney": ("https://www.infomoney.com.br/feed/", True),
    "Money Times · Mercados": ("https://www.moneytimes.com.br/mercados/feed/", False),
    "Money Times · Economia": ("https://www.moneytimes.com.br/economia/feed/", False),
}

# Termos que praticamente nunca aparecem em manchete de mercado legitima.
# Deliberadamente curta e conservadora: cada termo aqui e' uma chance de
# descartar algo bom.
#
# Tres termos foram REMOVIDOS depois que o auto-teste os pegou:
# - "campeonato" descartava "Campeonato de vendas impulsiona varejo"
# - "receita de" descartaria "receita de vendas cresce"
# - "jogador" descartaria "grande jogador do setor"
# E "quina" (de mega-sena) e' o caso mais instrutivo: por casamento de
# substring ele descartava "MAQUINA de cartao", porque "maquina" contem
# "quina". Por isso a comparacao passou a ser por PALAVRA INTEIRA, o que
# elimina essa classe inteira de erro, e nao so' este caso.
TERMOS_DESCARTE = (
    "futebol", "flamengo", "corinthians", "palmeiras", "neymar", "copa do mundo",
    "libertadores", "brasileirao", "bbb", "big brother", "novela", "celebridade",
    "cantor", "cantora", "influenciadora", "influenciador", "morre aos",
    "acidente de transito", "horoscopo", "signo", "mega-sena",
)


def _normalizar(texto: str) -> str:
    """Minusculas e sem acento, para a comparacao nao depender de grafia."""
    sem_acento = unicodedata.normalize("NFKD", str(texto or ""))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.lower()


def deve_descartar(titulo: str, termos=TERMOS_DESCARTE) -> bool:
    """True quando a manchete e' claramente de outra editoria.

    Casa por PALAVRA INTEIRA, nao por substring: com substring, "quina" (de
    mega-sena) descartava "maquina de cartao". Termos com espaco continuam
    funcionando, porque a fronteira de palavra vale nas pontas da expressao.

    Funcao pura e testavel: e' a unica heuristica desta coleta, entao merece
    ficar isolada e coberta por teste em vez de embutida no laco."""
    import re
    normalizado = _normalizar(titulo)
    return any(re.search(r"\b" + re.escape(_normalizar(t)) + r"\b", normalizado)
               for t in termos)


def coletar() -> tuple[pd.DataFrame, int]:
    """Le todos os feeds. Devolve (noticias, quantas foram descartadas)."""
    noticias = []
    descartadas = 0
    for fonte, (url, aplica_descarte) in FEEDS.items():
        feed = feedparser.parse(url)
        for item in feed.entries:
            titulo = item.get("title", "")
            if aplica_descarte and deve_descartar(titulo):
                descartadas += 1
                continue
            noticias.append({
                "titulo": titulo,
                "link": item.get("link", ""),
                "data": item.get("published", ""),
                "fonte": fonte,
            })
    return pd.DataFrame(noticias), descartadas


if __name__ == "__main__":
    import sys

    if "--teste" in sys.argv:
        # Caso 1: descarta o que e' claramente de outra editoria
        assert deve_descartar("Neymar marca golaco no classico")
        assert deve_descartar("Participante do BBB deixa a casa")
        assert deve_descartar("Cantora sertaneja morre aos 42 anos")
        print("[OK] Caso 1: manchete de outra editoria e' descartada.")

        # Caso 2: NAO descarta noticia de mercado - inclusive quando cita
        # palavra que aparece na lista dentro de outro contexto
        assert not deve_descartar("Copom eleva Selic para 15% ao ano")
        assert not deve_descartar("Petrobras anuncia dividendo extraordinario")
        assert not deve_descartar("Campeonato de vendas impulsiona varejo")
        print("[OK] Caso 2: manchete de mercado nao e' descartada.")

        # Caso 2b: casamento por PALAVRA INTEIRA. Com substring, "quina" (de
        # mega-sena) descartava "maquina" - erro que o teste do Caso 2 pegou e
        # que motivou a mudanca. Trava a classe inteira contra regressao.
        assert not deve_descartar("Maquina de cartao tem alta de 12%")
        assert not deve_descartar("Signos de recuperacao na industria")  # 'signo' dentro
        assert deve_descartar("Mega-Sena acumula em R$ 50 milhoes")
        print("[OK] Caso 2b: casa palavra inteira - 'quina' nao pega 'maquina'.")

        # Caso 3: comparacao ignora acento e caixa
        assert deve_descartar("FUTEBOL: veja os jogos de hoje")
        assert deve_descartar("Horoscopo do dia")
        assert deve_descartar("Horóscopo do dia")
        print("[OK] Caso 3: descarte ignora acento e caixa.")

        print("\nTodos os casos passaram.")
        sys.exit(0)

    from db import engine

    df, descartadas = coletar()
    print(f"{len(df)} noticia(s) nos feeds, {descartadas} descartada(s) por editoria.")

    try:
        existentes = pd.read_sql("SELECT link FROM noticias", engine)
        ja_temos = set(existentes["link"])
    except Exception:
        ja_temos = set()

    novas = df[~df["link"].isin(ja_temos)] if not df.empty else df
    if not novas.empty:
        novas.to_sql("noticias", engine, if_exists="append", index=False)
    print(f"{len(novas)} noticia(s) nova(s) adicionada(s).")
