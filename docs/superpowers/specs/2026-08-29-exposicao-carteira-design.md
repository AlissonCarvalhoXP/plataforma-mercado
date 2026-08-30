# Camada de Sinais de Exposição da Carteira — Design

**Data:** 2026-08-29
**Status:** Aprovado para implementação (Approach 1)

## 1. Motivação

O MIH hoje coleta dados ricos (macro, debêntures, notícias, opções) mas a análise
que cruza esses dados com a carteira do usuário é rasa: `gerar_contexto_carteira()`
apenas lista posições e percentuais, sem dizer o que um movimento de mercado
significa para elas. `analises.py` tem 3 regras isoladas (dólar, Selic, debêntures)
que nunca referenciam a carteira. O resultado é uma ferramenta que ainda se parece
mais com uma "mini-Bloomberg" (mostra dados) do que com uma plataforma de apoio à
decisão (transforma dados em leitura acionável) — o objetivo declarado no
`ROADMAP.md`.

Este design cobre a primeira fatia vertical de uma camada de inteligência cruzada:
cruzar a exposição da carteira (por indexador/direção) com os movimentos macro que
o MIH já coleta, e expor isso tanto na UI (aba Resumo) quanto no briefing gerado
por IA.

**Fora de escopo neste design** (fases futuras, não decompor agora):
- Persistir histórico de sinais em tabela própria (`sinais`) para ver evolução ao
  longo do tempo.
- Integrar sinais de exposição com `alertas.py` (disparo por e-mail).
- Reorganizar a navegação/abas do `app.py` como um todo.
- Propagar um componente de "card de insight" reutilizável para todas as abas
  (Macro, Carteira, Opções).
- Sinais cruzados vindos de debêntures, notícias ou opções (este design cobre
  apenas o cruzamento carteira × indicadores macro/dólar).

## 2. Arquitetura

Novo módulo `exposicao.py`, na raiz do projeto, seguindo exatamente o padrão de
`analises.py`: funções puras, sem efeito colateral, sem `subprocess`, testáveis via
bloco `if __name__ == "__main__":`. Nenhuma tabela nova — lê o que já existe
(`carteira`, `indicadores_bcb`, `usd_brl`) e é aditivo: nenhuma assinatura de
módulo existente muda.

Dois pontos de consumo:
- **`app.py` (aba Resumo):** chama a função a cada render e usa a lista de sinais
  para desenhar o breakdown de exposição e os cards de sinal.
- **`briefing.py`:** acrescenta o texto dos sinais ao contexto que já é montado
  para a IA (mesmo ponto onde `gerar_contexto_carteira()` já é injetado), para que
  o parágrafo gerado cite a exposição real em vez de só as taxas soltas.

## 3. Modelo de sinal

Função principal:

```python
def gerar_sinais_exposicao(df_carteira, df_indicadores, df_dolar) -> list[dict]:
    ...
```

Cada sinal retornado é um dict:

```python
{
    "indexador": str,        # "CDI", "Prefixado", "IPCA", "Dólar"
    "direcao": str,          # "long" | "short"
    "valor_exposto": float,  # soma de `tamanho` da carteira nesse grupo
    "variavel_gatilho": str, # "Selic", "IPCA", "Dólar"
    "delta": float,          # variação do gatilho (última leitura vs. anterior)
    "sentido_impacto": str,  # "favoravel" | "desfavoravel"
    "texto": str,            # frase pronta para exibição/briefing
}
```

### 3.1 Lógica de cruzamento por indexador

| Indexador na carteira | Gatilho macro | Long quando gatilho sobe | Short quando gatilho sobe |
|---|---|---|---|
| CDI | Δ Selic | Favorável (renda pós-fixada rende mais) | Desfavorável |
| Prefixado | Δ Selic | Desfavorável (marcação a mercado cai com juros mais altos) | Favorável |
| IPCA | Δ IPCA | Favorável (correção monetária maior) | Desfavorável |
| Dólar | Δ USD/BRL | Favorável | Desfavorável |
| Bolsa / N/A | — | Sem indicador equivalente hoje — entra apenas no breakdown de exposição, não gera sinal direcional | — |

