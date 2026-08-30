# Polimento de Tabelas e KPIs — Design

**Data:** 2026-08-29
**Status:** Aprovado para implementação

## 1. Motivação

O redesenho Terminal Cartesiano (spec anterior) entregou a identidade visual —
paleta, tipografia, navegação em rail, gráficos Plotly com tema — mas dois
pontos ainda pesam como "simplista" no feedback do usuário após o primeiro uso
real da ferramenta:

1. **Tabelas cruas** (`st.dataframe`/`st.data_editor` em Macro e Carteira):
   valores hoje chegam pré-formatados como texto (`f"R$ {x:.4f}"`), perdendo
   ordenação numérica real e o controle nativo de exibição do Streamlit.
2. **Falta de polimento geral**: os 6 `st.metric()` da página Macro são o
   widget padrão do Streamlit, sem nenhuma identidade visual própria.

Confirmado tecnicamente antes de desenhar: `st.dataframe` aceita
`column_config` (com `NumberColumn`, `DateColumn`, `SelectboxColumn`,
`ProgressColumn`, etc.) e também aceita um `pandas.Styler`, então cor
condicional por célula é possível mesmo a tabela renderizando em canvas
(onde CSS injetado não alcança — limitação já documentada na revisão final do
redesenho anterior).

**Fora de escopo** (não decompor agora):
- Nenhuma mudança em query, coleta ou regra de negócio — só apresentação.
- Só as páginas Macro e Carteira mudam — são as únicas com tabela/editor/metric
  hoje. Resumo, Notícias, Investidas, Relatórios e Opções não são tocadas.
- Sparklines inline (`column_config.LineChartColumn`) — precisariam de dado
  por linha em formato de lista, que as tabelas atuais não têm; fica para uma
  iteração futura se fizer sentido.

## 2. Componentes novos/expandidos

- **`componentes.py` (expande)** — `kpi_card(label, valor_texto, delta_texto=None, sentido=None) -> str`:
  monta o HTML de um card no estilo Terminal Cartesiano (painel com borda
  hairline, label em caixa alta `muted`, valor grande em `IBM Plex Mono`, e um
  delta opcional com glifo ▲/▼ colorido por `signal-pos`/`signal-neg`/`accent`
  — mesma linguagem visual de `badge_sinal`). Renderizado via
  `st.markdown(kpi_card(...), unsafe_allow_html=True)`.
- **`dados_app.py` (expande)** — `calcular_delta_indicador(df_indicadores, nome) -> float | None`:
  generaliza a lógica de "última leitura vs. leitura anterior distinta" (com
  dedup por data) que hoje só existe, de forma privada e específica a
  Selic/IPCA/Dólar, dentro de `exposicao.py`. Esta nova função pública em
  `dados_app.py` aceita qualquer `nome` de indicador (Selic, CDI, IPCA, IGP-M)
  — usada pelos KPIs da Macro. `exposicao.py` não muda; a duplicação de
  conceito entre os dois módulos é aceitável porque servem consumidores
  diferentes (sinais de carteira vs. exibição de indicador), mas ambos seguem
  a mesma regra de negócio (nunca inventar uma leitura quando faltar dado).
- **`tabelas.py` (novo módulo)** — mesma família de `graficos.py`/`componentes.py`:
  - `colunas_dolar() -> dict`, `colunas_debentures() -> dict`,
    `colunas_carteira() -> dict`: dicionários prontos para o parâmetro
    `column_config=` de `st.dataframe`/`st.data_editor`.
  - `progresso_prazo(data_emissao, data_vencimento, hoje=None) -> float`:
    função pura que devolve a fração (0 a 1, com clamp) do prazo da
    debênture já decorrida — usada como `ProgressColumn`.
  - `destacar_spread(df) -> pandas.io.formats.style.Styler`: aplica cor de
    fundo por linha na coluna `spread` (verde `signal_pos` se abaixo da média
    do indexador — mais atrativo —, coral `signal_neg` se acima), via
    `df.style.apply(...)`.

## 3. Onde aplica

### Macro (`paginas/macro.py`)
- Os 6 `st.metric(...)` (Selic, CDI, IPCA, IGP-M, Séries coletadas, Volume
  total) viram `st.markdown(kpi_card(...))`. Os 4 indicadores macro ganham
  delta via `calcular_delta_indicador` (formatado em p.p., mesmo padrão de
  `exposicao._formatar_delta`); "Séries coletadas"/"Volume total" ficam sem
  delta — não há uma leitura "anterior" natural para esses totais agregados.
- Tabela do dólar: `date`/`close` passam a ser valores nativos (não mais
  strings pré-formatadas) com `column_config=colunas_dolar()`.
- Tabela de debêntures: idem com `column_config=colunas_debentures()`, mais
  uma coluna nova `progresso_prazo` (via `ProgressColumn`) e o destaque
  condicional do `spread` via `destacar_spread(df)`.

### Carteira (`paginas/carteira.py`)
- `st.data_editor(...)` ganha `column_config=colunas_carteira()`:
  `direcao` e `indexador` viram `SelectboxColumn` (hoje são texto livre,
  sujeito a erro de digitação que `salvar_carteira()` já precisa normalizar);
  `tamanho` vira `NumberColumn(format="R$ %.2f")`.

## 4. Erros e testes

Mesmo padrão do resto do projeto: `tabelas.py` e as novas funções de
`dados_app.py`/`componentes.py` são funções puras, testadas com `assert` em
`if __name__ == "__main__":`. `progresso_prazo` e `calcular_delta_indicador`
são as únicas com lógica de cálculo real — cobrir explicitamente: prazo ainda
não iniciado (0), já vencido (1, com clamp), e o caso de indicador com menos
de 2 leituras distintas (retorna `None`, sem inventar delta — mesma regra já
estabelecida em `exposicao.py`). Verificação das páginas continua manual
(`streamlit run app.py`), mesma convenção já usada nas mudanças de UI
anteriores.
