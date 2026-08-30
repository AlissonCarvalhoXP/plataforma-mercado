# ROADMAP / HANDOFF — Módulo de Opções B3 no Market Intelligence Hub (MIH)

**Autor:** Francisco Alisson Carvalho Alves — Tesouraria, Itaúsa
**Data:** 24 de agosto de 2026
**Destinatário:** próxima IA / desenvolvedor que der continuidade
**Máquina:** pessoal (não corporativa) — sem restrições de TI, internet livre

> ⚠️ Aviso permanente do produto: ferramenta de **apoio à decisão e estudo quantitativo. NÃO
> constitui recomendação de investimento.** Exibir disclaimer em toda UI e relatório.

---

## 0. TL;DR — onde o projeto está AGORA

O módulo de opções **já está construído, integrado ao MIH e rodando com dados REAIS da B3**
(via brapi.dev, sandbox PETR4). Não é mais protótipo HTML nem dados fictícios. O que falta é
**concluir o backtest** (coletar histórico de vencimentos vencidos → calibrar o peso do score)
e depois **polir/expandir**.

**Status geral:**
- ✅ Núcleo Python (Black-Scholes, IV, screener, recomendações) — pronto e testado
- ✅ Integração ao MIH (aditiva, sem quebrar nada) — no ar
- ✅ Coleta de cadeia real PETR4 (45 séries no `mercado.db`) — funcionando
- 🔄 Backtest — coletor histórico pronto; **falta rodar a coleta e calibrar** (passo pendente)
- ⬜ Polimento visual + expansão de ativos + alertas — planejado

---

## 1. Ambiente e stack (confirmados na máquina do Francisco)

- **Python 3.14** (atenção: versão nova — ver armadilhas na seção 6)
- **Projeto MIH:** `C:\Users\aliss\projetos\plataforma-mercado`
- **Ambiente virtual:** `.venv` (ativar antes de tudo: `.venv\Scripts\Activate.ps1`)
- **Banco único:** `data/mercado.db` (SQLite)
- **Dependências instaladas:** pandas, requests, streamlit, plotly, scipy, numpy, pydantic, python-dotenv
- **Fonte de dados:** brapi.dev — `.env` com `PROVIDER=brapi` e `BRAPI_TOKEN` (plano gratuito)
- **Rodar o Hub:** `python -m streamlit run app.py` (usar `python -m` por causa do PATH)

### Tabelas no mercado.db (estado atual)
Originais do MIH (preservadas): `briefing`, `debentures`, `debentures_series`, `destaques`,
`indicadores_bcb`, `noticias`, `selic`, `usd_brl`.
Novas do módulo de opções: `opcoes_series`, `opcoes_underlying`, `opcoes_historico`.

---

## 2. Arquivos do módulo de opções (em `modules/opcoes/`)

| Arquivo | Função | Estado |
|---|---|---|
| `db_opcoes.py` | Cria tabelas + persistência (aditivo ao mercado.db) | ✅ pronto |
| `coleta_opcoes.py` | Coleta cadeia atual (brapi → mercado.db) | ✅ pronto |
| `analises_opcoes.py` | Black-Scholes, IV, desconto, diff, score (usa `scipy.stats.norm`) | ✅ pronto |
| `view_opcoes.py` | Aba Streamlit "Opções B3" (KPIs, ranking, cadeia, estratégias) | ✅ no ar |
| `coleta_opcoes_historico.py` | Coleta histórico p/ backtest (v2 com vencimentos passados) | ✅ pronto |
| `backtest_opcoes.py` | Motor de backtest + calibração do peso | ✅ pronto |
| `__init__.py` (x2) | evitam erro de import | ✅ |

### Como a aba foi plugada no `app.py`
A home do MIH é uma tela única (sem abas ainda). O módulo entrou como **seção no final** do `app.py`:
```python
from modules.opcoes.view_opcoes import render_aba_opcoes  # no topo
# ... no fim do arquivo:
render_aba_opcoes(selic=ultimo_valor("Selic") / 100)  # Selic real como taxa livre de risco
```

---

## 3. Modelo quantitativo (o que o screener faz)

- **Preço justo** via Black-Scholes usando a **HV 60d como vol de referência** (não a IV).
  O "desconto" mede quanto o mercado paga acima/abaixo do que a vol realizada justificaria.
