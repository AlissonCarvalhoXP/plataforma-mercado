# teste_ia.py
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
print("Chave lida:", os.getenv("GEMINI_API_KEY"))
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

resposta = client.models.generate_content(
        model="gemini-flash-latest",
    contents="Explique em uma frase o que e a taxa Selic.",
)
print(resposta.text)