# 🚀 DEPLOY — Plataforma de Inteligência de Mercado

## 1. PRÉ-REQUISITOS

✅ Código já está em: https://github.com/AlissonCarvalhoXP/plataforma-mercado
✅ Banco local (SQLite) atualizado e com colunas normalizadas
✅ requirements.txt com todas as dependências
✅ `.env.example` preparado

## 2. CONFIGURAR POSTGRES NA NUVEM (Neon)

### 2.1 Criar conta Neon
1. Acesse https://neon.tech
2. Sign up com GitHub (facilita integração)
3. Crie novo projeto
4. Copie a connection string (Connection String > Nodejs format)
   ```
   postgresql://user:password@ep-xxxxx.us-east-1.aws.neon.tech/neondb?sslmode=require
   ```

### 2.2 Migrar dados para Postgres
```bash
# No seu PC, com DATABASE_URL no .env apontando para Neon:
export DATABASE_URL="postgresql://user:password@ep-xxxxx.us-east-1.aws.neon.tech/neondb?sslmode=require"

# Rodar migração
python migrar_para_postgres.py
```

**Importante:** `migrar_para_postgres.py` normaliza as colunas durante a migração.

## 3. DEPLOY NO STREAMLIT CLOUD

### 3.1 Preparar repositório
```bash
# Garantir que .env NÃO está versionado
cat .gitignore  # deve conter .env

# Commitar .env.example
git add .env.example
git commit -m "docs: adicionar .env.example com instrucoes"
git push
```

### 3.2 Criar app no Streamlit Cloud
1. Acesse https://share.streamlit.io
2. Clique "New app"
3. Conecte GitHub: AlissonCarvalhoXP/plataforma-mercado
4. Branch: `main` (ou `agents/roadmap-execution-options-handoff`)
5. Main file path: `app.py`
6. Deploy

### 3.3 Configurar Secrets (credenciais)
1. Na página da app, clique **Settings** → **Secrets**
2. Adicione as variáveis (formato TOML):
   ```toml
   DATABASE_URL = "postgresql://user:password@ep-xxxxx.us-east-1.aws.neon.tech/neondb?sslmode=require"
   GEMINI_API_KEY = "sua_chave_gemini"
   EMAIL_USER = "seu_email@gmail.com"
   EMAIL_SENHA = "sua_senha_de_app"
   ```
3. Clique Save → app reinicia automaticamente

## 4. VALIDAR DEPLOY

### 4.1 Acessar a app
- URL: https://share.streamlit.io/[seu_usuario]/plataforma-mercado/app.py
- Validar que os indicadores carregam (Selic, CDI, IPCA, IGP-M)
- Validar que o dólar está visível
- Validar que as debentures aparecem

### 4.2 Teste dados ao vivo
```bash
# Rodar atualizar.py localmente
python atualizar.py

# Esperar 30 segundos (Streamlit polling)
# Recarregar a app (F5) — dados novos devem aparecer
# NÃO precisa fazer novo commit/push
```

## 5. AGENDAMENTO (PRODUÇÃO)

### 5.1 Opção A: GitHub Actions (recomendado)
Crie `.github/workflows/daily-update.yml`:
```yaml
name: Daily Market Update
on:
  schedule:
    - cron: '0 7 * * 1-5'  # 7 da manhã, seg-sex (horário UTC)

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: python atualizar.py
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          EMAIL_USER: ${{ secrets.EMAIL_USER }}
          EMAIL_SENHA: ${{ secrets.EMAIL_SENHA }}
```

### 5.2 Opção B: Cron local (Windows Task Scheduler)
- Mantém `atualizar.bat` como está
- Agenda Tarefas do Windows roda diário às 7 da manhã
- Executa localmente e grava no Postgres na nuvem

## 6. TROUBLESHOOTING

### Erro: "column 'date' does not exist"
→ Colunas não foram normalizadas. Rodar `padronizar_colunas.py`

### Erro: "FATAL: password authentication failed"
→ DATABASE_URL incorreta. Verificar credenciais Neon

### App carrega lento
→ Streamlit Cloud tem tier gratuito com limitações. Considerar upgrade ou cache.

### Dados não atualizam após atualizar.py local
→ Normal em Streamlit Cloud. Cache é revalidado a cada 1-5 minutos. Usar F5 para forçar refresh.

## 7. PRÓXIMOS PASSOS

1. **Portfolio Intelligence (V1):** Adicionar `st.data_editor` para carteira do usuário
2. **Módulo Investidas:** Monitorar CNPJ de empresas (Itaúsa) via CVM IPE
3. **Relatórios:** Export .xlsx com formatação BR

## REFERÊNCIAS

- Neon Docs: https://neon.tech/docs
- Streamlit Secrets: https://docs.streamlit.io/deploy/streamlit-cloud/secrets-management
- GitHub Actions: https://github.com/features/actions
