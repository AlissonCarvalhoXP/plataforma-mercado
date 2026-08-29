# Redesenho Visual Terminal Cartesiano Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar ao MIH uma identidade visual própria ("Terminal Cartesiano") consistente nas 7 seções da plataforma, migrando de abas horizontais para navegação em rail lateral (`st.navigation`/`st.Page`) e de gráficos nativos do Streamlit para Plotly com um template compartilhado.

**Architecture:** `app.py` vira um shell fino (tema + navegação + assistente de IA persistente). Cada seção de conteúdo vira uma função de página isolada em `paginas/`. Módulos novos e pequenos (`tema.py`, `dados_app.py`, `formatacao.py`, `graficos.py`, `componentes.py`) concentram tema, dados cacheados, formatação, gráficos e o badge de sinal — cada um com responsabilidade única, reaproveitado pelas páginas.

**Tech Stack:** Python, Streamlit 1.62 (`st.navigation`/`st.Page`, `st.cache_data`), Plotly (`graph_objects`), pandas, SQLAlchemy.

**Spec:** [docs/superpowers/specs/2026-08-29-redesign-visual-terminal-cartesiano-design.md](../specs/2026-08-29-redesign-visual-terminal-cartesiano-design.md)

## Global Constraints

- Mudança estritamente visual/estrutural: nenhuma query, cálculo ou regra de negócio muda (`exposicao.py`, `analises.py`, `carteira.py`, `investidas.py`, `relatorios.py` continuam exatamente como estão).
- As 7 seções de conteúdo permanecem as mesmas — viram itens de navegação, não são reorganizadas nem fundidas.
- Paleta e tipografia exatas do spec (seção 2): `bg #0A0E14`, `surface rgba(16,22,31,.9)`, `line rgba(140,170,210,.16)`, `line_soft rgba(140,170,210,.1)`, `text #E3E9F1`, `muted #8C9BB0`, `accent #4FD6E8`, `signal_pos #3DDC84`, `signal_neg #FF7A59`. Fontes: Space Grotesk (display), IBM Plex Sans (corpo/UI), IBM Plex Mono (todo número, tabular).
- Sem grade de fundo full-page (removida explicitamente pelo usuário) — a única "grade" fica dentro dos próprios gráficos (eixos com linhas discretas).
- Sem framework de teste automatizado no projeto — convenção é `assert` em bloco `if __name__ == "__main__":`, igual já usado em `exposicao.py`/`analises.py`/`carteira.py`.
- Verificação de páginas/navegação é manual (`streamlit run app.py`) — é trabalho de UI, sem como cobrir renderização real com asserts.

---

## Task 1: `tema.py` — tokens de cor, CSS e template Plotly

**Files:**
- Create: `tema.py`

**Interfaces:**
- Produces: `CORES: dict` (chaves: `bg, surface, line, line_soft, text, muted, accent, signal_pos, signal_neg`), `NOME_TEMPLATE_PLOTLY: str` (valor `"terminal_cartesiano"`), `aplicar_tema() -> None` (injeta o CSS via `st.markdown`).
- Ao ser importado, registra `NOME_TEMPLATE_PLOTLY` em `plotly.io.templates` — qualquer módulo que importar `tema` (ou que importe `graficos.py`, que por sua vez importa `tema`) já tem o template disponível.

- [ ] **Step 1: Escrever o teste (bloco de asserts) e o esqueleto do módulo**

Criar `tema.py`:

```python
"""
tema.py - Identidade visual "Terminal Cartesiano": tokens de cor, CSS da
aplicacao e template Plotly compartilhado. Ver docs/superpowers/specs/
2026-08-29-redesign-visual-terminal-cartesiano-design.md secao 2.
"""
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

CORES = {
    "bg": "#0A0E14",
    "surface": "rgba(16,22,31,.9)",
    "line": "rgba(140,170,210,.16)",
    "line_soft": "rgba(140,170,210,.1)",
    "text": "#E3E9F1",
    "muted": "#8C9BB0",
    "accent": "#4FD6E8",
    "signal_pos": "#3DDC84",
    "signal_neg": "#FF7A59",
}

NOME_TEMPLATE_PLOTLY = "terminal_cartesiano"

CSS = f"""
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap">
<style>
    :root {{
        --bg: {CORES['bg']};
        --surface: {CORES['surface']};
        --line: {CORES['line']};
        --line-soft: {CORES['line_soft']};
        --text: {CORES['text']};
        --muted: {CORES['muted']};
        --accent: {CORES['accent']};
        --signal-pos: {CORES['signal_pos']};
        --signal-neg: {CORES['signal_neg']};
    }}
    html, body, [data-testid="stAppViewContainer"] {{
        background: var(--bg);
        color: var(--text);
        font-family: 'IBM Plex Sans', system-ui, sans-serif;
    }}
    h1, h2, h3, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {{
        font-family: 'Space Grotesk', sans-serif;
        letter-spacing: 0.01em;
    }}
    [data-testid="stMetricValue"], [data-testid="stDataFrame"], code {{
        font-family: 'IBM Plex Mono', 'Consolas', monospace;
    }}
    [data-testid="stSidebar"] {{
        background: var(--bg);
        border-right: 1px solid var(--line);
    }}
    [data-testid="stSidebarNav"] li a {{
        font-family: 'IBM Plex Sans', sans-serif;
        color: var(--muted);
    }}
    [data-testid="stSidebarNav"] li a[aria-current="page"] {{
        color: var(--text);
        font-weight: 600;
        border-left: 2px solid var(--accent);
        background: rgba(79, 214, 232, 0.06);
    }}
    div[data-testid="stVerticalBlockBorderWrapper"],
    .element-container > div > div {{
        background: transparent;
    }}
    [data-testid="stMetric"] {{
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 0.75rem 1rem;
    }}
    .stButton > button, .stDownloadButton > button {{
        border-radius: 6px;
        border: 1px solid var(--line);
        background: var(--surface);
        color: var(--text);
        font-family: 'IBM Plex Sans', sans-serif;
        transition: border-color 0.15s ease;
    }}
    .stButton > button:hover, .stDownloadButton > button:hover {{
        border-color: var(--accent);
    }}
    .stAlert {{
        background: var(--surface);
        border: 1px solid var(--line);
        border-left: 3px solid var(--accent);
        color: var(--text);
    }}
    .topbar {{
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 10px;
        padding: 1.1rem 1.3rem;
        margin-bottom: 1rem;
    }}
    .topbar h1 {{
        margin: 0;
        font-size: 1.9rem;
        font-weight: 700;
    }}
    .topbar p {{
        margin: 0.25rem 0 0;
        color: var(--muted);
    }}
    .status-pill {{
        display: inline-block;
        border: 1px solid rgba(79, 214, 232, 0.35);
        background: rgba(79, 214, 232, 0.08);
        color: var(--accent);
        border-radius: 999px;
        padding: 0.2rem 0.7rem;
        font-size: 0.72rem;
        font-weight: 600;
        margin-top: 0.6rem;
    }}
</style>
"""


def aplicar_tema():
    """Injeta o CSS da identidade Terminal Cartesiano na pagina atual."""
    st.markdown(CSS, unsafe_allow_html=True)


def _registrar_template_plotly():
    """Registra o template Plotly compartilhado (chamado na importacao do modulo)."""
    template = go.layout.Template()
    template.layout.paper_bgcolor = "rgba(0,0,0,0)"
    template.layout.plot_bgcolor = "rgba(0,0,0,0)"
    template.layout.font = dict(family="IBM Plex Sans, sans-serif", color=CORES["text"], size=13)
    template.layout.colorway = [CORES["accent"], CORES["signal_pos"], CORES["signal_neg"], CORES["muted"]]
    template.layout.xaxis = dict(
        gridcolor=CORES["line_soft"], linecolor=CORES["line"], tickfont=dict(family="IBM Plex Mono, monospace")
    )
    template.layout.yaxis = dict(
        gridcolor=CORES["line_soft"], linecolor=CORES["line"], tickfont=dict(family="IBM Plex Mono, monospace")
    )
    template.layout.margin = dict(l=10, r=10, t=30, b=10)
    pio.templates[NOME_TEMPLATE_PLOTLY] = template


_registrar_template_plotly()


if __name__ == "__main__":
    assert NOME_TEMPLATE_PLOTLY in pio.templates, "template Plotly nao foi registrado"
    assert set(CORES.keys()) == {
        "bg", "surface", "line", "line_soft", "text", "muted", "accent", "signal_pos", "signal_neg",
    }
    print("[OK] Caso 1: template Plotly registrado em pio.templates.")

    template_registrado = pio.templates[NOME_TEMPLATE_PLOTLY]
    assert CORES["accent"] in template_registrado.layout.colorway
    assert CORES["signal_pos"] in template_registrado.layout.colorway
    assert CORES["signal_neg"] in template_registrado.layout.colorway
    print("[OK] Caso 2: colorway do template usa os tokens de sinal/accent.")

    assert CORES["accent"] in CSS
    assert CORES["bg"] in CSS
    assert "Space Grotesk" in CSS and "IBM Plex Mono" in CSS and "IBM Plex Sans" in CSS
    print("[OK] Caso 3: CSS referencia os tokens de cor e as 3 fontes da identidade.")

    print("\nTodos os casos passaram.")
```

- [ ] **Step 2: Rodar para confirmar**

Run: `python tema.py`
Expected: as 3 linhas `[OK] Caso N: ...` impressas em ordem, seguidas de `Todos os casos passaram.`, sem traceback. (Pode aparecer um `WARNING streamlit...missing ScriptRunContext` no console — é esperado ao importar `streamlit` fora de `streamlit run` e não indica falha.)

- [ ] **Step 3: Commit**

```bash
git add tema.py
git commit -m "feat: adicionar tema.py com tokens Terminal Cartesiano e template Plotly"
```

---

## Task 2: `dados_app.py` e `formatacao.py` — dados compartilhados e formatação

**Files:**
- Create: `dados_app.py`
- Create: `formatacao.py`

**Interfaces:**
- Produces (`formatacao.py`): `formatar_data_br(data) -> str`, `formatar_moeda(valor) -> str`.
- Produces (`dados_app.py`): `carregar_indicadores() -> pd.DataFrame` (cacheado), `carregar_dolar() -> pd.DataFrame` (cacheado), `carregar_noticias() -> pd.DataFrame` (cacheado), `carregar_debentures() -> pd.DataFrame` (cacheado, já com o merge series+ofertas e a coluna `link_sre`), `carregar_carteira() -> pd.DataFrame` (cacheado), `invalidar_cache_carteira() -> None`, `normalizar_indicador(valor) -> str`, `ultimo_valor(df_indicadores: pd.DataFrame, nome: str) -> float`.
- Consumes: `db.engine`, `carteira.ler_carteira` (import local dentro de `carregar_carteira`, mesmo padrão de import tardio já usado em `app.py` hoje).

- [ ] **Step 1: Escrever o teste (bloco de asserts) e o esqueleto de `formatacao.py`**

Criar `formatacao.py`:

