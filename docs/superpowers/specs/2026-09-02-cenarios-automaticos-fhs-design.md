# Cenários automáticos por Filtered Historical Simulation — design

**Data:** 2026-09-02
**Módulo:** `modules/opcoes/` (MIH — Market Intelligence Hub)
**Substitui:** a declaração manual de cenários da seção 7 de
`2026-09-02-recomendacao-estruturada-opcoes-design.md`
**Status:** design aprovado, aguardando plano de implementação

---

## 1. Contexto e motivação

O desenho atual pede que o usuário declare três cenários à mão (preço-alvo e
probabilidade). Isso funciona, mas depende de o usuário ter uma visão formada
toda vez, e não escala.

A substituição por um modelo automático tem uma armadilha específica que este
design existe para evitar.

### 1.1 A armadilha

Se o modelo estimar a distribuição a partir da volatilidade histórica e a
compararmos com a implícita, o resultado é literalmente `IV − HV` — que é o
`Diff_pp` já presente no Score, e que o backtest sobre 3,87 milhões de linhas
mostrou não ter edge (seção 4.4c do `ROADMAP_MIH_Opcoes_Handoff.md`).

Um modelo assim não acrescentaria informação: reembalaria o mesmo sinal com
mais etapas e mais aparência de sofisticação.

### 1.2 A saída: separar P de Q, como as mesas fazem

Casas quantitativas não geram cenários para ganhar do mercado. Elas mantêm duas
medidas com finalidades distintas:

| Medida | Origem | Serve para |
|---|---|---|
| **Q** (neutra ao risco) | Preços de opção | Precificar |
| **P** (mundo real) | Histórico + modelo | Risco, dimensionamento, VaR |

A diferença entre P e Q é o **prêmio de risco** — documentado, persistente e já
precificado. Não é vantagem.

Este design entrega a medida P. O valor não é prever melhor que o mercado: é
ter uma distribuição realista (com cauda gorda e assimetria) para dimensionar
posição e entender risco, coisa que a medida Q não fornece.

**A tela deve dizer isso.** A divergência entre P e Q é rotulada como prêmio de
risco, nunca como oportunidade.

## 2. Princípio orientador

| Afirma | Não afirma |
|---|---|
| Volatilidade é previsível (clustering é fato empírico robusto) | Que direção é previsível |
| A distribuição tem esta forma, dadas as dinâmicas históricas | Que o mercado está errado |
| O modelo é (ou não é) bem calibrado — medido | Que calibração implica lucro |

## 3. O modelo

### 3.1 Previsão de volatilidade

EWMA (RiskMetrics) como base: `var_t = lambda * var_{t-1} + (1 - lambda) * r_{t-1}^2`,
com `lambda = 0.94` para dados diários.

EWMA e não GARCH completo por decisão de escopo: temos 501 observações diárias,
e estimar GARCH(1,1) com essa amostra dá parâmetros instáveis. EWMA tem um
parâmetro fixo e conhecido, não precisa de otimização, e captura o efeito que
importa (clustering). GARCH fica como evolução, se a avaliação da seção 5
indicar que vale.

### 3.2 Filtered Historical Simulation

Procedimento, na ordem:

1. Calcular retornos log diários do ativo.
2. **Remover a média** dos retornos (ver 3.3 — passo crítico).
3. Rodar a recursão EWMA, obtendo a série de volatilidade condicional `sigma_t`.
4. Extrair os resíduos padronizados `z_t = r_t / sigma_t`. Esse conjunto carrega
   a cauda gorda e a assimetria reais do ativo, sem assumir distribuição.
5. Para cada caminho simulado, ao longo do horizonte: sortear `z` do conjunto
   empírico (com reposição), aplicar à volatilidade prevista, acumular o retorno
   e atualizar a recursão de volatilidade com o choque sorteado.
6. Preço terminal = `spot * exp(soma dos retornos do caminho)`.
7. **Recentrar no preço a termo** (ver 3.3).

O resultado é uma distribuição empírica de preços no vencimento, com caudas e
assimetria vindas do próprio ativo.

### 3.3 Por que remover a média e recentrar no termo

**Este é o ponto que separa o modelo de uma previsão disfarçada.**

Se os retornos históricos não forem centrados, a simulação herda o drift do
período amostral. Um ativo que subiu em 2024-2025 geraria uma distribuição
deslocada para cima — e isso seria **prever direção a partir de retorno
passado**, exatamente a armadilha da seção 1.1. Retorno esperado é
notoriamente difícil de estimar; drift amostral de 2 anos é ruído.

Por isso: os retornos são de-mediados antes de extrair os resíduos, e a
distribuição simulada é recentrada no **preço a termo** (`spot * exp(r * T)`),
que é não-arbitragem, não opinião.

