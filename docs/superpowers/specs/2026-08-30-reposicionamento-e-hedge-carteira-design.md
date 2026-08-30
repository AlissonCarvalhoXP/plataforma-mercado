# Reposicionamento do MIH + Integração Carteira → Opções — Design

**Data:** 2026-08-30
**Status:** Aprovado para implementação

## 1. Motivação

O objetivo do MIH muda: deixa de ter dupla finalidade (aprendizado + peça de
portfólio para entrevistas) e passa a ser uma **ferramenta quantitativa
profissional** para uso próprio. O módulo de Opções B3 (`modules/opcoes/`) —
hoje o mais maduro analiticamente (Black-Scholes, IV/HV, score, backtest) —
passa a ser o **módulo principal neste momento**. Os demais módulos (macro,
crédito/debêntures, notícias, carteira) passam a servir explicitamente de
**base analítica** para as recomendações de Opções, em vez de serem abas
paralelas e desconectadas.

Automação de envio de ordens para corretora é uma visão de longo prazo,
**condicional ao sucesso dos backtests** — não faz parte deste design; apenas
é registrada no roadmap.

**Fora de escopo neste design:**
- Reordenar a navegação do `app.py` (qual aba vem primeiro) — não faz parte
  deste ciclo.
- Sinais de notícias ou de exposição macro (`exposicao.py`) alimentando o
  motor de Opções — ficam para uma iteração futura; este design cobre apenas
  o cruzamento carteira × Opções.
- Automação de ordens (ver acima).
- Dimensionamento fracionário de contratos ou lotes não-padrão (mini-lotes) —
  fora de escopo; usa-se sempre o lote-padrão B3 de 100 ações.

## 2. Reposicionamento (documentação)

Mudança de conteúdo, sem código:

- **`HANDOFF.md` seção 1 (Perfil do usuário):** substitui "objetivo duplo
  (aprender + portfólio para entrevistas)" por: ferramenta quantitativa para
  uso próprio na análise e recomendação de posições; Opções B3 como módulo
  principal; os demais módulos como base analítica que alimenta suas
  recomendações e o briefing.
