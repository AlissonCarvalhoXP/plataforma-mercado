# 🗺️ Roadmap — Plataforma de Inteligência de Mercado

Plataforma que consolida indicadores macroeconômicos, dados de mercado e notícias,
transformando-os em **contexto e insights acionáveis** para apoio à decisão em
**Global Markets** e **Tesouraria**.

> **Visão de longo prazo:** evoluir de um dashboard para uma plataforma de apoio à
> decisão que transforma dados de mercado, eventos macro e notícias em leitura acionável.

**Stack:** Python · pandas · SQLAlchemy · yfinance · requests · Streamlit · SQLite (→ PostgreSQL) · Git/GitHub

**Legenda:** ✅ concluído · 🔜 próximo · 💡 planejado

---

## ✅ Fase 0 — Fundação
- [x] Ambiente de desenvolvimento (Python, VS Code, Git)
- [x] Estrutura do projeto + ambiente virtual (venv)
- [x] `requirements.txt`, `.gitignore`, `README.md`
- [x] Versionamento com Git

## ✅ Fase 1 — MVP (fatia vertical: coletar → armazenar → visualizar)
- [x] Coleta do dólar (USD/BRL) via yfinance — `coleta.py`
- [x] Armazenamento em SQLite (tabela `usd_brl`)
- [x] Leitura do banco — `consultar.py`
- [x] Dashboard interativo com Streamlit — `app.py`

## ✅ Fase 2 — Indicadores macro (Banco Central)
- [x] Integração com a API REST do BCB (SGS)
- [x] Função reutilizável `buscar_serie_bcb()` + laço `for`
- [x] Selic, CDI, IPCA e IGP-M (tabela `indicadores_bcb`)
- [x] Cartões dos indicadores no dashboard
- [x] Projeto publicado no GitHub

## 🔜 Fase 3 — Histórico vivo
- [ ] Coleta incremental (acumular sem duplicar)
- [ ] Script único de atualização (dólar + BCB)
- [ ] Agendamento diário automático

## 💡 Fase 2.5 — Crédito & Debêntures (CVM)
- [ ] Coleta de emissões via CVM Dados Abertos
- [ ] Limpeza e armazenamento
- [ ] Filtro de debêntures indexadas a CDI+ no dashboard
- [ ] Alerta de novas emissões

## 💡 Fase 4 — Análises automáticas
- [ ] Detecção de eventos relevantes (variações, mudanças de taxa)
- [ ] Geração de interpretações por regras

## 💡 Fase 5 — Notícias + IA
- [ ] Coleta de notícias (RSS)
- [ ] Classificação por tema (juros, câmbio, fiscal…)
- [ ] Resumo com IA (LLM)
- [ ] Briefing diário com fontes citadas

## 💡 Fase 6 — Alertas & Produção
- [ ] Regras de alerta (câmbio, emissões, indicadores)
- [ ] Notificações (e-mail / Telegram)
- [ ] Migração para PostgreSQL
- [ ] Deploy do dashboard (Streamlit Community Cloud)

## 🎨 Transversal — Design & UX
- [ ] Tema visual e layout
- [ ] Formatação BR de números e datas
- [ ] Organização em abas/seções

---

## 🌟 Estrela-guia
**Briefing matinal automático de câmbio + juros (BR):** dólar, curva DI, Selic,
2–3 manchetes e uma leitura de IA com fontes citadas.

