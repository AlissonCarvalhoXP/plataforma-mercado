# analise_ia.py
import time
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODELO = "gemini-flash-latest"


def classificar_noticia(titulo):
    prompt = f"""Classifique a manchete em UMA destas categorias:
Juros, Cambio, Inflacao, Fiscal, Credito, Bolsa, Mercados Globais, Outros.
Responda APENAS com a categoria, sem explicacao.

Manchete: {titulo}"""
    resposta = client.models.generate_content(model=MODELO, contents=prompt)
    return resposta.text.strip()


def gerar_briefing(contexto):
    prompt = f"""Voce e um analista escrevendo o briefing de mercado do dia (3 a 4 frases) para uma mesa de Tesouraria.
Abra pelo que for MAIS RELEVANTE ou que MAIS MUDOU hoje (o maior movimento do dia, uma novidade nas noticias, um destaque no credito) — NAO comece sempre pelo mesmo ponto (nem sempre pela Selic). Varie a abertura conforme os dados do dia.
Conecte os pontos (cambio, juros, credito, noticias) num texto coeso, com linguagem de mercado. Use SOMENTE os dados abaixo; nao invente numeros.

DADOS:
{contexto}
"""
    for tentativa in range(4):
        try:
            resposta = client.models.generate_content(model=MODELO, contents=prompt)
            return resposta.text.strip()
        except Exception:
            print(f"Tentativa {tentativa + 1} falhou (servidor ocupado). Esperando 10s...")
            time.sleep(10)
    return None


def responder_pergunta(pergunta, contexto):
    prompt = f"""Voce e um analista de mercado experiente (Global Markets / Tesouraria) respondendo a um colega de mesa.
Use o CONTEXTO abaixo como base factual — nao invente numeros fora dele.
Mas RACIOCINE como analista: conecte os pontos (cambio, juros, credito, noticias), explique o "porque" e entregue uma leitura util.
Se faltar um dado especifico, diga o que falta (em vez de so recusar).
Responda em 2 a 4 frases, com linguagem de mercado.

CONTEXTO:
{contexto}

PERGUNTA: {pergunta}
"""
    try:
        resposta = client.models.generate_content(model=MODELO, contents=prompt)
        return resposta.text.strip()
    except Exception:
        return "Nao consegui responder agora (servidor ocupado). Tente de novo."


def gerar_destaques(contexto):
    prompt = f"""Voce e um analista de mercado. Com base no CONTEXTO abaixo, escreva os 3 pontos de atencao mais relevantes de hoje para uma mesa de Tesouraria.
Descreva OBSERVACOES e o contexto (o que esta acontecendo e por que importa) — NAO de conselhos de investimento (evite "compre", "adote", "aproveite", "concentre").
Responda SO com os 3 bullets (comece cada um com "- "), curtos e objetivos, SEM frase de introducao. Nao invente numeros fora do contexto.

CONTEXTO:
{contexto}
"""
    for tentativa in range(3):
        try:
            resposta = client.models.generate_content(model=MODELO, contents=prompt)
            return resposta.text.strip()
        except Exception:
            print(f"Destaques - tentativa {tentativa + 1} falhou. Esperando 5s...")
            time.sleep(5)
    return None