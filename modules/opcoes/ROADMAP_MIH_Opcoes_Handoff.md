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

### ✅ 4.4 RESOLVIDO (2026-08-30) — Score colinear, calibração não convergia

Rodei o backtest de verdade (63 séries, 51 sinais após filtrar residuais — ver 4.5) e o
sweep de `peso_diff` (0,0 a 1,2) deu **resultado idêntico para todo peso testado**. Não
era falta de dado: **`desconto` e `diff` não são sinais independentes**. Por construção
de Black-Scholes (monotônico em volatilidade), sempre que `IV < HV` (`diff` negativo), o
preço justo calculado com `HV` fica maior que o preço de mercado (que reflete `IV`) quase
por definição — ou seja, `desconto` positivo. Confirmado nos dados reais: correlação
quase perfeita entre os dois sinais (ex.: diff -34,6pp ↔ desconto +72,9%). A entrada
anterior desta seção ("bug metodológico já corrigido... manter assim") estava errada — a
correção documentada só mudou a FORMA da colinearidade, não a removeu.

**Correção aplicada:** `desconto` sai do Score (vira campo só informativo). O Score
passa a somar dois eixos genuinamente ortogonais: `Diff_pp` (IV vs. HV, já existia) e o
novo `Skew_pp` (IV desta opção vs. o sorriso de vol do dia, ajustado a partir de outras
séries do mesmo vencimento/Tipo — `ajustar_sorriso()`, exige ≥4 strikes distintos).
Função `calcular_score()` compartilhada entre `analises_opcoes.py` e
`backtest_opcoes.py` (antes o backtest tinha uma reimplementação própria da fórmula, o
que já tinha permitido a divergência silenciosa registrada acima). Backtest agora varre
uma grade 2D (`peso_diff` × `peso_skew`). Validado: o sweep passou a variar de verdade
(win rate de 47,1% a 94,1% conforme a combinação, antes idêntico em todas). Detalhes
completos: `docs/superpowers/specs/2026-08-30-score-opcoes-sem-desconto-design.md`.

### ✅ 4.4b RESOLVIDO (2026-08-30) — Viés de theta-decay no backtest

Ao validar a correção 4.4, a combinação "vencedora" do sweep (`peso_diff=0,
peso_skew=0`) era um artefato: com os dois pesos zerados o Score ficava exatamente 0,0
pra toda linha, `score > 0` nunca era verdadeiro, e **todo sinal caía em "VENDER_VOL"
por padrão** — os "94,1% de acerto" capturavam o decaimento médio de theta (opção perde
valor com o tempo, "sempre vender" tende a acertar), não informação real do Diff/Skew.
Viés clássico de backtest de opções.

**Correção aplicada em `backtest_opcoes.py`:** (1) `score_minimo` (default `1e-6`)
exclui pontos com `|score|` praticamente zero da contagem de sinais — não caem mais em
"vender" por padrão, simplesmente não contam como sinal; (2) toda `Resultado` agora
reporta `expectativa_base_vender` (o que "sempre vender" teria dado nos MESMOS pontos)
e `edge` (`expectativa - expectativa_base_vender`) — `calibrar()` ranqueia por `edge`,
não por expectativa bruta.

**Resultado da validação:** com a correção, a combinação degenerada (0,0) sai do sweep
(nenhum sinal sobra). E o achado real: **toda combinação testada hoje mostra edge
negativo** (-63% a -79%) contra a base "sempre vender" — ou seja, com os dados atuais
(63 séries, um único ativo, amostra pequena), nenhum peso testado demonstra vantagem
real sobre simplesmente vender opções e deixar o theta trabalhar. Isso é a leitura
honesta do que os dados atuais permitem concluir — não invalida o desenho do Score
(Diff/Skew), só confirma que ainda não há evidência estatística de edge com o histórico
disponível. Auto-teste sintético (sem depender de rede/banco) cobre os dois casos em
`backtest_opcoes.py`.

**Ainda pendente:** amostra pequena (13-63 séries, só PETR4) — nenhuma calibração deve
ser aplicada em produção até acumular mais histórico e, idealmente, mais de um ativo.

**Avaliado e adiado:** motor de backtest mais robusto (Backtrader — viável, mas exercício/
vencimento de opções não é nativo, teria que ser construído de qualquer forma; QuantConnect/
LEAN — mais completo para opções, mas sem suporte nativo a B3, exigiria feed de dados
customizado do zero a partir da brapi). Nenhum dos dois resolve o viés de theta-decay
nem o tamanho da amostra — não vale adotar antes de resolver os dois pontos acima.

### 4.5 Correção aplicada (2026-08-30) — piso de preço relevante

Opções negociando abaixo de `PRECO_MINIMO_RELEVANTE = 0.05` (residuais de fim de vida,
quase sem valor) agora são excluídas do ranking (`analises_opcoes.py`) e do backtest
(`backtest_opcoes.py`) — nesses casos o preço justo também fica perto de zero e
`Desconto=(justo-mercado)/justo` explode numericamente (chegou a -9000%+ nos dados reais),
dominando o Score por instabilidade numérica, não por sinal de mercado. Essa correção é
independente da pendência 4.4 (colinearidade) — resolve um problema diferente (instabilidade
numérica em preços residuais) e reduziu pouco a amostra (53→51 sinais nos dados atuais).

---

## 5. ROADMAP — próximos passos (em ordem sugerida)

### Prioridade 1 — Backtest (detalhado na seção 4)
- [x] Coletar histórico de vencimentos vencidos da PETR4 (63 séries coletadas até
      2026-08-30 — ainda pouco para confiança estatística, seguir acumulando)
- [x] Redesenhar o Score (`Skew_pp` no lugar de `Desconto` — ver 4.4, resolvido)
- [x] Rodar calibração de novo — sweep passou a variar de verdade (não mais idêntico
      pra todo peso)
- [x] Corrigir o viés de theta-decay no backtest (4.4b, resolvido) — achado: nenhuma
      combinação testada hoje mostra edge real acima de "sempre vender"
- [ ] Acumular mais histórico/ativos (amostra pequena demais pra confiar em qualquer
      calibração ainda — nenhum edge positivo encontrado até agora)
- [ ] Só então: aplicar o peso calibrado em `analises_opcoes.py` (hoje `peso_diff=0.6`,
      `peso_skew=0.6` seguem arbitrários)

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