- **Desconto** = (justo − preço_mercado) / justo. Positivo = opção "barata".
- **Diff** = (IV − HV) × 100, em pontos percentuais.
- **Score** = desconto×100 − diff×**peso_diff** + log(liquidez)×peso_liq.
  - `peso_diff` default = **0,6** (arbitrário — é o que o backtest vai calibrar).
- **Sinal:** score > 0 → COMPRAR vol; score < 0 → VENDER vol.
- **Regime de vol** (estratégias): IV média × HV → ALTA (vender prêmio) / BAIXA (comprar vol) / NEUTRA.
- **Taxa livre de risco:** Selic real, lida da tabela `selic` do MIH.

---

## 4. PASSO PENDENTE (prioridade 1) — Concluir o Backtest

### Contexto
O backtest existe para **calibrar o `peso_diff`** (hoje 0,6, nunca validado). O motor
(`backtest_opcoes.py`) já está pronto e testado. **O bloqueio é DADOS**: as 45 séries já
coletadas são de **vencimentos futuros** (mal nasceram, ~1 dia de histórico cada). O backtest
precisa de séries com histórico longo → **séries de vencimentos JÁ VENCIDOS**.

### 4.1 Coletar histórico de vencimentos passados
O `coleta_opcoes_historico.py` (v2) já tem o modo certo. Rodar:
```powershell
python modules\opcoes\coleta_opcoes_historico.py --historico --vencimentos 2 --max-series 10 --pausa 6
```
- Descobre vencimentos vencidos da PETR4 (`/expirations?includeExpired=true`)
- Lista séries de cada um (`/chain`)
- Puxa histórico diário (`/analytics/history`: IV, gregas, preço, taxa) → `opcoes_historico`
- **Retoma automaticamente** se cair no limite (pula o que já coletou)

**Meta:** sair dos "7 pontos rasos" para **centenas de pontos reais**.

### 4.2 Rodar a calibração
```powershell
python modules\opcoes\backtest_opcoes.py
```
Saída: tabela com `peso_diff · n_sinais · win_rate · ret_medio · expectativa · ret_buy · ret_sell`
e o **melhor peso** ao final.

### 4.3 Aplicar o resultado
Substituir o `peso_diff` fixo (0,6) em `analises_opcoes.py` pelo melhor valor encontrado.

### ⚠️ Riscos conhecidos do backtest
- **Rate limit (429):** sandbox gratuito tem cota baixa (~1.000 req/mês). Coletar aos poucos,
  com `--max-series` e `--pausa` altos. O script tem retry/backoff e retomada.
- **Robustez estatística:** 1 série cobre só a vida dela. Quanto mais séries/vencimentos, melhor.
  Ideal acumular vários vencimentos ao longo do tempo.
- **Bug metodológico já corrigido:** o preço justo é recalculado via Black-Scholes real com HV
  (não pela razão HV/IV, que tornava desconto e diff colineares). Manter assim.

---

## 5. ROADMAP — próximos passos (em ordem sugerida)

### Prioridade 1 — Backtest (detalhado na seção 4)
- [ ] Coletar histórico de 2–3 vencimentos vencidos da PETR4
- [ ] Rodar calibração e definir o `peso_diff` ótimo
- [ ] Aplicar o peso calibrado em `analises_opcoes.py`

### Prioridade 2 — Automação da coleta
- [ ] Adicionar a coleta de opções ao `atualizar.py` / `atualizar.bat` do MIH
      (rodar `coleta_opcoes.py` diariamente para acumular histórico REAL ao longo do tempo)
- [ ] Agendar (Task Scheduler do Windows) para rodar após ~19h (dados EOD da brapi)

### Prioridade 3 — Fazer o `.env` ser lido de forma consistente
- [ ] Hoje a coleta às vezes cai em "token: sandbox" (só PETR4). Garantir `load_dotenv()`
      no ponto certo para usar o token e habilitar outros ativos.

### Prioridade 4 — Expandir universo de ativos
- [ ] Incluir **ITSA4** e investidas Itaúsa (Itaú, Alpargatas, Dexco) — faz sentido no contexto
- [ ] **Requer plano Pro da brapi** (opções ≠ PETR4 exigem Pro). Avaliar custo (~R$ 117/mês)

### Prioridade 5 — Polimento visual (Cenário B — tela única com abas)
- [ ] Converter a home empilhada do MIH em **abas** ("Visão Geral", "Câmbio", "Crédito",
      "Debêntures", "Opções B3") — decisão que já estava no `simulacao-hub-tesouraria`