Ponto de modelagem central: CDI e Prefixado reagem em **sentidos opostos** ao
mesmo gatilho (Selic) — reflete a lógica clássica de tesouraria (pós-fixado vs.
prefixado). O texto do sinal deve deixar isso explícito quando ambos existem na
carteira, ex.: *"Selic subiu 0,25pp → favorece R$ 21.000 em CDI (long), pressiona
R$ 15.000 em Prefixado (long)"*.

### 3.2 Janela de comparação

`analisar_selic()` (em `analises.py`) hoje compara a leitura atual com o primeiro
registro histórico da série — pouco útil para "o que mudou agora". `exposicao.py`
não reutiliza essa lógica, nem a janela de 6 leituras de `analisar_dolar()`.

> **Revisão (2026-08-29, pós-implementação):** a versão inicial deste documento
> especificava "última leitura vs. leitura imediatamente anterior" de forma
> uniforme para Selic, IPCA e USD/BRL. Na prática, a Selic (SGS 432) é uma
> função-degrau que só muda em dias de reunião do Copom (~8x/ano) — comparar
> com a leitura imediatamente anterior fazia CDI e Prefixado ficarem `neutro`
> na quase totalidade dos dias, escondendo justamente a oposição entre eles que
> é o ponto central do design (seção 3.1). A regra foi revisada para **última
> leitura vs. última leitura DIFERENTE dela** no histórico disponível (sem
> limite de quanto tempo olhar para trás — o volume de dados é pequeno):
> - Se a série inteira disponível for igual ao valor atual (nunca mudou no
>   período coletado), não gera sinal — mesmo tratamento do caso "dados
>   insuficientes" (nunca um delta 0,0 fabricado).
> - Aplicada uniformemente a Selic, IPCA e USD/BRL: para IPCA e Dólar, que
>   raramente repetem valor exato entre leituras consecutivas, o comportamento
>   na prática não muda — a leitura "diferente mais recente" quase sempre
>   coincide com a leitura imediatamente anterior.
> - Implementação: `exposicao._ultima_variacao()`.

### 3.3 Ordenação

Os sinais são ordenados com **desfavorável primeiro**: numa mesa de tesouraria, o
que exige atenção deve aparecer no topo, não o que já está confortável.

## 4. UI — aba Resumo

Layout atual: parágrafo de IA (briefing) + destaques + 4 métricas soltas
(Selic/IPCA/IGP-M/Dólar) sem relação com a carteira.

Novo layout:
1. Briefing da IA + destaques — mantém como está.
2. **"Exposição da carteira"** — `st.bar_chart` com soma de `tamanho` por
   indexador (mesmo padrão já usado na aba Debêntures para exibição por
   indexador).
3. **"Sinais do dia"** — lista dos dicts de `gerar_sinais_exposicao()` renderizada
   como blocos compactos: indexador, valor exposto, badge favorável/desfavorável,
   texto. Ordenada conforme 3.3.

As métricas soltas de Selic/IPCA/IGP-M/Dólar saem do Resumo — continuam
disponíveis na aba Macro, que é o lugar correto para elas.

## 5. Erros e casos vazios

Mesmo padrão defensivo do restante do projeto:
- Leituras via `try/except` silencioso, com fallback para lista vazia.
- Guarda explícita por indicador (análoga a `if len(dolar) < 6` em
  `analisar_dolar()`): se não houver leitura anterior de um indicador, aquele
  indexador simplesmente não gera sinal — nunca inventa um delta de 0,0 pp.
- Carteira vazia → nenhuma exceção; UI mostra "Carteira vazia, sem sinais a
  mostrar" (mesma mensagem de vazio que `carteira_tab` já usa hoje).

## 6. Teste

Sem framework automatizado no projeto (apenas scripts manuais, ex.:
`teste_integracao.py`). `exposicao.py` segue a convenção existente: bloco
`if __name__ == "__main__":` com `assert`s cobrindo:
- Carteira vazia → lista de sinais vazia, sem exceção.
- Indexador sem leitura anterior disponível → nenhum sinal gerado para ele.
- CDI e Prefixado reagindo em sentidos opostos ao mesmo Δ Selic (caso central do
  design).

Rodado manualmente antes de plugar em `app.py`/`briefing.py`, igual já é feito em
`carteira.py` e `analises.py`.
