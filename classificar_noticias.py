# classificar_noticias.py — classifica as manchetes coletadas por categoria.
#
# Antes, um `except Exception: categoria = ""` engolia qualquer falha da API e
# o script imprimia "Classificacao concluida!" ao final, mesmo com 100% de
# falha. Foi assim que 181 de 191 noticias ficaram sem categoria sem ninguem
# perceber - a causa real era a API do Gemini respondendo 503.
#
# Agora as falhas sao contadas e reportadas, e o codigo de saida e' diferente
# de zero quando nada foi classificado. Como o atualizar.py passou a verificar
# retorno de cada passo, o problema aparece no resumo da coleta diaria em vez
# de sumir.
import sys

import pandas as pd

from analise_ia import classificar_noticia
from db import engine

noticias = pd.read_sql("SELECT * FROM noticias", engine)

if "categoria" not in noticias.columns:
    noticias["categoria"] = ""


def _sem_categoria(valor) -> bool:
    """Nulo, vazio ou a string 'nan' contam como nao classificada."""
    texto = str(valor or "").strip()
    return not texto or texto.lower() == "nan"


pendentes = [i for i, linha in noticias.iterrows() if _sem_categoria(linha["categoria"])]
print(f"{len(pendentes)} noticia(s) sem categoria de {len(noticias)}.")

classificadas = 0
falhas = 0
primeiro_erro = None

for i in pendentes:
    titulo = noticias.at[i, "titulo"]
    try:
        categoria = classificar_noticia(titulo)
    except Exception as exc:
        falhas += 1
        if primeiro_erro is None:
            primeiro_erro = f"{type(exc).__name__}: {str(exc)[:200]}"
        continue
    noticias.at[i, "categoria"] = categoria
    classificadas += 1
    print(f"[{categoria}] {titulo[:60]}")

if classificadas:
    noticias.to_sql("noticias", engine, if_exists="replace", index=False)

print(f"\n{classificadas} classificada(s), {falhas} falha(s).")
if primeiro_erro:
    print(f"Primeiro erro: {primeiro_erro}")

# Codigo de saida diferente de zero quando havia trabalho e NADA foi feito:
# e' o que faz a coleta diaria acusar o problema em vez de declarar sucesso.
if pendentes and classificadas == 0:
    print("FALHOU: nenhuma noticia pode ser classificada.")
    sys.exit(1)