- [ ] Alinhar o tema do gráfico plotly ao padrão visual do resto do Hub

### Prioridade 6 — Enriquecer análises
- [ ] **IV Rank / Percentile reais** (usar histórico acumulado em vez do regime aproximado)
- [ ] Superfície de IV (skew por strike × term structure por vencimento)
- [ ] Gráfico de payoff das estruturas sugeridas (long/travas/condor/straddle)
- [ ] GARCH "de verdade" via lib `arch` (hoje há EWMA/GARCH-lite próprio)

### Prioridade 7 — IA e Alertas (aproveitar o que o MIH já tem)
- [ ] Estender o **Briefing do dia (Gemini)** para citar regime de vol e principais assimetrias
- [ ] Conectar ao módulo de **Alertas**: disparar quando Diff cruzar limiar / surgir desconto forte
- [ ] Módulo de **Monitor de Investidas** (já planejado no MIH) cruzando com opções

### Prioridade 8 — Governança e rastreabilidade
- [ ] Manter aba/exportação com rastreabilidade (fonte, timestamp, pesos do score)
- [ ] Definir quem valida as "estratégias sugeridas" antes de qualquer uso pela mesa

---

## 6. Armadilhas conhecidas (para a próxima IA não tropeçar)

- **Python 3.14 + NumPy 2.x:** `np.trapz` foi REMOVIDO → usar `np.trapezoid`. (Já aplicado no
  projeto standalone; conferir se `risk.py`/qualquer uso no MIH está atualizado.)
- **Streamlit no PATH:** rodar sempre `python -m streamlit run app.py` (não só `streamlit`).
- **`.env` não é lido sozinho:** precisa `python-dotenv` + `load_dotenv()`. Sem isso, cai em sandbox.
- **Erro SSL "certificate is not yet valid":** era relógio do PC errado. Manter data/hora automáticas.
- **Cópia via Keep quebra indentação/aspas:** preferir baixar arquivos; se colar, no VS Code usar
  "Convert Indentation to Spaces". (Método base64 também funciona para transportar sem quebrar.)
- **brapi sandbox:** só PETR4/PETR* respondem sem token; dados são EOD (~19h); cota mensal baixa.
- **Integração é ADITIVA:** nunca dropar/alterar tabelas existentes do MIH. Backup do
  `mercado.db` antes de mexer (`copy data\mercado.db data\mercado_backup.db`).

---

## 7. Comandos de referência rápida

```powershell
# ativar ambiente
.venv\Scripts\Activate.ps1

# rodar o Hub (com a aba de opções)
python -m streamlit run app.py

# coletar cadeia atual (foto do dia)
python modules\opcoes\coleta_opcoes.py

# coletar histórico p/ backtest (vencimentos vencidos)
python modules\opcoes\coleta_opcoes_historico.py --historico --vencimentos 2 --max-series 10 --pausa 6

# rodar calibração do backtest
python modules\opcoes\backtest_opcoes.py

# conferir tabelas do banco
python -c "import sys; sys.path.insert(0,'modules/opcoes'); import db_opcoes; print(db_opcoes.list_existing_tables('data/mercado.db'))"
```

---

## 8. Decisões em aberto (precisam do Francisco)

- **Plano brapi:** ✅ decidido (2026-08-30) — fica no gratuito por agora (só
  PETR4); reavaliar Pro conforme necessidade. Ver
  `docs/superpowers/specs/2026-08-30-reposicionamento-e-hedge-carteira-design.md`.
- **Universo definitivo de ativos:** ✅ resolvido de outra forma — em vez de
  uma lista fixa, o universo agora é dinâmico (`ativos_da_carteira()` em
  `coleta_opcoes.py`): cobre o que estiver na carteira do usuário, mais
  `ATIVOS_PADRAO` como base. Ainda limitado pelo plano brapi gratuito (só
  PETR4 tem dados reais hoje).
- **Convenção de dias:** hoje corridos/365 aproximando 252; padronizar para dias úteis B3.
- **Quando polir vs. expandir:** priorizar visual (abas) ou dados (mais ativos/histórico)?
- **Governança:** fluxo de validação das sugestões antes de uso pela mesa.

---

*Fim do handoff. O projeto está funcional e integrado; o próximo marco é concluir o backtest
(seção 4) e depois seguir o roadmap (seção 5).*
