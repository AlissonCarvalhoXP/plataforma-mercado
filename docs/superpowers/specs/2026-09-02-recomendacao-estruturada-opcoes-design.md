# Recomendação estruturada de operações com opções — design

**Data:** 2026-09-02
**Módulo:** `modules/opcoes/` (MIH — Market Intelligence Hub)
**Status:** design aprovado, aguardando plano de implementação

---

## 1. Contexto e motivação

Hoje a ferramenta recomenda operações assim: calcula um Score, aplica corte em
zero, e rotula cada série da cadeia como `COMPRAR_VOL` ou `VENDER_VOL`. A
"recomendação" destacada é a série de maior Score entre as compras e a de menor
entre as vendas.

Três achados tornam esse desenho insustentável:

**1. O Score não prevê retorno.** O backtest sobre 3,87 milhões de linhas do
COTAHIST (2024-2025, 188 ativos, 238.918 séries) não encontrou edge. Nos ativos
líquidos o edge é indistinguível de zero: −0,82% com IC 95% [−1,79%, +0,69%] nos
5 mais líquidos. O edge positivo aparente no universo amplo (+4,98%) é artefato
de microestrutura — cresce monotonicamente conforme a liquidez cai, de −1,32% nos
3 mais líquidos a +25,67% nos 45 mais ilíquidos. Detalhes na seção 4.4c do
`modules/opcoes/ROADMAP_MIH_Opcoes_Handoff.md`.

**2. A fórmula em produção nunca foi a testada.** O backtest chama
`calcular_score()` com `liq=0` e `peso_liq=0.0`; a produção chama com liquidez
real e `peso_liq=0.05`. São fórmulas diferentes — nenhuma conclusão do backtest
se aplica formalmente ao que roda na tela enquanto isso for verdade.

**3. O rótulo promete o que não se sustenta.** "Sinal de COMPRA de volatilidade"
sobre uma call solta é duplamente impreciso: sugere poder preditivo que não
existe, e a operação sugerida carrega delta — não é exposição a volatilidade.

Este design troca "recomendar o que vai dar certo" por **"estruturar bem o que
você decidiu fazer, e quantificar exatamente onde você discorda do mercado"**.

## 2. Princípio orientador

A ferramenta só afirma o que consegue sustentar:

| Afirma | Não afirma |
|---|---|
| Preço relativo observado (IV vs. HV, vs. sorriso) | Que isso prevê retorno |
| Risco financeiro exato de uma estrutura no vencimento | Probabilidade real de lucro |
| O que está embutido no preço das opções | Que o mercado está certo ou errado |
| Consequência do seu cenário, sob sua premissa | Que seu cenário vai se realizar |

Toda separação entre fato de mercado e premissa do usuário é explícita na tela.

## 3. Arquitetura

| Módulo | Responsabilidade | Estado |
|---|---|---|
| `analises_opcoes.py` | IV, sorriso, Score, ranking | corrigido |
| `distribuicao_opcoes.py` | Distribuição implícita, comparação com cenário | novo |
| `estruturas_opcoes.py` | Motor de payoff, catálogo, viabilidade | novo |
| `db_opcoes.py` | Tabela `opcoes_cenarios` | estendido |
| `paginas/opcoes.py` | UI | estendido |

Módulos novos são **funções puras**: sem banco, sem rede, sem efeito colateral —
mesmo padrão de `exposicao.py` e `analises.py`. Quem chama monta os dados.

**Fluxo:** ranking → distribuição implícita → cenário declarado → divergência →
estruturas viáveis → risco exato + payoff em cada cenário.

## 4. Correções em `analises_opcoes.py`

**4.1 Liquidez sai do Score direcional.** O termo `+ log1p(liq) * peso_liq` é
removido de `calcular_score()`. Liquidez passa a ser filtro e atributo de
qualidade da linha, não evidência direcional. Motivo duplo: liquidez não é
informação sobre a vol estar cara ou barata (uma opção líquida ganhava ~+0,46 de
Score só por ser líquida, o bastante para inverter o sinal); e a remoção alinha
produção com o que o backtest efetivamente mediu.

