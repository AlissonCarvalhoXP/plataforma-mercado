# HANDOFF — Plataforma de Inteligência de Mercado (MIH)
> Documento de continuidade. Se você é uma IA assumindo este projeto, LEIA TUDO antes de agir.

## 0. COMO USAR ESTE DOCUMENTO (instruções à IA)
Você é um **mentor de programação e mercados financeiros**. Seu papel NÃO é entregar
soluções prontas — é ENSINAR o usuário a construir. Siga rigorosamente a metodologia
da seção 2. O usuário (Alisson) está aprendendo do zero; a didática importa tanto
quanto o código.

## 1. PERFIL DO USUÁRIO
- **Nome:** Alisson (Francisco Alisson Carvalho Alves).
- **Cargo:** Estagiário — Tesouraria, Itaúsa.
- **Objetivo duplo:** (a) APRENDER (Python, eng. de dados, APIs, banco, IA, mercado,
  macro, Global Markets); (b) construir um PROJETO DE PORTFÓLIO para entrevistas em
  Global Markets, Tesouraria, ALM e Mesa.
- **Ambiente:** Windows, VS Code, Python 3.14 (MUITO recente — atenção a
  incompatibilidades), terminal PowerShell.
- **GitHub:** usuário `AlissonCarvalhoXP`, repo `plataforma-mercado`.
- **Fluxo de trabalho:** lê o chat numa máquina e programa em OUTRA. Transfere código
  via **Google Keep** (texto puro). ⚠️ NUNCA sugerir copiar código via Google Sheets —
  ele corrompe indentação e aspas (causou vários bugs).

## 2. METODOLOGIA (obrigatória — foi o que funcionou)
1. **Incremental e "simplest first":** menor coisa que funciona de ponta a ponta,
   depois expande. Nunca despejar 200 linhas de uma vez.
2. **Explicar o CONCEITO antes do código.**
3. **Um passo por vez.** Esperar o usuário rodar e confirmar antes do próximo.
4. **Fatia vertical** (não construir camada inteira antes de ver algo rodar).
5. Para cada etapa, seguir: ① objetivo ② arquitetura ③ arquivos ④ explicar código
   ⑤ código ⑥ como testar ⑦ melhorias futuras.
6. **Ensinar a depurar** (ler traceback, isolar causa). Erros são aprendizado.
7. **Confirmar fontes/endpoints** (web) ANTES de passar código, pra evitar erro à toa.
8. Tom: mentor, encorajador, celebra marcos, honesto sobre trade-offs.
9. Registrar decisões e marcos (o usuário valoriza commits com boas mensagens).

## 3. STACK
Python · pandas · SQLAlchemy · yfinance · requests · feedparser · Streamlit ·
google-genai (Gemini) · python-dotenv · psycopg2-binary · SQLite (local) →
PostgreSQL/Neon (nuvem). Deploy: Streamlit Community Cloud. Versionamento: Git/GitHub.

## 4. ARQUITETURA (motor separado da vitrine — "plataforma viva")
Motor (coleta/IA) → Banco (memória) → Vitrine (app.py). O dashboard é dispensável;
o motor roda sozinho via agendador. Conexão centralizada em `db.py`.

## 5. INVENTÁRIO DE ARQUIVOS
- `db.py` — cria `engine`. Usa `DATABASE_URL` (.env) se existir; senão SQLite
  (`sqlite:///data/mercado.db`). TODOS os módulos fazem `from db import engine`.
- `coleta.py` — USD/BRL via yfinance ("BRL=X"), incremental → tabela `usd_brl`.
- `coleta_bcb.py` — Selic(432)/CDI(12)/IPCA(433)/IGP-M(189) via API BCB SGS,
  incremental (chave indicador+data) → tabela `indicadores_bcb`. Fn `buscar_serie_bcb`.
- `coleta_debentures.py` — baixa ZIP CVM (oferta_distribuicao.zip), lê CSV
  resolucao_160, filtra "DEB" → tabela `debentures` (replace; CSV traz histórico full).
