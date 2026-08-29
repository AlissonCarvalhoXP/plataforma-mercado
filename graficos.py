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