```python
"""
formatacao.py - Formatacao BR de datas e valores monetarios, compartilhada
entre paginas. Extraido de app.py sem mudanca de comportamento.
"""
import pandas as pd


def formatar_data_br(data):
    if pd.isna(data):
        return ""
    if isinstance(data, str):
        data = pd.to_datetime(data)
    return data.strftime("%d/%m/%Y")


def formatar_moeda(valor):
    if pd.isna(valor):
        return ""
    return f"R$ {valor:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


if __name__ == "__main__":
    import datetime

    assert formatar_data_br(datetime.datetime(2026, 8, 29)) == "29/08/2026"
    assert formatar_data_br("2026-08-29") == "29/08/2026"
    assert formatar_data_br(None) == ""
    print("[OK] Caso 1: formatar_data_br cobre datetime, string e None.")

    assert formatar_moeda(1234.5) == "R$ 1.234,50"
    assert formatar_moeda(None) == ""
    print("[OK] Caso 2: formatar_moeda cobre valor normal e None.")

    print("\nTodos os casos passaram.")
```

Criar `dados_app.py`:

```python
"""
dados_app.py - Leituras de banco compartilhadas entre paginas, com
st.cache_data para nao reconsultar a cada troca de pagina. ultimo_valor
tambem vive aqui, pois opera sobre o DataFrame que este modulo carrega.
"""
import re

import pandas as pd
import streamlit as st

from db import engine

TTL_CACHE_SEGUNDOS = 300  # 5 minutos


@st.cache_data(ttl=TTL_CACHE_SEGUNDOS)
def carregar_indicadores():
    try:
        return pd.read_sql("SELECT * FROM indicadores_bcb", engine)
    except Exception:
        return pd.DataFrame(columns=["data", "valor", "indicador"])


@st.cache_data(ttl=TTL_CACHE_SEGUNDOS)
def carregar_dolar():
    try:
        return pd.read_sql("SELECT * FROM usd_brl ORDER BY date", engine)
    except Exception:
        return pd.DataFrame(columns=["date", "close"])


@st.cache_data(ttl=TTL_CACHE_SEGUNDOS)
def carregar_noticias():
    try:
        return pd.read_sql("SELECT titulo, link, data, categoria FROM noticias", engine)
    except Exception:
        return pd.DataFrame(columns=["titulo", "link", "data", "categoria"])


@st.cache_data(ttl=TTL_CACHE_SEGUNDOS)
def carregar_debentures():
    try:
        series = pd.read_sql("SELECT * FROM debentures_series", engine)
        ofertas = pd.read_sql(
            """
            SELECT numero_requerimento, nome_emissor, cnpj_emissor, emissao,
                  data_requerimento, data_encerramento, valor_total_registrado,
                  nome_lider, agente_fiduciario, titulo_incentivado
            FROM debentures
            """,
            engine,
        )
        deb = series.merge(ofertas, on="numero_requerimento", how="left")
        deb["link_sre"] = "https://web.cvm.gov.br/sre-publico-cvm/#/oferta-publica/" + deb["numero_requerimento"].astype(str)
        return deb
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=TTL_CACHE_SEGUNDOS)
def carregar_carteira():
    from carteira import ler_carteira

    try:
        return ler_carteira()
    except Exception:
        return pd.DataFrame(columns=["id", "ativo", "descricao", "direcao", "indexador", "tamanho"])


def invalidar_cache_carteira():
    """Chamar logo apos salvar a carteira, para a proxima leitura nao vir do cache antigo."""
    carregar_carteira.clear()


def normalizar_indicador(valor):
    if pd.isna(valor):
        return ""
    texto = str(valor).lower().strip()
    texto = re.sub(r"[^a-z0-9]", "", texto)
    return texto


def ultimo_valor(df_indicadores, nome):
    chave = normalizar_indicador(nome)
    serie = df_indicadores[df_indicadores["indicador"].map(normalizar_indicador) == chave]
    if serie.empty:
        return 0.0
    return float(serie["valor"].iloc[-1])


if __name__ == "__main__":
    df_ind = pd.DataFrame({
        "indicador": ["Selic", "Selic", "IGP-M"],
        "data": ["2026-01-01", "2026-01-02", "2026-01-01"],
        "valor": [10.0, 10.5, 0.3],
    })
    assert ultimo_valor(df_ind, "Selic") == 10.5
    assert ultimo_valor(df_ind, "IGP-M") == 0.3
    assert ultimo_valor(df_ind, "IPCA") == 0.0
    print("[OK] Caso 1: ultimo_valor encontra a ultima leitura por indicador normalizado.")

    assert normalizar_indicador("IGP-M") == "igpm"
    assert normalizar_indicador(None) == ""
    print("[OK] Caso 2: normalizar_indicador remove acentuacao/pontuacao e trata None.")

    print("\nTodos os casos passaram.")
```

- [ ] **Step 2: Rodar para confirmar**

Run: `python formatacao.py`
Expected: `[OK] Caso 1...`, `[OK] Caso 2...`, `Todos os casos passaram.`, sem traceback.

Run: `python dados_app.py`
Expected: `[OK] Caso 1...`, `[OK] Caso 2...`, `Todos os casos passaram.`, sem traceback (avisos de `ScriptRunContext`/`No runtime found` são esperados e não indicam falha).

- [ ] **Step 3: Verificar os carregadores cacheados contra o banco real**

Run:
```bash
python -c "
from dados_app import carregar_indicadores, carregar_dolar, carregar_noticias, carregar_debentures, carregar_carteira
for fn in [carregar_indicadores, carregar_dolar, carregar_noticias, carregar_debentures, carregar_carteira]:
    df = fn()
    print(fn.__name__, df.shape)
"
```
Expected: 5 linhas com nome da função e formato `(linhas, colunas)`, sem traceback.

- [ ] **Step 4: Commit**

```bash
git add dados_app.py formatacao.py
git commit -m "feat: extrair dados_app.py e formatacao.py de app.py"
```

---

## Task 3: `graficos.py` — figuras Plotly compartilhadas

**Files:**
- Create: `graficos.py`