- `enriquecer_debentures.py` — API SRE (.../requerimento/{n}), incremental por
  requerimento → tabela `debentures_series`. Extrai série, valor, datas, rating,
  remuneração; calcula Prazo_Anos, Indexador (regex), Spread.
- `adicionar_spread.py` — extrai Spread numérico do texto de remuneração (regex).
- `coleta_noticias.py` — RSS (InfoMoney + Money Times), incremental por link →
  tabela `noticias`.
- `classificar_noticias.py` — classifica notícias via IA → coluna `categoria`
  (Juros/Cambio/Inflacao/Fiscal/Credito/Bolsa/Mercados Globais/Outros). Incremental.
- `analise_ia.py` — cliente Gemini (MODELO="gemini-flash-latest"). Funções:
  `classificar_noticia`, `gerar_briefing`, `responder_pergunta`, `gerar_destaques`.
  Todas com retry/try-except (resiliência a 503).
- `analises.py` — análises por REGRAS: `analisar_dolar`, `analisar_selic`,
  `analisar_debentures`. NÃO pode ter efeito colateral (só funções + if __name__).
- `carteira.py` — Portfolio Intelligence V1. Tabela `carteira` (ativo, direcao,
  indexador, tamanho). Funções: `ler_carteira`, `salvar_carteira`, `gerar_contexto_carteira`.
  Contexto injetado em briefing.py e app.py para personalizar análises.
- `investidas.py` — Monitora fatos relevantes de empresas (Itaúsa e similares).
  Tabela `investidas` (cnpj, nome_empresa, fato_relevante, data_fato).
  Funcoes: `filtrar_noticias_por_empresa`, `gerar_alerta_investidas`. Integrado no
  app.py (aba Investidas) e alertas.py (alerta por e-mail).
- `briefing.py` — monta contexto (análises + notícias + CARTEIRA), gera briefing E
  destaques → tabelas `briefing` e `destaques`. Só salva se a IA respondeu.
- `enviar_email.py` — SMTP Gmail (EMAIL_USER/EMAIL_SENHA do .env; senha de app).
- `enviar_briefing.py` — manda briefing+destaques por e-mail.
- `alertas.py` — alerta condicional do dólar (TETO/PISO) por e-mail.
- `atualizar.py` — ORQUESTRADOR: roda coleta→bcb→debentures→enriquecer→noticias→
  classificar→briefing→enviar_briefing→alertas, em sequência (subprocess).
- `atualizar.bat` — wrapper p/ Agendador de Tarefas do Windows (roda diário).
- `consultar.py` — leitura simples de teste.
- `app.py` — dashboard Streamlit (briefing, destaques, indicadores, dólar,
  debêntures c/ merge emissor, notícias filtradas, CARTEIRA editável, "Pergunte à plataforma").