- **`HANDOFF.md` seção 0/2 (instruções à IA / metodologia):** reduz a ênfase
  didática ("mentor que ensina passo a passo, um passo por vez, esperar
  confirmação") para um modo de entrega direta — menos explicação
  intermediária, mesma exigência de rigor técnico e de commits bem
  documentados.
- **`ROADMAP.md`:** nova "Estrela-guia": motor de recomendação quantitativa
  de Opções B3, calibrado por backtest, que cruza carteira (e, no futuro,
  macro/crédito/notícias) para sugerir e dimensionar estruturas de hedge/
  renda. Adiciona uma seção "Visão futura condicional" registrando a
  automação de envio de ordens, dependente do sucesso dos backtests.
- **`modules/opcoes/ROADMAP_MIH_Opcoes_Handoff.md` seção 8 (decisões em
  aberto):** fecha a decisão "plano brapi" como "gratuito por agora,
  reavaliar Pro conforme necessidade".

## 3. Integração: Carteira → universo de coleta

Hoje `coleta_opcoes.py` coleta um universo fixo (`ATIVOS_PADRAO = ["PETR4"]`).
Nova função `ativos_da_carteira()`:
- Lê a tabela `carteira` (via `from db import engine` — primeiro ponto em que
  o módulo de Opções deixa de ser isolado do resto do MIH e passa a ler uma
  tabela do "core"; decisão deliberada, coerente com o novo objetivo do
  projeto).
- Filtra `ativo` por um padrão de ticker B3 (regex `^[A-Z]{4}\d{1,2}$`, ex.:
  `PETR4`, `ITUB4`) — não depende do campo `indexador` estar exatamente como
  `"Bolsa"`, porque a carteira real já diverge do enum documentado em
  `carteira.py` (hoje tem `"Ibov"`).
- Retorna a lista de tickers únicos encontrados.

`main()` em `coleta_opcoes.py` passa a coletar `ativos_da_carteira() ∪
ATIVOS_PADRAO` (união, sem duplicatas), em vez de só `ATIVOS_PADRAO`. O loop
de coleta já trata falha por ativo individualmente (`except Exception`) — um
ticker sem plano Pro da brapi simplesmente falha e loga, sem interromper os
demais. Nenhuma mudança na assinatura de `coletar_ativo()`.

**Na UI (`paginas/opcoes.py` / `view_opcoes.py`):** para um ticker que está na
carteira mas não tem dados de opções coletados (sandbox brapi só cobre
PETR4), mostra uma nota curta — "sem dados de opções disponíveis para
`<ticker>` (requer plano Pro da brapi)" — em vez de omitir silenciosamente ou
quebrar.

## 4. Integração: sugestão de hedge dimensionada

**O screener genérico continua exatamente como está hoje: aponta
oportunidades (`COMPRAR_VOL`/`VENDER_VOL`) em qualquer ativo coletado, com ou
sem posição na carteira — não é substituído nem faz gate por carteira.** A
sugestão de hedge é uma seção nova e aditiva, específica para quem já tem uma
posição.

Nova função em `modules/opcoes/analises_opcoes.py`:

```python
def sugerir_hedge(posicao: dict, ranking: list[dict], spot: float,
                   regime: str) -> dict | None:
    ...
```

- `posicao`: uma linha da carteira (`ativo`, `direcao`, `tamanho` em R$).
- `ranking`: saída de `analisar()` já calculada para esse `Ativo_Objeto`.
- `spot`, `regime`: já disponíveis (`underlying["Spot"]`,
  `regime_volatilidade()`).

**Tipo de estrutura** (cruza direção da posição × regime de vol):

| Direção | Regime ALTA (vol cara) | Regime BAIXA/NEUTRA (vol barata) |
|---|---|---|
| long | Venda coberta de CALL (monetiza prêmio caro) | Proteção via compra de PUT (barata) |
| short | Venda coberta de PUT (monetiza prêmio caro) | Proteção via compra de CALL (barata) |

**Escolha da série:** filtra o `ranking` já calculado por `Tipo`
(CALL/PUT conforme a estrutura) e `Moneyness` (OTM para venda coberta e para
proteção), pega o melhor `Score` — reaproveita o motor de ranking existente,
não introduz novo critério de seleção de strike.

**Dimensionamento:** `tamanho` na carteira é valor em R$, não quantidade de
ações. `quantidade_acoes = tamanho / spot`; `contratos =
int(quantidade_acoes // 100)` (lote-padrão B3 = 100 ações). Se `contratos ==
0` (posição menor que 1 lote-padrão), a função não sugere 0 contratos —
retorna uma observação explícita ("posição de R$ X é menor que 1 lote-padrão
de 100 ações ao preço atual — hedge via opções não é viável neste tamanho").

**Saída:** dict estruturado, mesmo padrão de `exposicao.py` (campos +
`texto` pronto para exibição): `{ativo, direcao_posicao, tipo_estrutura,
codigo_opcao_sugerida, contratos, texto}`. Toda saída de
`sugerir_hedge()` inclui o disclaimer padrão do módulo ("apoio à decisão e
estudo quantitativo — NÃO constitui recomendação de investimento"), reforçado
aqui por ser mais acionável (tipo + série + quantidade) que o screener
genérico.

Se `posicao["ativo"]` não tiver dados de opções coletados (ver seção 3), a
função retorna `None` — a UI trata isso mostrando a nota de "sem dados
disponíveis" da seção 3, não uma mensagem duplicada.

Plugado em `paginas/opcoes.py` como nova seção **"Sugestões de hedge para sua
carteira"**, abaixo do ranking/screener existente (que continua inalterado).

## 5. Erros e casos vazios

- Carteira sem nenhuma posição em ação reconhecida pelo regex → seção de
  hedge mostra "nenhuma posição em ações reconhecida na carteira" (não
  quebra, não afeta o screener genérico).
- Ticker da carteira sem dados de opções coletados → nota de "sem dados
  disponíveis" (seção 3), `sugerir_hedge()` retorna `None` para essa posição.
- Posição menor que 1 lote-padrão → observação explícita, sem sugestão de 0
  contratos (seção 4).
- Falha de coleta em um ticker específico (brapi sem plano Pro, rate limit)
  → já tratado pelo `except Exception` existente em `main()`; não interrompe
  os demais tickers.

## 6. Teste

Sem framework automatizado (convenção do projeto): `assert`s em
`if __name__ == "__main__":`, mesmo padrão de `exposicao.py`,
`analises.py`, `carteira.py`. Casos mínimos:
- `ativos_da_carteira()`: reconhece tickers válidos, ignora `"CDB Banco X"` /
  `"USD/BRL"` / indexadores não-ação, deduplica.
- `sugerir_hedge()`: as 4 combinações direção × regime da tabela da seção 4
  produzem o tipo de estrutura correto; posição menor que 1 lote-padrão
  retorna a observação (não 0 contratos); ticker sem ranking disponível
  retorna `None`.

## 7. Documentação (seção 2 deste design)

Edições de conteúdo em `HANDOFF.md`, `ROADMAP.md` e
`modules/opcoes/ROADMAP_MIH_Opcoes_Handoff.md` — sem código, sem teste
automatizado; verificação é leitura do texto final.