**Interfaces:**
- Consumes: `tema.NOME_TEMPLATE_PLOTLY` (Task 1).
- Produces: `grafico_linha(df: pd.DataFrame, x: str, y: str, titulo: str | None = None) -> plotly.graph_objects.Figure`, `grafico_barra(serie: pd.Series, titulo: str | None = None) -> plotly.graph_objects.Figure`.

- [ ] **Step 1: Escrever o teste (bloco de asserts) e o esqueleto do módulo**

Criar `graficos.py`:

```python
"""
graficos.py - Funcoes que montam figuras Plotly usando o template
compartilhado de tema.py. Nao leem banco - recebem os dados prontos
(DataFrame/Series) e devolvem a figura.
"""
import plotly.graph_objects as go

from tema import NOME_TEMPLATE_PLOTLY


def grafico_linha(df, x, y, titulo=None):
    """Grafico de linha generico (usado hoje para USD/BRL)."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df[x], y=df[y], mode="lines"))
    fig.update_layout(template=NOME_TEMPLATE_PLOTLY, title=titulo, height=320)
    return fig


def grafico_barra(serie, titulo=None):
    """Grafico de barra generico a partir de uma pd.Series (indice=categoria,
    valor=numero) - usado para exposicao por indexador e emissoes por indexador."""
    fig = go.Figure()
    fig.add_trace(go.Bar(x=serie.index.astype(str), y=serie.values))
    fig.update_layout(template=NOME_TEMPLATE_PLOTLY, title=titulo, height=320)
    return fig


if __name__ == "__main__":
    import pandas as pd

    df_linha = pd.DataFrame({"date": ["2026-01-01", "2026-01-02"], "close": [5.1, 5.2]})
    fig1 = grafico_linha(df_linha, "date", "close", titulo="USD/BRL")
    assert isinstance(fig1, go.Figure)
    assert fig1.layout.title.text == "USD/BRL"
    assert list(fig1.data[0].y) == [5.1, 5.2]
    print("[OK] Caso 1: grafico_linha monta uma go.Figure com os dados corretos.")

    serie = pd.Series({"CDI": 10, "IPCA": 4})
    fig2 = grafico_barra(serie, titulo="Exposicao")
    assert isinstance(fig2, go.Figure)
    assert list(fig2.data[0].x) == ["CDI", "IPCA"]
    assert list(fig2.data[0].y) == [10, 4]
    print("[OK] Caso 2: grafico_barra usa o indice da serie no eixo x.")

    from tema import CORES
    assert CORES["accent"] in fig2.layout.template.layout.colorway
    print("[OK] Caso 3: figura usa o template Terminal Cartesiano (colorway com o accent).")

    print("\nTodos os casos passaram.")
```

- [ ] **Step 2: Rodar para confirmar**

Run: `python graficos.py`
Expected: `[OK] Caso 1...`, `[OK] Caso 2...`, `[OK] Caso 3...`, `Todos os casos passaram.`, sem traceback.

- [ ] **Step 3: Commit**

```bash
git add graficos.py
git commit -m "feat: adicionar graficos.py com figuras Plotly compartilhadas"
```

---

## Task 4: `componentes.py` — badge de sinal

**Files:**
- Create: `componentes.py`

**Interfaces:**
- Consumes: dict de sinal no formato de `exposicao.gerar_sinais_exposicao` (chaves `sentido_impacto`, `texto`).
- Produces: `badge_sinal(sinal: dict) -> str`.

- [ ] **Step 1: Escrever o teste (bloco de asserts) e o esqueleto do módulo**

Criar `componentes.py`:

```python
"""
componentes.py - Helpers de apresentacao reutilizaveis entre paginas.
Funcoes puras (recebem dados, devolvem string) - sem leitura de banco
nem import de streamlit.
"""

_BADGES = {"desfavoravel": "🔴", "favoravel": "🟢", "neutro": "⚪"}


def badge_sinal(sinal):
    """Formata um dict de sinal (do formato de exposicao.gerar_sinais_exposicao)
    como uma linha de markdown com o badge de cor correspondente."""
    marcador = _BADGES[sinal["sentido_impacto"]]
    return f"{marcador} {sinal['texto']}"


if __name__ == "__main__":
    sinal_fav = {"sentido_impacto": "favoravel", "texto": "Dólar variou +R$ 0,04 -> favorece R$ 1.000,00 em Dólar (long)"}
    assert badge_sinal(sinal_fav) == "🟢 Dólar variou +R$ 0,04 -> favorece R$ 1.000,00 em Dólar (long)"
    print("[OK] Caso 1: badge_sinal formata sinal favoravel.")

    sinal_desf = {"sentido_impacto": "desfavoravel", "texto": "Selic variou +0.25 p.p. -> pressiona R$ 5.000,00 em Prefixado (long)"}
    assert badge_sinal(sinal_desf) == "🔴 Selic variou +0.25 p.p. -> pressiona R$ 5.000,00 em Prefixado (long)"
    print("[OK] Caso 2: badge_sinal formata sinal desfavoravel.")

    sinal_neutro = {"sentido_impacto": "neutro", "texto": "Selic nao variou -> nao afeta R$ 2.000,00 em CDI (long)"}
    assert badge_sinal(sinal_neutro) == "⚪ Selic nao variou -> nao afeta R$ 2.000,00 em CDI (long)"
    print("[OK] Caso 3: badge_sinal formata sinal neutro.")

    print("\nTodos os casos passaram.")
```

- [ ] **Step 2: Rodar para confirmar**

Run: `python componentes.py`
Expected: `[OK] Caso 1...`, `[OK] Caso 2...`, `[OK] Caso 3...`, `Todos os casos passaram.`, sem traceback.

- [ ] **Step 3: Commit**

```bash
git add componentes.py
git commit -m "feat: adicionar componentes.py com badge_sinal"
```

---

## Task 5: `paginas/resumo.py`

**Files:**
- Create: `paginas/__init__.py` (vazio — mesmo padrão de `modules/opcoes/__init__.py`)
- Create: `paginas/resumo.py`

