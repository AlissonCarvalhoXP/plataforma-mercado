# Coleta de Histórico de Opções via COTAHIST (B3) — Design

**Data:** 2026-08-30
**Status:** Aprovado para implementação

## 1. Motivação

O backtest de Opções (`modules/opcoes/backtest_opcoes.py`) está limitado pela amostra:
hoje só há histórico de PETR4 via brapi.dev (plano gratuito), com poucas séries
qualificadas (13-63 conforme a rodada) — insuficiente pra qualquer calibração
confiável (ver `docs/superpowers/specs/2026-08-30-score-opcoes-sem-desconto-design.md`
e `modules/opcoes/ROADMAP_MIH_Opcoes_Handoff.md` seções 4.4/4.4b). Ampliar via brapi
exige o plano Pro (R$ 116,66/mês, confirmado em brapi.dev/pricing) — e mesmo assim não
dá bid/ask real, só preço agregado.

A B3 publica gratuitamente, sem token, sem cadastro e sem limite de requisição, o
arquivo oficial de cotações históricas (COTAHIST) — todo pregão desde 1986, de todos os
papéis negociados, **incluindo opções, com bid/ask real** (campos que a brapi nem no
plano pago fornece no histórico). Layout oficial confirmado via PDF público da B3
(`SeriesHistoricas_Layout.pdf`, revisão de 13/04/2017) — ver seção 4.

## 2. Escopo

- **Ativos:** todos os que tiverem opções negociadas no arquivo do ano (não restrito à
  carteira atual) — mais amostra é sempre melhor pro backtest, e não custa mais caro
  processar o arquivo inteiro já que ele é baixado por inteiro de qualquer forma.
- **Período:** 2024 e 2025 (2 arquivos anuais). Anos mais antigos refletem regimes de
  mercado menos comparáveis a hoje; pode-se estender depois se necessário.
- **Modo de execução:** backfill manual (`python modules/opcoes/coleta_cotahist.py
  --ano 2024`), não entra na automação diária — arquivos anuais só ficam completos
  depois que o ano termina; coleta incremental do ano corrente continua sendo trabalho
  da brapi (`coleta_opcoes.py`/`coleta_opcoes_historico.py`), não deste pipeline.
- **Fora de escopo:** anos anteriores a 2024, arquivos diários da B3 (existem, mas não
  são necessários pro backfill de anos já fechados), qualquer mudança em
  `backtest_opcoes.py` (ele já lê tudo de `opcoes_historico` independente da fonte).

## 3. Arquitetura

Novo módulo `modules/opcoes/coleta_cotahist.py`, seguindo o padrão dos outros
coletores do módulo (`coleta_opcoes_historico.py`): script standalone com
`if __name__ == "__main__":` + `argparse`.

**Fluxo:**
1. Baixar `https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{ANO}.ZIP`
   (URL a confirmar no passo de verificação, seção 6 — a B3 já trocou domínio/caminho
   dessas URLs no passado).
2. Descompactar em memória (`zipfile`), obter `COTAHIST_A{ANO}.TXT`.
3. Ler linha a linha (245 bytes fixos, sem necessidade de carregar o arquivo inteiro em
   memória de uma vez — iterar o arquivo).
4. Para cada linha com `TIPREG="01"`:
   - Se `CODBDI` ∈ {"78", "82"} → registro de opção (78=CALL, 82=PUT, via tabela
     oficial anexa ao layout). Guardar temporariamente.
   - Se `CODBDI="02"` e `TPMERC="010"` → registro de ação à vista (lote padrão).
     Indexar por `(DATA_PREGAO, NOMRES)` → `PREULT` (preço de fechamento), mantendo o
     de maior `VOLTOT` em caso de mais de um registro com o mesmo `NOMRES` no mesmo dia
     (heurística: entre duas classes de ação do mesmo emissor, a mais líquida é a
     candidata a ter opções ativas — ver risco na seção 6).
5. Depois de indexar todo o arquivo: para cada registro de opção, buscar
   `(DATA_PREGAO, NOMRES)` no índice de ações à vista. Sem correspondência → descarta a
   linha (não inventa preço de ativo-objeto).
6. Calcular IV via `analises_opcoes.implied_vol()` (Black-Scholes, já existe), usando a
   Selic mais próxima daquela data (`indicadores_bcb`) como taxa livre de risco.
7. Gravar em `opcoes_historico` (schema estendido — seção 4.2), com
   `Fonte='b3_cotahist'`, `ON CONFLICT(Codigo_Opcao, Data) DO UPDATE` (mesmo padrão de
   `coleta_opcoes_historico.py` — idempotente, resumível).

## 4. Layout do arquivo (confirmado — PDF oficial da B3, revisão 01, 13/04/2017)

Registros de 245 bytes fixos. Campos relevantes do Registro-01 (posições 1-indexed,
inclusive, conforme o documento oficial):

