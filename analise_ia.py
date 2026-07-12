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
    prompt = f"""Voce e um analista escrevendo um briefing de mercado curto (3 a 4 frases) para uma mesa de Tesouraria.
Conecte os pontos (cambio, juros, credito e noticias) num texto coeso e objetivo, com linguagem de mercado.
Use SOMENTE os dados abaixo; nao invente numeros.

DADOS:
{contexto}
"""
    for tentativa in range(3):
        try:
            resposta = client.models.generate_content(model=MODELO, contents=prompt)
            return resposta.text.strip()
        except Exception as e:
            print(f"Tentativa {tentativa + 1} falhou (servidor ocupado). Esperando 5s...")
            time.sleep(5)
    return "Nao foi possivel gerar o briefing agora (servidor ocupado). Tente mais tarde."

if __name__ == "__main__":
    exemplo = "Ibovespa fecha em alta de quase 3%, apos IPCA; dolar recua para R$ 5,10"
    print(f"Manchete: {exemplo}")
    print(f"Categoria: {classificar_noticia(exemplo)}")    