**Interfaces:**
- Consumes: `dados_app.carregar_carteira`, `dados_app.carregar_indicadores`, `dados_app.carregar_dolar` (Task 2); `graficos.grafico_barra` (Task 3); `componentes.badge_sinal` (Task 4); `exposicao.gerar_sinais_exposicao`, `exposicao.resumo_exposicao_por_indexador` (já existentes); `db.engine`.
- Produces: `pagina_resumo() -> None` (função de página, sem argumentos, chamada por `st.Page`).

- [ ] **Step 1: Criar `paginas/__init__.py`**

Arquivo vazio.

- [ ] **Step 2: Criar `paginas/resumo.py`**

```python
"""
paginas/resumo.py - Pagina "Resumo": briefing do dia, destaques, exposicao
da carteira e sinais do dia. Extraida de app.py sem mudanca de logica,
so trocando st.bar_chart por graficos.grafico_barra e o badge manual por
componentes.badge_sinal.
"""
import pandas as pd
import streamlit as st

from componentes import badge_sinal
from dados_app import carregar_carteira, carregar_dolar, carregar_indicadores
from db import engine
from exposicao import gerar_sinais_exposicao, resumo_exposicao_por_indexador
from graficos import grafico_barra


def pagina_resumo():
    st.subheader("Resumo executivo")

    try:
        briefing = pd.read_sql("SELECT texto FROM briefing", engine)
        if not briefing.empty:
            st.info(briefing["texto"].iloc[0])
    except Exception:
        st.write("Rode o briefing.py para gerar o comentário do dia.")

    try:
        destaques = pd.read_sql("SELECT texto FROM destaques", engine)
        if not destaques.empty:
            st.markdown("**⚡ Destaques do dia**")
            st.markdown(destaques["texto"].iloc[0])
    except Exception:
        pass

    carteira_df = carregar_carteira()
    ind = carregar_indicadores()
    dolar = carregar_dolar()

    st.markdown("**Exposição da carteira**")
    resumo_exposicao = resumo_exposicao_por_indexador(carteira_df)
    if resumo_exposicao.empty:
        st.info("Carteira vazia, sem sinais a mostrar.")
    else:
        st.plotly_chart(grafico_barra(resumo_exposicao), use_container_width=True)

        st.markdown("**Sinais do dia**")
        sinais = gerar_sinais_exposicao(carteira_df, ind, dolar)
        if not sinais:
            st.caption("Sem sinais no momento (dados insuficientes para calcular variação).")
        else:
            for sinal in sinais:
                st.markdown(badge_sinal(sinal))
```

- [ ] **Step 3: Verificar com dados reais**

Run: `python -c "from paginas.resumo import pagina_resumo; pagina_resumo()"`
Expected: nenhum traceback (avisos de `ScriptRunContext` são esperados fora de `streamlit run`).

- [ ] **Step 4: Commit**

```bash
git add paginas/__init__.py paginas/resumo.py
git commit -m "feat: extrair pagina Resumo para paginas/resumo.py"
```

---

## Task 6: `paginas/macro.py`

**Files:**
- Create: `paginas/macro.py`

**Interfaces:**
- Consumes: `dados_app.carregar_debentures`, `dados_app.carregar_dolar`, `dados_app.carregar_indicadores`, `dados_app.ultimo_valor` (Task 2); `formatacao.formatar_data_br`, `formatacao.formatar_moeda` (Task 2); `graficos.grafico_barra`, `graficos.grafico_linha` (Task 3).
- Produces: `pagina_macro() -> None`.

- [ ] **Step 1: Criar `paginas/macro.py`**

```python
"""
paginas/macro.py - Pagina "Macro": indicadores do BCB, dolar e debentures.
Extraida de app.py sem mudanca de logica, so trocando st.line_chart/
st.bar_chart por graficos.grafico_linha/graficos.grafico_barra.
"""
import pandas as pd
import streamlit as st

from dados_app import carregar_debentures, carregar_dolar, carregar_indicadores, ultimo_valor
from formatacao import formatar_data_br, formatar_moeda
from graficos import grafico_barra, grafico_linha


def pagina_macro():
    st.subheader("Indicadores macro")

    ind = carregar_indicadores()
    dolar = carregar_dolar()
    deb = carregar_debentures()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Selic (% a.a.)", round(ultimo_valor(ind, "Selic"), 2))
    c2.metric("CDI (% a.d.)", round(ultimo_valor(ind, "CDI"), 4))
    c3.metric("IPCA (% mes)", round(ultimo_valor(ind, "IPCA"), 2))
    c4.metric("IGP-M (% mes)", round(ultimo_valor(ind, "IGP-M"), 2))

    st.subheader("Dólar (USD/BRL)")
    if not dolar.empty:
        st.plotly_chart(grafico_linha(dolar, "date", "close", titulo="USD/BRL"), use_container_width=True)
        dolar_display = dolar.copy()
        dolar_display["date"] = dolar_display["date"].apply(formatar_data_br)
        dolar_display["close"] = dolar_display["close"].apply(lambda x: f"R$ {x:.4f}")
        st.dataframe(dolar_display, use_container_width=True, hide_index=True)
    else:
        st.info("Sem dados de dólar disponíveis.")

    st.subheader("Debêntures")
    if not deb.empty:
        d1, d2 = st.columns(2)
        d1.metric("Séries coletadas", len(deb))
        d2.metric("Volume total (R$ bi)", round(deb["valor_serie"].sum() / 1e9, 2))
        st.write("**Emissões por indexador**")
        st.plotly_chart(grafico_barra(deb["indexador"].value_counts()), use_container_width=True)
        deb_display = deb[[
            "nome_emissor", "serie", "indexador", "spread", "valor_serie", "prazo_anos",
            "data_emissao", "data_vencimento", "rating", "titulo_incentivado",
            "nome_lider", "agente_fiduciario", "data_encerramento", "link_sre",
        ]].copy()
        for coluna in ["data_emissao", "data_vencimento", "data_encerramento"]:
            if coluna in deb_display.columns:
                deb_display[coluna] = deb_display[coluna].apply(formatar_data_br)
        if "valor_serie" in deb_display.columns:
            deb_display["valor_serie"] = deb_display["valor_serie"].apply(lambda x: formatar_moeda(x / 1e6) if pd.notna(x) else "")
        if "spread" in deb_display.columns:
            deb_display["spread"] = deb_display["spread"].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "")
        st.dataframe(deb_display, use_container_width=True, hide_index=True)
    else:
        st.info("Sem dados de debêntures disponíveis.")
```