**4.2 Zona neutra.** `Sinal` passa a ter três estados: `COMPRAR_VOL`, `NEUTRO`,
`VENDER_VOL`. O limiar é expresso em pontos de volatilidade e configurável.

O valor do limiar é **arbitrário e declarado como tal** no código e na tela. Não
há como calibrá-lo: calibrar exigiria o poder preditivo que o backtest mostrou
não existir. Um número honestamente arbitrário é preferível a um número com
aparência de otimizado.

**4.3 Sorriso ajustado por `(Tipo, Data_Vencimento)`.** Hoje o agrupamento é só
por `Tipo`, então uma série de 7 dias e outra de 90 entram na mesma parábola.
Como a superfície de volatilidade tem estrutura a termo, parte do `Skew_pp`
mede diferença de prazo, não desvio de strike. A mesma correção vale para
`_construir_sorrisos_por_dia()` em `backtest_opcoes.py`, que tem o mesmo defeito.

**4.4 Rótulo honesto.** O texto de saída passa a descrever "desvio de preço
observado", nunca previsão.

## 5. Motor de payoff (`estruturas_opcoes.py`)

### 5.1 Representação

Uma estrutura é uma lista de pernas. Cada perna:
`(lado, tipo, strike, prêmio, quantidade, vencimento)`, onde lado é
`comprar`/`vender` e tipo é `CALL`/`PUT`. Quantidade permite ratio spreads sem
tratamento especial.

### 5.2 Payoff no vencimento

Ao preço `S` do ativo, por ação:

| Perna | Payoff |
|---|---|
| Compra de CALL | `max(S − K, 0) − prêmio` |
| Venda de CALL | `prêmio − max(S − K, 0)` |
| Compra de PUT | `max(K − S, 0) − prêmio` |
| Venda de PUT | `prêmio − max(K − S, 0)` |

Combinado = soma das pernas × quantidade × lote (100).

### 5.3 Extremos e breakevens exatos

O payoff combinado é linear por partes, com quebras **apenas nos strikes**.
Portanto:

1. Avaliar em `S = 0`, em cada strike, e num ponto além do maior strike.
2. Inclinação acima do maior strike = quantidade líquida de calls. Positiva
   implica ganho ilimitado; negativa implica **perda ilimitada**.
3. Abaixo do menor strike o ativo é limitado por `S >= 0`, então esse lado é
   sempre finito e o extremo está em `S = 0`.
4. Breakevens: em cada segmento entre quebras consecutivas, se o payoff troca de
   sinal, resolver linearmente o cruzamento do zero.

Os valores saem exatos por construção geométrica — sem grade aproximada.

### 5.4 Catálogo declarativo

Cada estrutura é uma declaração (nome, teses que expressa, pernas com seletor de
strike, restrição de vencimento), não código próprio. Acrescentar uma estrutura é
acrescentar uma linha na tabela; a matemática de risco é escrita e testada uma
vez só.

**Seletores de strike** indexam a escada de strikes realmente listada: `ATM`,
`1º OTM`, `2º OTM`, `1º ITM`. Não se usa seleção por delta, que dependeria de
qual volatilidade alimenta o modelo — indexação sobre a cadeia real é verificável
por inspeção e não carrega premissa.

**Catálogo por tese:**

| Tese | Estruturas |
|---|---|
| Vol cara, sem visão direcional | Venda de straddle/strangle, borboleta comprada, condor |
| Vol barata, sem visão | Compra de straddle/strangle |
| Vol cara + alta | Venda de put, trava de alta com puts (crédito) |
| Vol cara + baixa | Venda coberta de call, trava de baixa com calls (crédito) |
| Vol barata + alta | Compra de call, trava de alta com calls (débito) |
| Vol barata + baixa | Compra de put, trava de baixa com puts (débito) |
| Estrutura a termo | Calendário (vencimentos distintos) |

