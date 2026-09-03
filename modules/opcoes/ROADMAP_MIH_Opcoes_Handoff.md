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

### ✅ 4.4c RESOLVIDO (2026-08-31) — Amostra ampliada via COTAHIST: **sem edge real**

A pendência "amostra pequena" de 4.4b foi atacada de frente: pipeline próprio de
ingestão do **COTAHIST da B3** (`modules/opcoes/coleta_cotahist.py`, gratuito, sem
token), cobrindo **2024-2025 inteiros, todos os ativos com opções negociadas**.

**Resultado da coleta:** 3.870.372 linhas limpas em `opcoes_historico`
(1.734.303 de 2024 + 2.136.069 de 2025), **188 ativos**, **238.918 séries** — contra
as 63 séries de PETR4 que bloqueavam a calibração antes.

**Quatro bugs reais encontrados e corrigidos no caminho** (todos achados testando
contra dado real, não por revisão de código):

1. **Dependência do Postgres remoto no meio de job longo** — `coleta_cotahist.py` lia
   a Selic via `db.engine` (remoto), violando o isolamento deliberado de
   `modules/opcoes/` (que usa SQLite local de propósito). Causou um
   `PendingRollbackError` e depois um socket preso em `CloseWait` travando o processo.
   Corrigido: Selic passou a vir do mesmo SQLite local, e `coleta_bcb_historico.py`
   ganhou `--db-path` pra popular esse arquivo. Pipeline agora não depende de rede
   além do download da B3.
2. **IV presa no piso/teto do solver** — o Newton-Raphson vetorizado não converge
   quando vega ≈ 0 (opções fundo ITM/OTM: moneyness médio 0,54 nessas linhas vs. 0,11
   nas saudáveis). **11% das linhas** (479.313) tinham IV grudada em 1e-4 ou 5.0 — não
   é IV, é falha de convergência. Descartadas na origem.
3. **Sorriso misturando ativos diferentes** — `_construir_sorrisos_por_dia` agrupava por
   `(Data, Tipo)`, o que era inofensivo com um ativo só, mas ao juntar 188 ativos
   misturaria strikes de PETR4 (~R$35) com WEGE3 (~R$50) no mesmo ajuste. Corrigido para
   `(Data, Tipo, Ativo_Objeto)`, com teste de regressão (Caso 3).
4. **Colisão de ticker entre ciclos de vencimento** — o código de opção da B3 **não
   carrega o ano**, e é reciclado: **29.103 dos 238.918 códigos (12,2%)** têm mais de um
   `Data_Vencimento`. Agrupar séries só por `Codigo_Opcao` colava contratos diferentes,
   e o "retorno no horizonte" comparava o preço de UM contrato com o de OUTRO. Isso
   produzia retorno bruto médio de **+15,48% em 5 pregões** (implausível) e inflava o
   edge de ~3% para ~15%. Corrigido para `(Codigo_Opcao, Data_Vencimento)`.

**Veredito da calibração — não há edge real:**

Com tudo corrigido, o pool completo (176 ativos, 2.322.039 pontos) mostra edge de
+4,98% na melhor combinação (`peso_diff=0.3`, `peso_skew=1.0`). Mas o teste decisivo
— **edge em função da liquidez** — mostra que isso é artefato de microestrutura:

| Liquidez (pontos por ativo) | Ativos | Edge pool | Edge mediano |
|---|---|---|---|
| ≥100k (mais líquidos) | 3 | **−1,32%** | −1,16% |
| 30k–100k | 20 | +6,21% | +3,05% |
| 10k–30k | 39 | +4,15% | +2,92% |
| 3k–10k | 39 | +11,54% | +7,64% |
| 1k–3k | 30 | +14,53% | +8,69% |
| <1k (ilíquidos) | 45 | **+25,67%** | +12,45% |

Acumulado pelos mais líquidos: **top 5 = −0,82%**, top 10 = +3,04%, top 20 = +3,59%,
todos os 176 = +4,98%.

**O edge cresce monotonicamente conforme a liquidez cai** — de −1,3% nos três ativos
mais negociados até +25,7% nos 45 mais ilíquidos. Essa é a assinatura clássica de
artefato de microestrutura, não de sinal: opção ilíquida tem preço de fechamento
defasado, spread largo e pouquíssimos negócios; e como o retorno de opção é convexo
(perda limitada a −100%, ganho ilimitado), ruído puro produz média positiva.
**Exatamente onde seria operável, o edge é negativo.**

Casos extremos ilustram o ruído: TRAD tem "edge" de +408,8% com **n=3 pontos**;
LAVV, −119,6% com n=8. A mediana de 176 ativos majoritariamente ilíquidos descreve
o ativo ilíquido típico, não vantagem operável — por isso a leitura por faixa de
liquidez, e não a mediana global, é a que vale.

**Um artefato adicional confirmado:** MGLU (edge +29,8% no recorte líquido) tem salto
de R$1,32 → R$13,15 num pregão (+896%, 24→27/05/2024) — o grupamento da Magazine
Luiza. **O COTAHIST traz preços brutos, não ajustados por evento societário.**

**Quanta incerteza há nisso (bootstrap por ativo, 400 reamostragens):**

Reamostrar pontos individuais superestimaria a precisão — janelas de 5 pregões se
sobrepõem e todas as opções do mesmo ativo/dia se movem juntas. Reamostrando o ativo
inteiro (bootstrap por cluster):