- [ ] **Step 2: Verificar com dados reais**

Run: `python -c "from paginas.macro import pagina_macro; pagina_macro()"`
Expected: nenhum traceback.

- [ ] **Step 3: Commit**

```bash
git add paginas/macro.py
git commit -m "feat: extrair pagina Macro para paginas/macro.py"
```

---

## Task 7: Páginas sem gráfico — Notícias, Investidas, Carteira, Relatórios, Opções

**Files:**
- Create: `paginas/noticias.py`
- Create: `paginas/investidas.py`
- Create: `paginas/carteira.py`
- Create: `paginas/relatorios.py`
- Create: `paginas/opcoes.py`

**Interfaces:**
- Consumes: `dados_app.carregar_noticias`, `dados_app.invalidar_cache_carteira`, `dados_app.carregar_indicadores`, `dados_app.ultimo_valor` (Task 2); `investidas.*`, `carteira.*`, `relatorios.*` (já existentes, sem mudança); `modules.opcoes.view_opcoes.render_aba_opcoes` (já existente).
- Produces: `pagina_noticias() -> None`, `pagina_investidas() -> None`, `pagina_carteira() -> None`, `pagina_relatorios() -> None`, `pagina_opcoes() -> None`.

Estas 5 páginas não usam gráfico e são extrações mecânicas do corpo de cada
aba em `app.py`, sem lógica nova — por isso agrupadas numa única task.

- [ ] **Step 1: Criar `paginas/noticias.py`**

```python
"""
paginas/noticias.py - Pagina "Noticias": lista de manchetes classificadas.
"""
import streamlit as st

from dados_app import carregar_noticias


def pagina_noticias():
    st.subheader("Notícias do mercado")
    noticias = carregar_noticias()
    if noticias.empty:
        st.info("Nenhuma notícia disponível no momento.")
    else:
        for _, n in noticias.head(20).iterrows():
            st.markdown(f"`{n['categoria']}` **[{n['titulo']}]({n['link']})** — _{n['data']}_")
```

- [ ] **Step 2: Criar `paginas/investidas.py`**

```python
"""
paginas/investidas.py - Pagina "Investidas": monitor de fatos relevantes
por empresa cadastrada.
"""
import streamlit as st


def pagina_investidas():
    st.subheader("Monitor de empresas")
    try:
        from investidas import (
            adicionar_empresa_interesse,
            criar_tabela_empresas_interesse,
            filtrar_noticias_por_empresa,
            listar_empresas_interesse,
            remover_empresa_interesse,
        )

        criar_tabela_empresas_interesse()

        with st.form("form_empresas_interesse", clear_on_submit=True):
            nome_empresa = st.text_input("Empresa", placeholder="Ex.: Itaúsa")
            cnpj = st.text_input("CNPJ (opcional)", placeholder="17.197.092/0001-91")
            enviado = st.form_submit_button("Adicionar empresa")
            if enviado and nome_empresa:
                ok = adicionar_empresa_interesse(nome_empresa, cnpj)
                if ok:
                    st.success(f"Empresa {nome_empresa} adicionada ao monitoramento.")
                else:
                    st.warning("Não foi possível salvar a empresa.")

        empresas = listar_empresas_interesse()
        if empresas.empty:
            st.info("Nenhuma empresa configurada. Adicione uma para começar a monitorar notícias.")
        else:
            for _, empresa in empresas.iterrows():
                nome = empresa["nome_empresa"]
                cnpj_empresa = empresa.get("cnpj", "")
                noticias_empresa = filtrar_noticias_por_empresa(nome)
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"### {nome} ({cnpj_empresa or 'CNPJ não informado'})")
                with col2:
                    if st.button("Remover", key=f"remove_{nome}"):
                        remover_empresa_interesse(nome)
                        st.rerun()

                if noticias_empresa.empty:
                    st.caption(f"Sem notícias recentes sobre {nome}.")
                else:
                    for _, n in noticias_empresa.head(5).iterrows():
                        st.markdown(f"`{n['categoria']}` **[{n['titulo']}]({n['link']})** — _{n['data']}_")
    except Exception as exc:
        st.warning(f"Erro ao carregar Investidas: {exc}")
```

- [ ] **Step 3: Criar `paginas/carteira.py`**