### 5.5 Os dois eixos da tese têm origens diferentes

| Eixo | Origem | Base |
|---|---|---|
| Volatilidade (cara/barata) | Ferramenta sugere, usuário confirma | Desvio observado de IV |
| Direção (alta/baixa/lateral) | **Somente o usuário**, via cenários (seção 7) | A ferramenta não tem base |

A ferramenta nunca sugere direção. Sem visão declarada, oferece apenas estruturas
neutras em delta.

**O cenário declarado é a entrada direcional** — não há seletor separado de
alta/baixa. Declarar `Alta R$42 25% / Base R$35 55% / Baixa R$28 20%` já é
expressar visão direcional de forma probabilística e auditável, o que é mais
informativo que escolher um rótulo num menu. Sem cenário declarado, o eixo
direcional fica ausente e só as estruturas neutras em delta são oferecidas.

**Posição na carteira não é visão.** O campo `direcao` (`long`/`short`) da
carteira entra como **viabilidade** — ter as ações habilita venda coberta e
dimensiona contratos — nunca como opinião direcional inferida. Estar long por
razão estrutural, querendo proteger, é o oposto de estar long por achar que sobe.

### 5.6 Controle da explosão combinatória

1. Só strikes numa faixa de moneyness ao redor do spot.
2. Só pernas com liquidez acima do mínimo configurado.
3. Teto de variantes por tipo de estrutura, priorizando as pernas mais líquidas.

## 6. Distribuição implícita (`distribuicao_opcoes.py`)

### 6.1 Método

Ajusta o sorriso do vencimento, precifica calls numa grade fina de strikes, e
extrai a densidade neutra ao risco por diferenças finitas (Breeden-Litzenberger):
a probabilidade de terminar entre dois strikes corresponde ao preço de uma
borboleta estreita ali. A probabilidade **é** um preço observável, não uma
estimativa do modelo.

### 6.2 Risco-neutro não é probabilidade do mundo real

A distribuição extraída embute prêmio de risco de variância, que para ações
**infla sistematicamente a cauda de baixa**. O mercado precificar 12% de queda
forte não significa que ele atribua 12% de crença a esse evento — parte é o custo
do seguro.

Consequência de design, obrigatória na tela: exibir sempre como "embutido no
preço", **nunca** como "o mercado acha". Toda comparação com o cenário do usuário
carrega a ressalva de que a diferença tem componente de prêmio de risco, não só
de opinião. Sem isso, a ferramenta faria o usuário enxergar divergência onde há
apenas remuneração de risco.

### 6.3 Densidade negativa

Uma parábola extrapolada viola não-arbitragem com facilidade, e a segunda
derivada pode sair negativa. Nesse caso a função **recusa** a distribuição e
informa o motivo, em vez de exibir número inválido ou truncá-lo silenciosamente.

## 7. Cenários

### 7.1 Declaração

Manual e explícita, três estados por vencimento alvo, cada um com preço-alvo,
probabilidade subjetiva e premissa em texto livre:

```
Alta   R$ 42   25%   Selic cai, Brent > 80, lucro acima do consenso
Base   R$ 35   55%   cenário atual se mantém
Baixa  R$ 28   20%   Selic sobe, Brent < 65
```

Deliberadamente manual nesta fase. Derivar preço-alvo automaticamente de macro e
resultados seria construir um modelo preditivo — exatamente o que o backtest
mostrou ser difícil — antes de saber se o fluxo é útil na prática. Automatizar
partes é evolução futura, depois de validado o uso.

### 7.2 Persistência

Tabela `opcoes_cenarios` no SQLite local: ativo, data de declaração, vencimento
alvo, cenário, preço-alvo, probabilidade, premissa.

A data de declaração habilita a aferição posterior: com o tempo, é possível medir
se os cenários do usuário acertam mais que o preço implícito. **Isso é
genuinamente calibrável**, ao contrário do Score.

### 7.3 Saída

Comparação por faixa de preço, seguida das estruturas viáveis — cada uma com
risco máximo, breakevens, prêmio líquido e payoff calculado em cada um dos três
cenários declarados.