O modelo prevê a **largura e a forma** da distribuição. Nunca o centro.

### 3.4 Saída no formato de cenários

Para plugar na UI existente sem reescrevê-la, a distribuição simulada é
resumida em três cenários. O horizonte `h` é sempre **os dias até o vencimento
da opção em análise** — não um parâmetro solto.

A distribuição é cortada nos quantis 25% e 75%, e cada cenário recebe:

| Cenário | Preço | Probabilidade |
|---|---|---|
| baixa | média condicional abaixo do quantil 25% | 25% |
| base | média condicional entre os quantis 25% e 75% | 50% |
| alta | média condicional acima do quantil 75% | 25% |

**O preço de cada cenário é a média condicional da sua região, não o quantil de
corte.** Isso importa: usar o quantil 10% como "preço do cenário de baixa" e ao
mesmo tempo atribuir a ele a massa abaixo do quantil 25% seria incoerente — o
ponto exibido não representaria a região que ele resume. Com a média
condicional, os três pontos são um resumo próprio da distribuição, e a soma
ponderada deles recupera a média da distribuição completa.

Ainda assim, **o cálculo de valor esperado usa a distribuição completa**, não os
três pontos: o resumo existe para exibição e para reaproveitar o comparador já
construído.

## 4. Evento de resultado (segunda fase)

Uma data de balanço dentro da vida da opção concentra variância num único dia e
produz vol crush depois. Saber onde a variância está alocada no tempo não é
prever direção.

Não há fonte gratuita estruturada de calendário de resultados (verificado:
brapi não expõe esse dado). A entrada é **manual, uma data por trimestre** —
distinção importante: é um **fato objetivo e verificável**, não uma opinião,
diferente do preço-alvo que este design remove.

Com as datas passadas informadas, o modelo estima o movimento absoluto médio
nesses dias a partir da própria série de preços, e acrescenta essa variância
extra ao dia do evento na simulação.

**Gate:** com 2 anos de dados há ~8 datas de resultado — amostra fina, com
incerteza larga. Esta fase só entra depois que o núcleo (seções 3 e 5) estiver
validado, e a estimativa carrega o número de observações em que se baseia.

## 5. Avaliação — o gate que decide se o modelo entra em produção

Esta seção é a razão de o design ser confiável, e vem **antes** da integração
com a UI.

### 5.1 Por que dá para validar agora

Calibração de previsão de densidade é uma pergunta **bem-posta**: "quando o
modelo diz 10% de chance, acontece 10% das vezes?" tem resposta objetiva. É
diferente do Score, que só conseguimos invalidar depois de muito trabalho.

E não é preciso esperar meses: com os 501 pregões de 2024-2025 dá para rodar
walk-forward — na data T, usando **somente** dados até T, prever a distribuição
em T+h e comparar com o que de fato ocorreu, repetindo ao longo da série.

### 5.2 Métricas

**PIT (Probability Integral Transform):** para cada previsão, calcular a
posição percentual do valor realizado na distribuição prevista. Se o modelo for
bem calibrado, esses valores são uniformes em [0,1]. Desvio da uniformidade
diagnostica o defeito: acúmulo nas pontas significa cauda estreita demais;
acúmulo no meio, cauda larga demais.

**CRPS (Continuous Ranked Probability Score):** regra de pontuação própria para
distribuições. Para um conjunto simulado, tem forma fechada em termos das
distâncias entre membros do conjunto e o valor realizado. Menor é melhor.

### 5.3 O benchmark que o modelo precisa vencer

CRPS sozinho não diz se o modelo é bom — só compara. O benchmark é a
**distribuição histórica incondicional**: mesmo horizonte, sem modelo de
volatilidade, apenas a distribuição empírica dos retornos passados.

Se o FHS não vencer esse benchmark, o modelo de volatilidade não está
agregando, e a complexidade não se justifica.

### 5.4 Janelas sobrepostas

Previsões em datas consecutivas com horizonte de h dias compartilham período e
não são independentes. A avaliação usa **janelas não sobrepostas** para as
métricas de calibração, ao custo de menos observações (com h=45 e 501 pregões,
cerca de 11 janelas independentes por ativo).

Esse número é pequeno. Por isso a avaliação roda sobre **vários ativos**, e o
resultado é reportado com o número de janelas em que se baseia — sem alegar
precisão que 11 observações não sustentam.

### 5.5 A decisão

**Se a calibração não passar, o modelo não entra em produção** e a declaração
manual permanece. Descobrir isso antes de trocar é o propósito desta seção.

## 6. Aferição contínua

Cada previsão gerada é persistida com a data em que foi feita, em
`opcoes_previsoes`: ativo, data da previsão, horizonte, os quantis da
distribuição prevista, e o preço realizado (preenchido depois).