```python
"""
paginas/carteira.py - Pagina "Carteira": edicao da carteira do usuario.
"""
import pandas as pd
import streamlit as st

from dados_app import invalidar_cache_carteira


def pagina_carteira():
    st.subheader("Minha carteira")
    try:
        from carteira import gerar_contexto_carteira, ler_carteira, salvar_carteira

        df_carteira = ler_carteira()
        if df_carteira.empty:
            df_carteira = pd.DataFrame(
                [{
                    "ativo": "Ex: USD/BRL",
                    "descricao": "Posição de hedge",
                    "direcao": "long",
                    "indexador": "Dólar",
                    "tamanho": 50000.0,
                }]
            )

        cols = ["ativo", "descricao", "direcao", "indexador", "tamanho"]
        if not set(cols).issubset(df_carteira.columns):
            for col in cols:
                if col not in df_carteira.columns:
                    df_carteira[col] = ""

        df_editado = st.data_editor(
            df_carteira[cols],
            use_container_width=True,
            hide_index=True,
            key="carteira_editor",
            num_rows="dynamic",
        )

        if st.button("Salvar carteira"):
            ok = salvar_carteira(df_editado)
            if ok:
                invalidar_cache_carteira()
                st.success("Carteira atualizada com sucesso!")
                st.rerun()
            else:
                st.error("Não foi possível salvar a carteira.")

        st.markdown("**Resumo da carteira**")
        st.info(gerar_contexto_carteira())
    except Exception as exc:
        st.warning(f"Erro ao carregar carteira: {exc}")
```

- [ ] **Step 4: Criar `paginas/relatorios.py`**

```python
"""
paginas/relatorios.py - Pagina "Relatorios": geracao/download dos
relatorios Excel operacionais.
"""
import streamlit as st


def _gerar_bytes_relatorio(export_func):
    try:
        caminho = export_func()
        if not caminho:
            return None, None
        with open(caminho, "rb") as arquivo:
            return arquivo.read(), caminho
    except Exception as exc:
        st.error(f"Erro ao preparar relatório: {exc}")
        return None, None


def pagina_relatorios():
    st.subheader("Relatórios operacionais")
    try:
        from relatorios import (
            gerar_relatorio_debentures,
            gerar_relatorio_dolar,
            gerar_relatorio_indicadores,
        )

        relatorios = {
            "Debêntures": ("relatorio_debentures.xlsx", gerar_relatorio_debentures),
            "Indicadores": ("relatorio_indicadores.xlsx", gerar_relatorio_indicadores),
            "Dólar": ("relatorio_dolar.xlsx", gerar_relatorio_dolar),
        }

        for nome, (arquivo_nome, export_func) in relatorios.items():
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**{nome}**")
            with col2:
                if st.button(f"Gerar {nome}", key=f"btn_{arquivo_nome}"):
                    payload, _ = _gerar_bytes_relatorio(export_func)
                    if payload is not None:
                        st.session_state[f"download_{arquivo_nome}"] = payload
                        st.success(f"Relatório {nome} preparado.")
                if st.session_state.get(f"download_{arquivo_nome}") is not None:
                    st.download_button(
                        label=f"Baixar {arquivo_nome}",
                        data=st.session_state[f"download_{arquivo_nome}"],
                        file_name=arquivo_nome,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )

        if st.button("Gerar todos os relatórios"):
            try:
                from relatorios import exportar_todos_relatorios
                arquivos = exportar_todos_relatorios()
                st.success(f"{len(arquivos)} relatórios gerados.")
                for destino in arquivos:
                    st.caption(destino)
            except Exception as exc:
                st.error(f"Erro ao gerar lote: {exc}")
    except Exception as exc:
        st.warning(f"Erro ao carregar relatórios: {exc}")
```

- [ ] **Step 5: Criar `paginas/opcoes.py`**

```python
"""
paginas/opcoes.py - Pagina "Opcoes": wrapper fino em torno do modulo de
Opcoes B3 (modules/opcoes), que ja tem sua propria UI Plotly.
"""
from dados_app import carregar_indicadores, ultimo_valor
from modules.opcoes.view_opcoes import render_aba_opcoes


def pagina_opcoes():
    ind = carregar_indicadores()
    render_aba_opcoes(selic=ultimo_valor(ind, "Selic") / 100)
```

- [ ] **Step 6: Verificar as 5 páginas com dados reais**

Run:
```bash
python -c "from paginas.noticias import pagina_noticias; pagina_noticias()"
python -c "from paginas.investidas import pagina_investidas; pagina_investidas()"
python -c "from paginas.carteira import pagina_carteira; pagina_carteira()"
python -c "from paginas.relatorios import pagina_relatorios; pagina_relatorios()"
python -c "from paginas.opcoes import pagina_opcoes; pagina_opcoes()"
```
Expected: nenhum traceback em nenhum dos 5 comandos.

- [ ] **Step 7: Commit**

```bash
git add paginas/noticias.py paginas/investidas.py paginas/carteira.py paginas/relatorios.py paginas/opcoes.py
git commit -m "feat: extrair paginas Noticias, Investidas, Carteira, Relatorios e Opcoes"
```

---

## Task 8: `app.py` — shell com navegação, tema e assistente de IA

**Files:**
- Modify: `app.py` (reescrita completa — o arquivo todo é substituído pelo shell abaixo)

**Interfaces:**
- Consumes: `tema.aplicar_tema` (Task 1); `dados_app.carregar_indicadores`, `dados_app.carregar_dolar`, `dados_app.carregar_debentures`, `dados_app.carregar_noticias`, `dados_app.ultimo_valor` (Task 2); `paginas.resumo.pagina_resumo` (Task 5); `paginas.macro.pagina_macro` (Task 6); `paginas.noticias.pagina_noticias`, `paginas.investidas.pagina_investidas`, `paginas.carteira.pagina_carteira`, `paginas.relatorios.pagina_relatorios`, `paginas.opcoes.pagina_opcoes` (Task 7).

- [ ] **Step 1: Reescrever `app.py`**

Substituir o conteúdo inteiro de `app.py` por:

