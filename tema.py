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
        font-family: 'Space Grotesk', sans-serif;
    }}
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