- `migrar_para_postgres.py` — copia todas as tabelas SQLite → Postgres, normalizando colunas.
- `padronizar_colunas.py` — padroniza nomes de colunas (minúsculas) em banco existente.
- `.env.example` — template com variáveis de ambiente necessárias.
- `DEPLOY.md` — guia passo-a-passo para deploy em Streamlit Cloud + Postgres/Neon.
- `.github/workflows/daily-update.yml` — GitHub Actions para rodar pipeline diário.
- `.gitignore` (ignora venv/, .env, data/*.db), `README.md`, `ROADMAP.md`, `HANDOFF.md`.

## 6. TABELAS DO BANCO
usd_brl · indicadores_bcb · debentures · debentures_series · noticias · briefing ·
destaques · carteira · (Portfolio Intelligence)

## 7. FONTES DE DADOS (todas grátis, sem premium)
- BCB SGS: `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{cod}/dados/ultimos/{n}?formato=json`
- CVM lista: `https://dados.cvm.gov.br/dados/OFERTA/DISTRIB/DADOS/oferta_distribuicao.zip`
- CVM detalhe: `https://web.cvm.gov.br/sre-publico-cvm/rest/sitePublico/pesquisar/requerimento/{n}`
  (requer header Accept: application/json)
- Yahoo Finance via yfinance (ticker "BRL=X").
- RSS: infomoney.com.br/feed/ e moneytimes.com.br/feed/
- IA: Google Gemini (google-genai), modelo "gemini-flash-latest". Chave grátis (AI Studio).

## 8. ⚠️ BUG ABERTO (PRÓXIMA TAREFA — PRIORIDADE MÁXIMA)
Ao migrar para PostgreSQL, as colunas foram criadas com MAIÚSCULAS (Date, Close,
Numero_Requerimento...) porque o pandas.to_sql preservou os nomes originais.
Postgres dobra identificadores SEM aspas para minúsculo → queries como
`SELECT Date FROM usd_brl` falham com "column 'date' does not exist".
Afeta: coleta.py, alertas.py, enriquecer_debentures.py, app.py, analises.py, etc.
(rodou parcial: BCB, CVM, notícias, briefing e e-mail funcionaram; dólar,
enriquecimento e alertas falharam).
FIX RECOMENDADO (didático, alinhado à metodologia): PADRONIZAR nomes de coluna em
MINÚSCULO — renomear as colunas nos DataFrames antes de salvar (ex.: usd_brl com
date/close/high/low/open/volume) E ajustar todas as queries para minúsculo.
Depois, re-rodar migrar_para_postgres.py para recriar as tabelas.
Fazer INCREMENTAL (uma tabela/arquivo por vez, testar, seguir).
STATUS NUVEM: psycopg2-binary já foi adicionado ao requirements.txt e commitado
(commit db0c992). Verificar se o build do Streamlit Cloud passou. Se falhar por
Python 3.14, fixar Python 3.12 nas config do app.

## 9. GOTCHAS / LIÇÕES JÁ APRENDIDAS (não repetir)
- Relógio do PC atrasado → erro SSL "certificate not yet valid". (Já resolvido.)
- Google Sheets corrompe código copiado → usar Google Keep (texto puro).
- `.env`: formato NOME=valor, SEM espaço no "=", SEM aspas. Streamlit Secrets (TOML):
  NOME = "valor" COM aspas. São formatos diferentes!
- Importação circular + efeito colateral: subprocess NUNCA em módulo importado
  (só no atualizar.py). analises.py deve ser só funções.
- `except Exception` genérico mascarou um bug (engine usado antes de existir) — cuidado.
- Streamlit: rodar com `streamlit run app.py` (não `python`); terminal fica ocupado
  (não travou); mudança no banco não dispara Rerun (usar F5).
- Gemini: nomes de modelo mudam; usar alias "gemini-flash-latest". 503 = servidor
  ocupado (temporário) → retry.
- Deploy snapshot: `git add -f data/mercado.db` (está no .gitignore).

## 10. DECISÕES DE PRODUTO/ARQUITETURA (respeitar)
- **Modelagem:** guardar dado ATÔMICO (Indexador e Spread em colunas separadas);
  montar "CDI + X%" só na EXIBIÇÃO (fase de Relatórios). Mesma regra de datas:
  guardar ISO, exibir BR.
- **Caminho B antes de A:** priorizar IA analítica/proativa (feito) antes de
  IA-agente que consulta o banco sozinha (caminho A) — este só quando os dados
  crescerem e não couberem no contexto.
- **Compliance (CVM):** IA deve dar OBSERVAÇÕES/contexto, não CONSELHO de
  investimento (evitar "compre/adote/aproveite"). Já ajustado no prompt de destaques.
- **Foco:** ir FUNDO em UMA persona (Tesouraria/Global Markets BR) + camada de
  carteira, em vez de espalhar em várias personas. Constraint real = custo do dado
  premium (tempo real/global exige Bloomberg). Fontes atuais servem bem ao escopo BR/diário.

## 11. ROADMAP
### CONCLUÍDO ✅
- Fase 0 Fundação (ambiente, Git).
- Fase 1 MVP (dólar → SQLite → Streamlit).
- Fase 2 Indicadores macro BCB (Selic/CDI/IPCA/IGP-M).
- Fase 2.5 Monitor de debêntures (CVM: coleta + enriquecimento + spread + dashboard).
- Fase 3 Coleta incremental + orquestração (atualizar.py) + agendamento (.bat).
- Fase 4 Análises automáticas por regras (analisar_dolar/selic/debentures).
- Fase 5 Notícias (RSS) + classificação IA + briefing + destaques + assistente Q&A.
- Fase 6: Alertas por e-mail ✅ ; Deploy Streamlit Cloud (snapshot + DEPLOY.md) ✅ ;
  PostgreSQL/Neon: migração com normalização de colunas ✅ ; Workflow GitHub Actions ✅.
- **Fase 7 [NOVO]:** Portfolio Intelligence V1 ✅ ; Módulo Investidas (Itaúsa) ✅.

### PENDENTE ⬜ (ordem sugerida)
1. **Refinos de prompt** — briefing menos repetitivo (variar abertura); enxugar/
   afinar destaques (contínuo).
2. **Coleta de Fatos Relevantes (CVM IPE)** — integrar download automático de fatos
   relevantes de Itaúsa e empresas similares; alertar automaticamente.
3. **(Futuro) IA-agente (caminho A)** — function calling: IA gera consultas ao banco
   sozinha. Só quando o volume de dados justificar.

### FASE 8 — RELATÓRIOS & PERFUMARIA ✅ (2025-01-17)
- relatorios.py: 3 geradores de Excel (debentures, indicadores, dolar) com formatação BR
  * Dates: dd/mm/aaaa | Valores: R$ com 2 casas | Taxas: X.XX%
  * Spreads: "CDI + X.XX%" conforme decisão de modelagem (montado na exibição, não no armazenamento)
- email_html.py: templates HTML com inline CSS para briefing profissional
  * Sections: Métrica (Selic/IPCA/IGP-M/Dólar), Briefing, Alertas, Carteira, Call-to-Action
  * Suporta envio automático (requer EMAIL_USER/EMAIL_SENHA em .env)
- app.py: melhorias UI/UX
  * Seção "📥 Download de Relatórios": botões para gerar/baixar Excel (individual ou em lote)
  * Seção "📧 Enviar Briefing por Email": input de email + botão de envio
  * Theme customizado com CSS: gradientes, cores, metriccard styling
  * Formatação de dados: datas em dd/mm/aaaa + moeda em R$ em TODOS dataframes exibidos
  * st.set_page_config: wide layout, sidebar expanded, page title/icon
- teste_integracao.py: script de validação end-to-end dos novos módulos
  * Imports, DB connection, geração de relatórios, carteira, investidas, formatação HTML
  
Status: ✅ Código completo | 🧪 Testes básicos passaram | ⚙️ Pronto para produção
Próximos passos: streamlit run app.py + validar UI; configure .env para teste de SMTP

### VISÃO DE LONGO PRAZO (norte, não construir agora)
"Motor de contextualização" que responde: *"dado quem eu sou, o que importa pra mim
hoje?"*. Personas adicionais (Hedge Fund macro, ALM, Research) só como visão futura.

## 12. PRÓXIMO PASSO IMEDIATO
1. Executar `streamlit run app.py` e validar os novos botões de relatórios e email
2. Testar download dos .xlsx files com dados e formatação corretos
3. Configurar .env com EMAIL_USER/EMAIL_SENHA para testar envio de SMTP
4. Executar `python atualizar.py` para validar pipeline completo end-to-end
5. Fazer refinement dos prompts do briefing (menos repetitivo, mais insights)
6. Depois: Coleta de Fatos Relevantes (CVM IPE) ou IA-agente (caminho A)