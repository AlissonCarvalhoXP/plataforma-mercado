# enviar_email.py
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()
EMAIL = os.getenv("EMAIL_USER")
SENHA = os.getenv("EMAIL_SENHA")


def enviar_email(assunto, corpo, para=None):
    para = para or EMAIL   # sem destinatario -> manda pra voce mesmo
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = EMAIL
    msg["To"] = para
    msg.set_content(corpo)
    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.starttls()
        smtp.login(EMAIL, SENHA)
        smtp.send_message(msg)


if __name__ == "__main__":
    enviar_email("Teste da plataforma", "Se voce recebeu isto, o e-mail funciona! 🚀")
    print("E-mail enviado!")