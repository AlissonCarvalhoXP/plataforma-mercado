# Plataforma de Inteligência de Mercado

Consolida indicadores macroeconômicos, dados de mercado e análises
automatizadas para apoio à decisão em Global Markets e Tesouraria.

## 🎯 Objetivo

Transformar dados dispersos em **contexto acionável** diário:
- Indicadores macro (Selic, CDI, IPCA, IGP-M via BCB)
- Câmbio (USD/BRL via yfinance)
- Debêntures (novas emissões via CVM)
- Notícias classificadas por tema (IA)
- Briefing automático com insights

## ✅ Status

**Fase 6 (pronto para produção):** Dados, IA e alertas funcionam.

- ✅ Coleta incremental (dólar, BCB, CVM, RSS)
- ✅ Análises automáticas por regras
- ✅ IA: classificação de notícias + briefing + Q&A
- ✅ Alertas por e-mail
- ✅ Dashboard Streamlit
- 🚀 Deploy: Streamlit Cloud + Postgres/Neon (veja [DEPLOY.md](DEPLOY.md))

## 📚 Stack

Python · Pandas · SQLAlchemy · yfinance · Streamlit · SQLite/PostgreSQL · Google Gemini