| Campo | Posições | Formato | Uso |
|---|---|---|---|
| TIPREG | 1-2 | `"01"` fixo | filtrar linhas de dado (ignorar header/trailer) |
| DATA_PREGAO | 3-10 | AAAAMMDD | `Data` |
| CODBDI | 11-12 | texto | `78`=CALL, `82`=PUT, `02`=lote padrão (ação) |
| CODNEG | 13-24 | texto | `Codigo_Opcao` (ou ticker da ação, pro índice) |
| TPMERC | 25-27 | número | `070`=opção de compra, `080`=opção de venda, `010`=à vista |
| NOMRES | 28-39 | texto | nome resumido do emissor — chave de casamento opção↔ação |
| PREULT | 109-121 | `(11)V99` (2 casas implícitas, sem ponto) | preço de fechamento — `Preco_Opcao` ou `Preco_Ativo` conforme o registro |
| PREOFC | 122-134 | `(11)V99` | melhor oferta de compra → `Bid` |
| PREOFV | 135-147 | `(11)V99` | melhor oferta de venda → `Ask` |
| TOTNEG | 148-152 | número | número de negócios → `Num_Negocios` |
| VOLTOT | 171-188 | `(16)V99` | volume financeiro total → `Volume` |
| PREEXE | 189-201 | `(11)V99` | preço de exercício (strike) → `Strike` |
| DATVEN | 203-210 | AAAAMMDD | vencimento → `Data_Vencimento` |

Campos com `V99`/`V06` são inteiros de largura fixa com casas decimais implícitas (sem
ponto no texto) — extrair como `int(trecho) / 100.0` (ou `/ 1_000_000` pros de 6 casas,
não usados aqui). Em Python, `linha[10:12]` dá as posições 11-12 (slice 0-indexed,
fim exclusivo) — cuidado na hora de converter posição 1-indexed inclusive do documento
pra slice Python.

## 4.2 Extensão do schema `opcoes_historico`

Adicionar colunas (nulas, `ALTER TABLE opcoes_historico ADD COLUMN ...`, aditivo — não
quebra linhas existentes da brapi):
- `Bid REAL` — `PREOFC / 100.0`
- `Ask REAL` — `PREOFV / 100.0`
- `Volume REAL` — `VOLTOT / 100.0`
- `Num_Negocios INTEGER` — `TOTNEG`

Linhas de fonte `brapi` continuam com essas colunas `NULL` (a brapi não fornece isso no
histórico). `backtest_opcoes.py` não precisa dessas colunas hoje (o backtest usa
`liq=0` fixo, documentado como limitação da fonte brapi) — ficam disponíveis pra uma
iteração futura que calibre `peso_liq` de verdade com dado real de volume.

## 5. Erros e casos vazios

- Opção sem ação à vista correspondente no mesmo dia (`NOMRES` sem match) → descarta a
  linha, não grava com `Preco_Ativo` inventado.
- Linha malformada (menos de 245 bytes, campo numérico não parseável) → pula a linha,
  loga e segue (não aborta o arquivo inteiro por uma linha ruim).
- Download falhar (rede, URL mudou) → erro claro, sem retry automático (script manual,
  rodado sob supervisão — diferente do coletor diário da brapi, que já tem
  retry/backoff pra rate limit).
- Selic ausente pra uma data específica → usa a leitura mais próxima disponível
  (mesmo espírito de `exposicao.py`: nunca inventa dado, mas também não trava por uma
  data sem leitura exata).
- Execução idempotente: rodar de novo pro mesmo ano não duplica (`ON CONFLICT
  (Codigo_Opcao, Data) DO UPDATE`, mesma convenção de `coleta_opcoes_historico.py`).

## 6. Verificação necessária ANTES de implementar o parser completo

Dois pontos que o PDF documenta mas que precisam de confirmação contra um arquivo real
(prática já estabelecida no projeto — "confirmar fontes antes de passar código"):

1. **URL de download atual.** A B3 já mudou domínio/caminho desses arquivos no
   passado; confirmar a URL vigente antes de escrever o downloader.
2. **Casamento opção↔ação por NOMRES.** Verificar contra registros reais da PETR4 (e
   idealmente mais um emissor com múltiplas classes, tipo Itaúsa/Itaú) se `NOMRES`
   bate de forma inambígua entre o registro de opção e o de ação à vista no mesmo dia,
   e se a heurística de "maior `VOLTOT` em caso de empate" resolve os casos de emissor
   com ON e PN.

Esses dois pontos são o primeiro passo do plano de implementação (spike de
verificação), antes de escrever o parser completo.

## 7. Teste

Sem framework automatizado (convenção do projeto). Dois níveis:
- **Unitário:** parser testado contra uma linha sintética de 245 bytes construída à
  mão no formato oficial (`assert` em `if __name__ == "__main__":`, mesmo padrão de
  `analises_opcoes.py`) — cobre extração de cada campo, CALL vs. PUT via CODBDI,
  linha malformada não derruba o processamento.
- **Real:** depois do parser pronto, rodar contra o arquivo de 2024 baixado de
  verdade e conferir manualmente uma série conhecida da PETR4 (comparar contra o que
  já está em `opcoes_historico` via brapi, onde os períodos se sobrepõem) antes de
  aceitar como pronto para uso no backtest.
