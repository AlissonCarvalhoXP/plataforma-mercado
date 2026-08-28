"""
email_html.py - Gera e envia emails formatados em HTML com design profissional.

Usa template HTML com CSS inline para garantir compatibilidade com clientes de email.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import os
from dotenv import load_dotenv
import pandas as pd
from db import engine

load_dotenv()

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_SENHA = os.getenv("EMAIL_SENHA")

TEMPLATE_BRIEFING = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); 
                   color: white; padding: 30px; border-radius: 8px 8px 0 0; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 28px; }}
        .header p {{ margin: 5px 0 0 0; opacity: 0.9; }}
        .content {{ background: #f9f9f9; padding: 30px; border-left: 5px solid #2a5298; }}
        .section {{ margin-bottom: 25px; padding-bottom: 25px; border-bottom: 1px solid #ddd; }}
        .section:last-child {{ border-bottom: none; }}
        .section-title {{ color: #2a5298; font-size: 18px; font-weight: bold; margin-bottom: 10px; }}
        .metric {{ display: inline-block; background: white; padding: 15px 20px; 
                  margin: 5px 10px 5px 0; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        .metric-label {{ font-size: 12px; color: #666; text-transform: uppercase; }}
        .metric-value {{ font-size: 18px; font-weight: bold; color: #2a5298; }}
        .briefing-text {{ background: white; padding: 15px; border-radius: 5px; line-height: 1.8; }}
        .alerta {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; 
                 border-radius: 5px; margin: 15px 0; }}
        .alerta-titulo {{ color: #856404; font-weight: bold; font-size: 14px; }}
        .footer {{ background: #f0f0f0; padding: 20px; text-align: center; color: #666; font-size: 12px; }}
        .footer p {{ margin: 5px 0; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th {{ background: #2a5298; color: white; padding: 10px; text-align: left; font-size: 12px; }}
        td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
        tr:nth-child(even) {{ background: #f5f5f5; }}
        .positivo {{ color: #28a745; font-weight: bold; }}
        .negativo {{ color: #dc3545; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Briefing de Mercado</h1>
            <p>{data_hora}</p>
        </div>
        
        <div class="content">
            {metricas}
            
            <div class="section">
                <div class="section-title">🤖 Análise do Dia</div>
                <div class="briefing-text">{briefing}</div>
            </div>
            
            {destaques}
            
            {alertas}
            
            <div class="section">
                <div class="section-title">📈 Carteira</div>
                <p>{carteira}</p>
            </div>
        </div>
        
        <div class="footer">
            <p><strong>Market Intelligence Hub</strong></p>
            <p>Plataforma de suporte à decisão em Tesouraria e Global Markets</p>
            <p>Gerado automaticamente em {timestamp}</p>
        </div>
    </div>
</body>
</html>
"""


def formatar_dados_metricas():
    """Formata indicadores macro para exibição em HTML."""
    try:
        ind = pd.read_sql("SELECT * FROM indicadores_bcb", engine)
        dolar = pd.read_sql("SELECT close FROM usd_brl ORDER BY date DESC LIMIT 1", engine)
        
        def ultimo_valor(nome):
            return ind[ind["indicador"] == nome]["valor"].iloc[-1]
        
        selic = round(ultimo_valor("Selic"), 2)
        cdi = round(ultimo_valor("CDI"), 4)
        ipca = round(ultimo_valor("IPCA"), 2)
        igpm = round(ultimo_valor("IGP-M"), 2)
        dol = round(dolar["close"].iloc[-1], 2)
        
        metricas = f"""
        <div class="section">
            <div class="section-title">📍 Indicadores</div>
            <div>
                <div class="metric">
                    <div class="metric-label">Selic</div>
                    <div class="metric-value">{selic}%</div>
                </div>
                <div class="metric">
                    <div class="metric-label">CDI</div>
                    <div class="metric-value">{cdi}%</div>
                </div>
                <div class="metric">
                    <div class="metric-label">IPCA</div>
                    <div class="metric-value">{ipca}%</div>
                </div>
                <div class="metric">
                    <div class="metric-label">IGP-M</div>
                    <div class="metric-value">{igpm}%</div>
                </div>
                <div class="metric">
                    <div class="metric-label">USD/BRL</div>
                    <div class="metric-value">R$ {dol}</div>
                </div>
            </div>
        </div>
        """
        return metricas
    except Exception as e:
        print(f"[ERRO] Falha ao formatar métricas: {e}")
        return ""


def enviar_email_html(destinatario, assunto, briefing_texto, destaques_texto="", alertas_texto="", carteira_texto=""):
    """
    Envia email formatado em HTML com briefing e análises.
    
    Args:
        destinatario: email do destinatário
        assunto: assunto do email
        briefing_texto: conteúdo do briefing
        destaques_texto: destaques do dia (opcional)
        alertas_texto: alertas de mercado (opcional)
        carteira_texto: resumo da carteira (opcional)
    """
    if not EMAIL_USER or not EMAIL_SENHA:
        print("[AVISO] EMAIL_USER ou EMAIL_SENHA não configurados no .env")
        return False
    
    try:
        # Preparar seções do HTML
        metricas = formatar_dados_metricas()
        
        destaques_html = ""
        if destaques_texto:
            destaques_html = f"""
            <div class="section">
                <div class="section-title">⚡ Destaques</div>
                <div class="briefing-text">{destaques_texto}</div>
            </div>
            """
        
        alertas_html = ""
        if alertas_texto:
            alertas_html = f"""
            <div class="alerta">
                <div class="alerta-titulo">⚠️ ALERTAS DE MERCADO</div>
                <p>{alertas_texto}</p>
            </div>
            """
        
        carteira_html = carteira_texto or "Nenhuma carteira configurada."
        
        # Preencher template
        data_hora = datetime.now().strftime("%d/%m/%Y às %H:%M")
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        
        html_content = TEMPLATE_BRIEFING.format(
            data_hora=data_hora,
            metricas=metricas,
            briefing=briefing_texto,
            destaques=destaques_html,
            alertas=alertas_html,
            carteira=carteira_html,
            timestamp=timestamp
        )
        
        # Criar mensagem
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"] = EMAIL_USER
        msg["To"] = destinatario
        
        # Anexar HTML
        msg.attach(MIMEText(html_content, "html", "utf-8"))
        
        # Enviar
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_USER, EMAIL_SENHA)
            smtp.send_message(msg)
        
        print(f"[OK] Email enviado para {destinatario}")
        return True
    
    except Exception as e:
        print(f"[ERRO] Falha ao enviar email: {e}")
        return False


if __name__ == "__main__":
    # Teste: enviar briefing com dados reais
    try:
        briefing = pd.read_sql("SELECT texto FROM briefing", engine)["texto"].iloc[0]
    except:
        briefing = "Briefing não disponível. Rode briefing.py primeiro."
    
    try:
        destaques = pd.read_sql("SELECT texto FROM destaques", engine)["texto"].iloc[0]
    except:
        destaques = ""
    
    try:
        from carteira import gerar_contexto_carteira
        carteira = gerar_contexto_carteira()
    except:
        carteira = ""
    
    # Enviar para teste
    enviar_email_html(
        destinatario=EMAIL_USER or "teste@example.com",
        assunto="📊 Briefing de Mercado - Teste",
        briefing_texto=briefing,
        destaques_texto=destaques,
        carteira_texto=carteira
    )