Isso serve a dois propósitos:

1. Acompanhar, ao longo dos meses, se o modelo segue calibrado — regime de
   mercado muda, e um modelo calibrado em 2024-2025 pode deixar de ser.
2. Comparar, quando o usuário sobrepuser um cenário manual, se a visão dele
   vem acertando mais que o modelo. Essa comparação também é bem-posta.

## 7. Integração e o que permanece manual

O cenário automático vira o **padrão**. O override manual permanece disponível,
por um motivo específico: se o usuário sabe algo sobre a empresa que não está
no preço, essa é a única entrada potencialmente portadora de vantagem — um
modelo estatístico não a replica.

O que muda: o usuário deixa de ser **obrigado** a opinar para usar a
ferramenta.

Na tela, a origem de cada distribuição é sempre explícita: "modelo (FHS)",
"seu cenário", ou "embutido no preço".

## 8. Arquitetura

| Módulo | Responsabilidade | Estado |
|---|---|---|
| `modelo_cenarios.py` | EWMA, FHS, resumo em cenários | novo |
| `avaliacao_previsoes.py` | PIT, CRPS, walk-forward, benchmark | novo |
| `db_opcoes.py` | Tabela `opcoes_previsoes` | estendido |
| `view_opcoes.py` | Origem da distribuição, override | modificado |
| `distribuicao_opcoes.py` | Sem mudança — já aceita as duas formas | inalterado |

Módulos novos são funções puras, sem banco e sem rede, seguindo o padrão de
`exposicao.py` e dos módulos criados no design anterior.

**Fonte da série de preços:** `Preco_Ativo` de `opcoes_historico`, que já traz
501 pregões diários para 188 ativos (2024-2025). Não requer coleta nova.

## 9. Tratamento de erro

| Situação | Comportamento |
|---|---|
| Menos de 250 pregões de histórico | Recusa o modelo; sem série suficiente para EWMA e resíduos |
| Preços com salto > 35% em um pregão | Descarta a série e avisa: provável evento societário não ajustado (o COTAHIST traz preço bruto — grupamento do MGLU: R$1,32 → R$13,15) |
| Horizonte maior que o histórico disponível | Recusa |
| Menos de 8 janelas independentes na avaliação | Reporta as métricas com aviso de amostra insuficiente para conclusão |

## 10. Testes

**10.1 EWMA — contra valor conhecido.** Série sintética de volatilidade
constante deve produzir estimativa convergindo para essa volatilidade.

**10.2 FHS preserva os momentos.** Simulando a partir de resíduos com
assimetria e curtose conhecidas, a distribuição terminal deve preservar o sinal
da assimetria e curtose acima da normal.

**10.3 Recentragem no termo.** Com retornos históricos de drift forte
(sintéticos, subindo consistentemente), a mediana da distribuição simulada deve
ficar no preço a termo, **não** no preço extrapolado pelo drift. Este é o teste
que trava a decisão da seção 3.3 contra regressão.

**10.4 PIT de um modelo perfeito é uniforme.** Gerando dados de uma
distribuição conhecida e prevendo com essa mesma distribuição, os valores de
PIT devem passar num teste de uniformidade. Trava a implementação da métrica
contra a matemática.

**10.5 CRPS contra forma fechada.** Para uma previsão determinística (todos os
membros iguais), o CRPS reduz ao erro absoluto. Caso verificável na mão.

**10.6 Erros da seção 9.** Cada linha vira um caso.

## 11. Limitações conhecidas

1. **501 pregões é série curta.** Suficiente para EWMA, apertado para GARCH,
   e dá poucas janelas independentes na avaliação.
2. **Um único regime.** 2024-2025. Calibração pode não se sustentar em regime
   diferente — daí a aferição contínua da seção 6.
3. **Preços não ajustados por evento societário** (limitação herdada do
   COTAHIST). Mitigada pelo filtro de salto da seção 9, não resolvida.
4. **FHS assume que resíduos padronizados são i.i.d.** Se houver estrutura
   remanescente (assimetria de vol, efeito alavancagem), o EWMA não a captura.
5. **Calibração não implica lucro.** Um modelo perfeitamente calibrado descreve
   bem a distribuição e ainda assim não gera vantagem — a distribuição P estar
   correta não diz que a Q está errada.

## 12. Fora de escopo

- Consenso de analistas: sem fonte gratuita, e a evidência sobre calibração de
  preço-alvo de consenso é fraca. Implementar adicionaria complexidade e falsa
  sensação de fundamento.
- GARCH completo (ver 3.1) — reavaliar após a seção 5.
- Coleta automática de calendário de resultados (sem fonte).
- Modelagem de superfície de volatilidade estocástica.
