# Redesenho Visual — Terminal Cartesiano — Design

**Data:** 2026-08-29
**Status:** Aprovado para implementação

## 1. Motivação

O MIH hoje usa um tema dark genérico (gradientes azul-petróleo, glow cyan) aplicado
via CSS inline em `app.py`, com gráficos nativos do Streamlit (`st.line_chart`/
`st.bar_chart`) sem controle visual real, exceto no módulo de Opções, que já usa
Plotly. O projeto tem duplo propósito — uso diário e peça de portfólio para
entrevistas em Global Markets/Tesouraria (`HANDOFF.md` §1) — então a identidade
visual importa tanto quanto a análise: precisa ler como uma ferramenta de mesa
profissional, não como um dashboard genérico de tutorial.

Este design define uma identidade visual própria — **Terminal Cartesiano** —
inspirada em terminais de mesa reais (Bloomberg/Reuters, o que a persona-alvo usa
de fato) combinado com a linguagem quantitativa do módulo de Opções (curvas,
superfícies de vol), e a aplica de forma consistente nas 7 seções da plataforma.

**Fora de escopo neste design** (decisões deliberadamente adiadas, não decompor
agora):
- Reorganizar o que vive em cada seção (ex.: fundir Macro + Debêntures numa
  página "Crédito & Taxas", cogitado no roadmap do módulo de Opções). Este design
  é estritamente visual — as 7 seções de conteúdo permanecem como são hoje,
  apenas viram itens de navegação em vez de abas.
- Rollout em fases — decidido fazer tudo numa leva só, para não conviver com duas
  linguagens visuais ao mesmo tempo.
- Qualquer alteração de lógica de negócio, queries ou cálculo (`exposicao.py`,
  `analises.py`, `carteira.py`, etc.) — o dado e as regras não mudam, só a
  apresentação.

## 2. Identidade visual — tokens

### Cor

| Token | Hex / valor | Uso |
|---|---|---|
| `bg` | `#0A0E14` | Fundo da aplicação (grafite quase-preto, não puro preto) |
| `surface` | `rgba(16,22,31,.9)` | Fundo de painéis/cards |
| `line` | `rgba(140,170,210,.16)` | Bordas de painel (hairline, 1px) |
| `line-soft` | `rgba(140,170,210,.1)` | Divisores internos (entre linhas de uma lista) |
| `text` | `#E3E9F1` | Texto primário |
| `muted` | `#8C9BB0` | Texto secundário, labels |
| `accent` | `#4FD6E8` | Cyan — marca, item ativo da navegação, série primária dos gráficos |
| `signal-pos` | `#3DDC84` | Verde — sinal favorável |
| `signal-neg` | `#FF7A59` | Coral — sinal desfavorável |

Nada de gradientes ou glow decorativo — painéis são sólidos/translúcidos com
borda hairline, sem sombra pesada nem blur decorativo. A única textura de "grade"
fica **dentro dos próprios gráficos** (eixos com linhas discretas na cor `line`),
não espalhada pela página — decisão tomada explicitamente ao revisar o mockup
(remover a grade de fundo full-page, que ficava carregada demais para uma UI
densa em números).

### Tipografia

| Papel | Fonte | Uso |
|---|---|---|
| Display | Space Grotesk (500/700) | Títulos de página, marca ("MIH ▪ MESA"), item ativo do rail |
| Corpo/UI | IBM Plex Sans (400/500/600/700) | Texto corrido, labels, botões |
| Dado | IBM Plex Mono (400/600), algarismos tabulares | **Todo número da plataforma** — métricas, tabelas, valores em cards |

O tratamento monoespaçado para números é o elemento de assinatura: colunas de
valores alinham como num terminal de verdade, com glifos direcionais (▲/▼) e cor
vindo só de `signal-pos`/`signal-neg`/`accent` conforme o caso — nunca decoração
sem função.

## 3. Arquitetura — navegação

Hoje `app.py` é um script único com `st.tabs()`. Este design migra para
**`st.navigation` + `st.Page`** (nativo do Streamlit, instalado 1.62 — bem acima
do mínimo 1.36 que introduziu a API), que renderiza a lista de páginas na
sidebar — a base do rail lateral do mockup aprovado.