**A divergência não filtra as estruturas.** Toda estrutura viável é exibida, e
cada uma mostra dois valores esperados lado a lado: sob a **sua** distribuição
declarada e sob a **implícita no preço**. A diferença entre os dois é o ganho
esperado que existe *se a sua premissa estiver certa*.

Isso respeita a decisão de não eleger uma estrutura: em vez de a ferramenta
aplicar um critério de seleção próprio, ela expõe a consequência de cada opção
sob as duas visões e deixa a comparação com o usuário. Também evita inventar uma
regra de mapeamento divergência→estrutura que seria mais uma premissa embutida.

A ressalva da seção 6.2 acompanha essa comparação: parte da diferença entre as
duas distribuições é prêmio de risco, não discordância de opinião.

## 8. Tratamento de erro

Toda falha é explícita e diz o motivo. Nenhuma exibe número inválido.

| Situação | Comportamento |
|---|---|
| Menos de 4 strikes distintos no vencimento | Sem sorriso e sem distribuição; informa quantos faltam |
| Densidade negativa | Recusa a distribuição e explica |
| Perna sem liquidez mínima | Estrutura não oferecida; informa qual perna faltou |
| Nenhum cenário declarado | Apenas estruturas neutras em delta |
| Sem posição na carteira | Venda coberta não oferecida |

## 9. Testes

**9.1 Payoff — valores de livro-texto.** Trava de alta (compra CALL 30 a R$2,
venda CALL 35 a R$0,50): perda máxima R$150, ganho máximo R$350, breakeven
R$31,50, nada ilimitado. Idem straddle e borboleta.

**9.2 Distribuição — teste analítico exato.** Numa cadeia sintética com IV
constante, a distribuição neutra ao risco **é** lognormal com parâmetros em forma
fechada. A extração numérica deve bater com a fórmula analítica dentro de
tolerância. Isso trava o método contra a matemática, não contra um valor
produzido pela própria implementação.

**9.3 Viabilidade e erros.** Cada linha da tabela da seção 8 vira um caso.

**9.4 Regressão do Score.** Confirmar que `calcular_score()` sem o termo de
liquidez reproduz exatamente a fórmula que o backtest mediu.

## 10. Fatiamento sugerido

O plano de implementação deve entregar em fatias úteis isoladamente:

1. **Motor de payoff** — isolado, testável, útil sozinho (avalia estruturas
   montadas à mão).
2. **Correções em `analises_opcoes.py`** — independentes do resto.
3. **Catálogo e viabilidade** — sobre o motor pronto.
4. **Distribuição implícita** — independente do catálogo.
5. **Cenários, persistência e UI** — amarra tudo.

## 11. Limitações conhecidas

Documentadas no código, não escondidas:

1. **Payoff é no vencimento.** Séries de estilo americano podem ser exercidas
   antes, e dividendos alteram esse incentivo em calls. A convenção vigente de
   cada série na B3 não é afirmada aqui.
2. **Risco antes do vencimento difere do risco no vencimento.** Perda máxima no
   vencimento não protege de marcação a mercado adversa nem de chamada de margem
   no meio do caminho. Precisa aparecer na tela, não só no código — contradiz a
   leitura natural de "perda máxima".
3. **Prêmio de entrada é preço observado**, sujeito a spread. Em série ilíquida
   pode não ser executável.
4. **Margem não é calculada.** A B3 usa metodologia CORE (cenários de estresse por
   portfólio), não replicável fielmente aqui. Um número aproximado apresentado
   como exigido poderia levar a montar posição que a corretora recusa. A tela
   remete à corretora.
5. **Escopo inicial de um único ativo.** Cenário com fundamento não escala para
   188 tickers.

## 12. Fora de escopo

- Cálculo de margem (ver 11.4).
- Derivação automática de preço-alvo a partir de macro e resultados (ver 7.1).
- Retomar a busca por poder preditivo no Score.
- Execução de ordens.