| Universo | Ativos | Edge | IC 95% | P(edge>0) |
|---|---|---|---|---|
| Top 5 mais líquidos | 5 | −0,82% | **[−1,79% , +0,69%]** | 13,8% |
| Top 10 | 10 | +3,04% | [−0,77% , +10,04%] | 89,2% |
| Top 20 | 20 | +3,59% | [+0,36% , +8,46%] | 98,2% |
| Todos | 176 | +4,98% | [+2,90% , +7,76%] | 100% |

**Leitura correta:** nos ativos líquidos o edge é **indistinguível de zero** (o IC
cruza o zero), não comprovadamente negativo. A afirmação sustentada é "não é
positivo", não "é negativo". Nos universos amplos o edge é estatisticamente
significativo — mas significância não conserta viés: um estimador enviesado com IC
estreito continua enviesado, e o gradiente monotônico por liquidez é o que indica
viés. Custos de transação (spread, slippage), **não modelados no backtest**, só
empurrariam o resultado para baixo — o que reforça a decisão prática.

**Limites de confiança:** (a) o tier líquido tem só 5 clusters, então o próprio IC é
impreciso; (b) um único regime (2024-2025, Selic alta); (c) foi testada UMA
formulação — linear, horizonte de 5 pregões, regra `score>0 → comprar vol`. Ausência
de edge nesta formulação não implica que `Diff`/`Skew` sejam inúteis em geral.

**Conclusão honesta:** ampliar a amostra em 3.800x (63 séries → 238.918) **não revelou
edge nenhum**. O achado de 4.4b se confirma num universo muito maior: `Diff` e `Skew`
como estão não demonstram vantagem sobre a linha de base nos ativos onde se poderia
operar. Os pesos `peso_diff=0.6` / `peso_skew=0.6` em `analises_opcoes.py` **seguem
arbitrários e não devem ser calibrados** com base nisso — calibrar contra ruído de
microestrutura é pior que não calibrar.

**Limitação conhecida (não corrigida):** eventos societários não são ajustados. Antes de
qualquer nova tentativa de extrair sinal desta base, isso precisa ser tratado (detectar
saltos >35% em um pregão e descartar/ajustar a série).

**Desempenho:** `preparar_pontos()` separa a varredura cara (HV móvel, sorrisos, filtros)
da pontuação, que é a única parte dependente dos pesos — o sweep recalculava tudo 16
vezes. Caso 4 do auto-teste trava a equivalência entre o score vetorizado e o
`calcular_score()` do screener ao vivo.

### ❌ 4.4d REPROVADO NO GATE (2026-09-02) — modelo de cenários automáticos por FHS

Tentativa de substituir a declaração manual de cenários por um modelo
estatístico (Filtered Historical Simulation sobre EWMA). **O modelo não passou
na avaliação de calibração e NÃO foi para produção** — a declaração manual
permanece.

**O desenho previa esse desfecho.** A spec
(`docs/superpowers/specs/2026-09-02-cenarios-automaticos-fhs-design.md`, seção
5.5) colocava a avaliação ANTES da integração justamente para que um modelo mal
calibrado fosse descoberto antes de virar tela. Foi o que aconteceu.

**Resultado do walk-forward** (janelas não sobrepostas, horizonte 45 dias
úteis, 501 pregões por ativo, cada previsão usando somente dados até a data):

| Ativo | Janelas | CRPS modelo | CRPS benchmark | Ganho |
|---|---|---|---|---|
| PETR | 5 | 1,2259 | 1,2675 | **+3,3%** |
| VALE | 5 | 2,4276 | 2,1070 | −15,2% |
| ITUB | 5 | 1,4061 | 1,3415 | −4,8% |
| BBDC | 5 | 11,6957 | 0,9361 | **−1149,4%** |
| BBAS | — | recusado pela guarda de salto (51% num pregão) | | |

**Agregado: −196,4%**, dominado inteiramente pelo BBDC. **Excluindo BBDC:
−7,3%** (modelo 1,6865 vs benchmark 1,5720). Reprovado nos dois recortes — dois
de três ativos restantes perdem para o benchmark.

**O que o BBDC revelou:** sua série tem 2 saltos acima de 15% (máximo 15,9%:
R$16,60 → R$13,96), quase certamente bonificação ou desdobramento, não
movimento de mercado. Eles passaram pela guarda de `SALTO_MAXIMO = 0.35`, que
foi calibrada para o caso extremo do MGLU (+896%). Como o EWMA com λ=0,94 é
muito reativo, uma janela iniciada logo após esse salto produz distribuição
absurdamente larga e CRPS catastrófico.

**Achado que vale para além deste modelo:** a guarda de 35% é frouxa demais
para eventos societários comuns, que ficam na faixa de 10-20%. Qualquer trabalho
futuro sobre esta base precisa de ajuste de proventos de verdade, não de um
filtro de salto — limitação já registrada em 4.4c e agora confirmada com custo
concreto.

**O que passou:** a uniformidade do PIT **não foi rejeitada** (p = 0,235). Ou
seja, a *forma* da distribuição prevista é compatível com a realizada; o modelo
falha em ser mais *afiado* que o benchmark, não em ser enviesado.

**Conclusão honesta:** prever a largura da distribuição com EWMA sobre 501
pregões não bate a distribuição empírica incondicional nos ativos testados.
Volatilidade é previsível em princípio, mas a vantagem não sobreviveu à
medição — nem com dados sujos por eventos societários, nem sem eles.

**O que fica construído e utilizável:** `modelo_cenarios.py` (EWMA, FHS,
resumo em cenários, guardas) e `avaliacao_previsoes.py` (PIT, CRPS,
walk-forward, benchmark) permanecem no repositório, testados. A infraestrutura
de avaliação serve para qualquer modelo futuro — é o gate, não o modelo, que é
o ativo duradouro aqui.

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
