# Score de Opções sem Desconto — Design

**Data:** 2026-08-30
**Status:** Implementado

## 1. Motivação

Ao rodar o backtest do módulo de Opções (`modules/opcoes/backtest_opcoes.py`) contra
histórico real (63 séries, 317 pontos), o sweep de `peso_diff` (0,0 a 1,2) devolvia
**resultado idêntico para qualquer peso testado**. Não era falta de dado: `Desconto`
(preço-espaço, `(justo-mercado)/justo`) e `Diff` (vol-espaço, `IV-HV`) são
matematicamente quase colineares — Black-Scholes é monotônico em volatilidade, então
sempre que `IV < HV`, o preço justo calculado com `HV` fica maior que o mercado quase
por definição, tornando `Desconto` uma reexpressão não-linear do mesmo gap que `Diff`
já mede. Confirmado nos dados reais (correlação quase perfeita entre os dois). O
`peso_diff` nunca mudava o sinal `COMPRAR_VOL`/`VENDER_VOL` de nenhuma linha por causa
disso — não havia dois sinais independentes pra calibrar.

`Desconto` também é a versão mais frágil dos dois: perto do vencimento, com o preço
justo tendendo a zero, ele explode numericamente (chegou a -9000%+ nos dados reais,
corrigido separadamente com `PRECO_MINIMO_RELEVANTE` — ver commit anterior).

## 2. Decisão

`Desconto` sai do Score — vira campo apenas informativo (continua exibido no Ranking e
no texto das oportunidades). O Score passa a somar **dois eixos genuinamente
ortogonais**:

1. **`Diff_pp`** (já existia): gap entre IV e HV — vol atual vs. vol realizada.
2. **`Skew_pp`** (novo): gap entre a IV desta opção e a IV que o **sorriso de
   volatilidade do dia** (outras séries do mesmo vencimento/Tipo, no mesmo pregão)
   preveria para o seu strike. Ortogonal por construção: mede desvio *entre strikes*
   no mesmo momento, não *ao longo do tempo* contra HV — uma ação pode ter IV acima da
   HV (Diff positivo) e, ao mesmo tempo, essa mesma opção estar barata frente às
   vizinhas na cadeia (Skew negativo).

**Por que skew e não IV Rank/Percentile** (a outra opção óbvia, já no roadmap do
módulo, prioridade 6): IV Rank precisa de semanas/meses de histórico acumulado por
ativo para ter sentido (compara a IV de hoje com a distribuição dela mesma no tempo).
Skew usa dados de um único dia (a própria cadeia já coletada) — disponível hoje, sem
esperar acumular histórico. IV Rank continua como refinamento futuro, não descartado.

### 2.1 Ajuste do sorriso

`ajustar_sorriso(pontos: list[(strike, iv)])`: parábola `IV = f(Strike)` por mínimos
quadrados (`np.polyfit` grau 2). Exige **≥4 strikes distintos** — com 3 pontos a
parábola tem exatamente 3 graus de liberdade para 3 parâmetros e interpola tudo
perfeitamente (resíduo sempre zero, não mediria nada). Devolve `None` quando não há
pontos suficientes; nesse caso `Skew_pp = 0.0` para as opções daquele dia/Tipo — não
inventa um sorriso a partir de poucos dados.

### 2.2 Score

```python
def calcular_score(diff_pp, skew_pp, liq, peso_diff=0.6, peso_skew=0.6, peso_liq=0.05):
    return -diff_pp * peso_diff - skew_pp * peso_skew + math.log1p(max(0, liq)) * peso_liq
```

Função pura, compartilhada entre `analises_opcoes.analisar()` (screener ao vivo) e
`backtest_opcoes.rodar_backtest()` (backtest) — antes o backtest tinha sua própria
reimplementação da fórmula (`score_linha()`), o que já tinha permitido a fórmula real
divergir silenciosamente da documentada (o handoff do módulo registrava uma correção
que não tinha, de fato, sido replicada da forma certa). Agora os dois usam a mesma
função; drift entre screener e backtest deixa de ser possível.

Pesos default (`peso_diff=0.6`, `peso_skew=0.6`) continuam **arbitrários** — a
calibração via backtest é o próximo passo, agora que o sweep de peso tem algo real
para calibrar (seção 4).

### 2.3 Backtest

`_construir_sorrisos_por_dia(hist)`: agrupa o histórico por `(Data, Tipo)` e ajusta um
sorriso por grupo, reaproveitando `ajustar_sorriso` — mesma lógica do screener,
aplicada retroativamente aos dados já coletados. `calibrar()` passa a varrer uma
**grade 2D** (`peso_diff` × `peso_skew`, 4×4 pontos por padrão) em vez de um sweep 1D —
faz sentido calibrar dois pesos independentes juntos, não um de cada vez.

## 3. Resultado da validação (2026-08-30, 63 séries)

A degenerescência sumiu: o sweep agora varia de verdade entre combinações de peso
(antes: resultado idêntico em todas as 7 linhas; depois: `win_rate` variando de 47,1% a
94,1% conforme a combinação). Isso confirma que a correção resolveu o problema
mecânico que motivou este design.

**Achado adicional, não resolvido aqui:** a combinação "vencedora" do sweep
(`peso_diff=0, peso_skew=0`) é um artefato trivial — com os dois pesos zerados, o Score
fica exatamente 0,0 para toda linha (a única parcela restante é liquidez, sempre 0 no
histórico), e `score > 0` nunca é verdadeiro, então **todo sinal cai em "VENDER_VOL"
por padrão**. O resultado "94,1% de acerto" está capturando o decaimento médio de
theta (opção perde valor com o tempo, então "sempre vender" tende a acertar), não uma
informação real do Diff/Skew. Esse é um viés clássico de backtest de opções (apostar
sempre contra o preço captura theta, não edge) e precisa ser tratado antes de confiar
em qualquer peso "vencedor" — ex.: comparar contra uma linha de base "sempre vender"
explícita, ou excluir a banda de score ≈ 0 da contagem de sinais. Registrado no roadmap
do módulo como pendência separada (seção 4.4), não corrigido nesta sessão.

## 4. Fora de escopo

- IV Rank/Percentile — depende de acumular histórico por ativo ao longo de semanas
  (já no roadmap do módulo, prioridade 6).
- Term structure (comparar IV entre vencimentos diferentes) — exigiria coletar mais de
  um vencimento por vez (hoje `coleta_opcoes.py` foca só no vencimento mais próximo de
  35 dias).
- Correção do viés de theta-decay no backtest (seção 3, achado adicional).
- GARCH real para a HV (já no roadmap do módulo) — melhoraria a qualidade do
  `Diff_pp`, mas é refinamento independente deste design.