```python
# app.py
import pandas as pd
import streamlit as st

from dados_app import carregar_debentures, carregar_dolar, carregar_indicadores, carregar_noticias, ultimo_valor
from db import engine
from paginas.carteira import pagina_carteira
from paginas.investidas import pagina_investidas
from paginas.macro import pagina_macro
from paginas.noticias import pagina_noticias
from paginas.opcoes import pagina_opcoes
from paginas.relatorios import pagina_relatorios
from paginas.resumo import pagina_resumo
from tema import aplicar_tema

st.set_page_config(
    page_title="Market Intelligence Hub",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

aplicar_tema()

st.markdown(
    """
    <div class="topbar">
        <h1>Market Intelligence Hub</h1>
        <p>Radar macro, debêntures, notícias e carteira em uma interface operacional.</p>
        <div class="status-pill">Sistema ativo • monitoramento em tempo real</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    if st.button("🤖 Assistente IA", use_container_width=True):
        st.session_state["ia_open"] = True

pg = st.navigation([
    st.Page(pagina_resumo, title="Resumo", icon="📊"),
    st.Page(pagina_macro, title="Macro", icon="📈"),
    st.Page(pagina_noticias, title="Notícias", icon="📰"),
    st.Page(pagina_investidas, title="Investidas", icon="🏢"),
    st.Page(pagina_carteira, title="Carteira", icon="💼"),
    st.Page(pagina_relatorios, title="Relatórios", icon="📥"),
    st.Page(pagina_opcoes, title="Opções", icon="🧮"),
])
pg.run()

# Assistente de IA - persistente, renderizado fora de qualquer pagina
prompt_ia = st.chat_input("Pergunte à plataforma sobre mercado, taxas e renda fixa...")
if prompt_ia:
    try:
        from analise_ia import responder_pergunta
        from carteira import gerar_contexto_carteira

        ind = carregar_indicadores()
        dolar = carregar_dolar()
        deb = carregar_debentures()
        noticias = carregar_noticias()
        mercado = noticias[~noticias["categoria"].isin(["Outros", ""])].copy()

        contexto = (
            f"Indicadores: Selic {round(ultimo_valor(ind, 'Selic'), 2)}% a.a., "
            f"IPCA {round(ultimo_valor(ind, 'IPCA'), 2)}% (mes), IGP-M {round(ultimo_valor(ind, 'IGP-M'), 2)}% (mes).\n"
            f"Dolar USD/BRL atual: R$ {float(dolar['close'].iloc[-1]) if not dolar.empty else 0:.2f}.\n"
            f"Debentures: {len(deb)} series.\n"
        )
        if not deb.empty:
            contexto += f"Por indexador: {deb['indexador'].value_counts().to_dict()}\n"
        try:
            contexto += "\nCarteira: " + gerar_contexto_carteira() + "\n"
        except Exception:
            pass
        try:
            briefing = pd.read_sql("SELECT texto FROM briefing", engine)
            if not briefing.empty:
                contexto += "\nBriefing: " + briefing["texto"].iloc[0] + "\n"
        except Exception:
            pass
        if not mercado.empty:
            contexto += "\nManchetes: " + "; ".join(mercado["titulo"].head(10).tolist())

        with st.spinner("Pensando..."):
            st.write(responder_pergunta(prompt_ia, contexto))
    except Exception as exc:
        st.warning(f"Erro ao responder pergunta: {exc}")
```

- [ ] **Step 2: Verificar que o arquivo importa sem erro**

Run: `python -c "import ast; ast.parse(open('app.py', encoding='utf-8').read())"`
Expected: nenhum traceback (confirma que o arquivo é sintaticamente válido antes do teste manual com o servidor real).

- [ ] **Step 3: Verificação manual completa**

Run: `python -m streamlit run app.py`

No navegador, confirmar:
- A sidebar mostra a lista de páginas (Resumo, Macro, Notícias, Investidas, Carteira, Relatórios, Opções) no lugar das abas horizontais de antes, com o item ativo destacado (borda cyan à esquerda).
- O botão "🤖 Assistente IA" continua no topo da sidebar, acima da lista de páginas.
- Cada página abre sem erro e mostra o conteúdo esperado (Resumo com exposição/sinais, Macro com métricas + gráfico de dólar em Plotly + debêntures, Notícias, Investidas, Carteira editável, Relatórios com botões de download, Opções).
- O gráfico de dólar (Macro) e o de exposição (Resumo) aparecem como gráficos Plotly (interativos, com hover), não mais `st.line_chart`/`st.bar_chart` nativos.
- O chat "Pergunte à plataforma..." continua visível embaixo, funciona independente de qual página está aberta.
- Trocar de página e voltar não deve gerar erro nem demora perceptível (efeito do cache).

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: reescrever app.py como shell com st.navigation e tema Terminal Cartesiano"
```

---

## Self-Review

**Spec coverage:**
- Seção 2 (tokens de cor e tipografia) → Task 1.
- Seção 3 (navegação `st.navigation`/`st.Page`, pacote `paginas/`) → Tasks 5-8.
- Seção 4 (`tema.py`, funções de gráfico Plotly, helper de badge) → Tasks 1, 3, 4.
- Seção 5 (dados cacheados por página) → Task 2, consumido nas Tasks 5-8.
- Seção 6 (erros/testes inalterados, verificação manual) → mantido em todas as tasks de página; Task 8 traz a verificação manual completa.

**Placeholder scan:** nenhum "TBD"/"TODO" — todos os steps têm código completo, extraído linha a linha do `app.py` atual (lido integralmente antes de escrever este plano).

**Type consistency:** `ultimo_valor(df_indicadores, nome)` definido na Task 2 e usado com essa assinatura (2 argumentos posicionais) em `paginas/macro.py` (Task 6), `paginas/opcoes.py` (Task 7) e `app.py` (Task 8) — nenhuma chamada usa a assinatura antiga de 1 argumento. `grafico_linha`/`grafico_barra` (Task 3) usados com os mesmos nomes e assinatura em `paginas/resumo.py` e `paginas/macro.py`. `badge_sinal` (Task 4) usado com a mesma assinatura em `paginas/resumo.py`. Nomes de página (`pagina_resumo`, `pagina_macro`, etc.) idênticos entre a task que os cria e a Task 8 que os importa.