Cada uma das 7 seções vira uma função de página independente, testável e lida
isoladamente, num novo pacote `paginas/`:

```
paginas/
├── resumo.py       (pagina_resumo)
├── macro.py        (pagina_macro)
├── noticias.py     (pagina_noticias)
├── investidas.py   (pagina_investidas)
├── carteira.py     (pagina_carteira)
├── relatorios.py   (pagina_relatorios)
└── opcoes.py       (pagina_opcoes — wrapper fino em torno de
                      modules/opcoes/view_opcoes.render_aba_opcoes,
                      que não muda)
```

`app.py` vira um shell fino:
1. Injeta o CSS/tema (de `tema.py`) e os imports de fonte, uma única vez.
2. Monta `pg = st.navigation([st.Page(pagina_resumo, title="Resumo", icon="📊"), ...])`
   e chama `pg.run()`.
3. Depois de `pg.run()`, renderiza o `st.chat_input` da IA — que continua
   persistente/global, fora de qualquer página, exatamente como hoje.

O bloco estático da sidebar de hoje ("Operações" + lista de bullets repetindo os
nomes das seções) é removido — fica redundante com a lista de navegação nativa.
O botão "🤖 Assistente IA" permanece na sidebar.

**Correção pós-implementação:** a posição do botão relativa à lista de páginas
não é uma escolha livre — `st.navigation` renderiza a lista de páginas em uma
posição fixa do layout da sidebar, então qualquer conteúdo adicionado antes de
`pg.run()` (como este botão) aparece **abaixo** dela, não acima, independente da
ordem das chamadas no código. A frase original desta seção ("acima da lista de
páginas") descrevia uma posição inatingível com essa API e foi corrigida aqui
após a revisão final de implementação constatar isso na renderização real do
Streamlit 1.62.

## 4. Componentes novos

- **`tema.py`** — módulo único com: dict de tokens de cor, o bloco CSS completo
  da identidade (substitui o bloco CSS atual de `app.py`), o `<link>` das 3
  fontes do Google Fonts, e um template Plotly (`plotly.graph_objects.layout.Template`)
  registrado em `plotly.io.templates["terminal_cartesiano"]` com as cores/fontes
  dos tokens — todo gráfico usa esse template por padrão, sem repetir estilo.
- **Funções de gráfico Plotly** — cada chamada nativa vira uma função pequena
  que monta uma `go.Figure`/`px` usando o template compartilhado:
  - `dolar` (linha, hoje em `st.line_chart` na aba Macro)
  - `debêntures por indexador` (barra, hoje em `st.bar_chart` na aba Macro/Debêntures)
  - `exposição por indexador` (barra, hoje em `st.bar_chart` no Resumo, vindo de
    `exposicao.resumo_exposicao_por_indexador`)
- **Helper de sinal/badge** — função única que recebe um dict de sinal (do
  formato de `exposicao.gerar_sinais_exposicao`) e devolve o markup do badge
  favorável/desfavorável/neutro, substituindo a montagem manual atual no Resumo.

## 5. Dados

Sem mudança em nenhuma query, cálculo ou regra de negócio. Muda só **onde** as
leituras rodam: com páginas de verdade, só a função da página ativa executa a
cada rerender — cada `pagina_*.py` carrega apenas os dados que usa. Leituras
compartilhadas entre páginas (indicadores, dólar) ganham `@st.cache_data` com
TTL curto (poucos minutos), evitando reconsultas desnecessárias — coisa que o
`app.py` atual não faz (hoje recarrega tudo, de todas as abas, a cada rerender,
independente de qual está aberta).

## 6. Erros e testes

Mesmo padrão defensivo de hoje (try/except por seção, mensagens de fallback
como "Rode o briefing.py..."), só realocado para dentro de cada função de
página — sem mudar a filosofia. Verificação continua manual (`streamlit run
app.py`, checar cada página visualmente) — é trabalho de UI/apresentação, sem
lógica nova para cobrir com asserts, mesma convenção já usada no projeto para
este tipo de mudança.
