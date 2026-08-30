# Polimento de Tabelas e KPIs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar os `st.metric()` crus da página Macro por cards de KPI no estilo Terminal Cartesiano (com variação vs. leitura anterior), e trocar a formatação de tabela via string por `column_config` nativo (moeda/data/progresso/link tipados) em Macro e Carteira, incluindo destaque condicional do spread de debêntures.

**Architecture:** Três módulos pequenos e puros seguem o padrão já estabelecido (`tema.py`/`graficos.py`/`componentes.py`): `dados_app.py` ganha uma função de delta genérica, `componentes.py` ganha `kpi_card`, e um novo `tabelas.py` concentra os dicionários de `column_config` e a lógica de destaque condicional. As páginas Macro e Carteira só passam a chamar esses helpers em vez de pré-formatar valores como string.

**Tech Stack:** Python, Streamlit 1.62 (`st.column_config`, `pandas.Styler` via `st.dataframe`), pandas.

**Spec:** [docs/superpowers/specs/2026-08-29-polimento-tabelas-kpi-design.md](../specs/2026-08-29-polimento-tabelas-kpi-design.md)

## Global Constraints

- Nenhuma query, coleta ou regra de negócio muda — só apresentação (Macro e Carteira, únicas páginas tocadas).
- Sem framework de teste automatizado — convenção é `assert` em `if __name__ == "__main__":`, igual já usado em `exposicao.py`/`dados_app.py`/`tema.py`/`graficos.py`/`componentes.py`.
- `calcular_delta_indicador` segue a MESMA regra já estabelecida em `exposicao._calcular_deltas`: delta = última leitura vs. leitura imediatamente anterior **distinta** (dedup por data primeiro — o banco real tem linhas duplicadas por data em `indicadores_bcb`), e `None` quando houver menos de 2 leituras distintas (nunca inventar delta).
- **Desvio deliberado do exemplo do spec, baseado em dado real:** o spec cita `indexador` como candidato a `SelectboxColumn`, mas a carteira real hoje tem `indexador = "Ibov"` (verificado direto no banco) — valor fora do conjunto canônico documentado em `carteira.py` ("CDI, Prefixado, IPCA, Dólar, Bolsa, N/A"). `SelectboxColumn` é um dropdown estrito: travaria a edição dessa linha existente. Por isso `colunas_carteira()` aplica `SelectboxColumn` **só em `direcao`** (valores reais confirmados: `long`/`short`, dentro do conjunto que `salvar_carteira()` já força) — `indexador` continua texto livre, sem mudança de comportamento.
- Cores de destaque usam os tokens já existentes em `tema.CORES` (`signal_pos`/`signal_neg`) — não inventar cores novas.

---

## Task 1: `dados_app.py` — `calcular_delta_indicador`

**Files:**
- Modify: `dados_app.py`

**Interfaces:**
- Consumes: `normalizar_indicador(valor) -> str` (já existe no mesmo arquivo).
- Produces: `calcular_delta_indicador(df_indicadores: pd.DataFrame, nome: str) -> float | None`.

- [ ] **Step 1: Escrever o teste (asserts) para o novo caso**

No bloco `if __name__ == "__main__":` de `dados_app.py`, adicionar (após o `Caso 2` existente, antes do `print("\nTodos os casos passaram.")` final):

```python
    df_selic_2_leituras = pd.DataFrame({
        "indicador": ["Selic", "Selic"],
        "data": pd.to_datetime(["2026-08-01", "2026-08-15"]),
        "valor": [10.50, 10.75],
    })
    assert calcular_delta_indicador(df_selic_2_leituras, "Selic") == 0.25 or round(calcular_delta_indicador(df_selic_2_leituras, "Selic"), 2) == 0.25
    print("[OK] Caso 3: calcular_delta_indicador acha a ultima leitura vs. a anterior.")

    df_uma_leitura = pd.DataFrame({
        "indicador": ["IPCA"],
        "data": pd.to_datetime(["2026-08-01"]),
        "valor": [0.30],
    })
    assert calcular_delta_indicador(df_uma_leitura, "IPCA") is None
    assert calcular_delta_indicador(df_ind, "Selic") is not None  # df_ind (Caso 1) tem 2 leituras de Selic
    print("[OK] Caso 4: calcular_delta_indicador devolve None com menos de 2 leituras.")

    df_com_duplicata = pd.DataFrame({
        "indicador": ["Selic", "Selic", "Selic"],
        "data": pd.to_datetime(["2026-08-01", "2026-08-15", "2026-08-15"]),
        "valor": [10.50, 10.75, 10.75],
    })
    delta_dup = calcular_delta_indicador(df_com_duplicata, "Selic")
    assert round(delta_dup, 2) == 0.25  # 10.75 (15/08) - 10.50 (01/08), nao 10.75 - 10.75
    print("[OK] Caso 5: linha duplicada na ultima data nao zera o delta (dedup por data aplicado).")
```

- [ ] **Step 2: Rodar para confirmar que falha**

Run: `python dados_app.py`
Expected: `NameError: name 'calcular_delta_indicador' is not defined`.

- [ ] **Step 3: Implementar**

Adicionar em `dados_app.py`, logo após a função `ultimo_valor` existente (antes do bloco `if __name__ == "__main__":`):

```python
def calcular_delta_indicador(df_indicadores, nome):
    """Delta = ultima leitura - leitura imediatamente anterior DISTINTA, para
    o indicador `nome`. None se houver menos de 2 leituras distintas (nunca
    inventa um delta). Mesma regra de exposicao._calcular_deltas, generalizada
    para qualquer indicador (usada pelos KPIs da pagina Macro)."""
    if df_indicadores is None or df_indicadores.empty:
        return None
    chave = normalizar_indicador(nome)
    serie = (
        df_indicadores[df_indicadores["indicador"].map(normalizar_indicador) == chave]
        .sort_values("data")
        .drop_duplicates(subset="data", keep="last")
    )
    if len(serie) < 2:
        return None
    valores = serie["valor"].tolist()
    return valores[-1] - valores[-2]
```

- [ ] **Step 4: Rodar para confirmar que passa**

Run: `python dados_app.py`
Expected: `[OK] Caso 1...` até `[OK] Caso 5...`, seguido de `Todos os casos passaram.`, sem traceback.

- [ ] **Step 5: Verificar contra o banco real**

Run:
```bash
python -c "
from dados_app import carregar_indicadores, calcular_delta_indicador
ind = carregar_indicadores()
for nome in ['Selic', 'CDI', 'IPCA', 'IGP-M']:
    print(nome, '->', calcular_delta_indicador(ind, nome))
"
```
Expected: 4 linhas, cada uma com um número (positivo, negativo ou zero) ou `None`, sem traceback.

- [ ] **Step 6: Commit**

```bash
git add dados_app.py
git commit -m "feat: adicionar calcular_delta_indicador em dados_app.py"
```

---

## Task 2: `kpi_card` — componente + CSS de suporte

**Files:**
- Modify: `componentes.py`
- Modify: `tema.py`

**Interfaces:**
- Produces: `kpi_card(label: str, valor_texto: str, delta_texto: str | None = None, sentido: str | None = None) -> str`. `sentido`, quando informado, deve ser `"positivo"`, `"negativo"` ou `"neutro"` — qualquer outro valor cai em `"neutro"`. Isto é **direção do valor** (subiu/desceu), não o vocabulário `favoravel`/`desfavoravel` de `exposicao.py` (que depende de contexto de carteira, que os KPIs da Macro não têm).

- [ ] **Step 1: Escrever o teste (asserts) para `kpi_card`**

No bloco `if __name__ == "__main__":` de `componentes.py`, adicionar (após o `Caso 3` existente, antes do `print("\nTodos os casos passaram.")` final):

```python
    html_sem_delta = kpi_card("Selic", "14,00%")
    assert html_sem_delta == '<div class="kpi-card"><div class="kpi-label">Selic</div><div class="kpi-value">14,00%</div></div>'
    print("[OK] Caso 4: kpi_card sem delta.")

    html_positivo = kpi_card("Selic", "14,00%", "▲ +0.25 p.p.", "positivo")
    assert '<span class="kpi-delta positivo">▲ +0.25 p.p.</span>' in html_positivo
    print("[OK] Caso 5: kpi_card com delta positivo.")

    html_negativo = kpi_card("IPCA", "0,07%", "▼ -0.10 p.p.", "negativo")
    assert 'kpi-delta negativo' in html_negativo
    print("[OK] Caso 6: kpi_card com delta negativo.")

    html_sentido_invalido = kpi_card("X", "1", "0", "sentido-desconhecido")
    assert 'kpi-delta neutro' in html_sentido_invalido
    print("[OK] Caso 7: sentido invalido cai em neutro.")
```

- [ ] **Step 2: Rodar para confirmar que falha**

Run: `python componentes.py`
Expected: `NameError: name 'kpi_card' is not defined`.

- [ ] **Step 3: Implementar `kpi_card`**

Adicionar em `componentes.py`, logo após `_BADGES`/antes de `badge_sinal` (ou depois, tanto faz — manter as duas funções no mesmo arquivo):

```python
_CLASSES_DELTA_VALIDAS = {"positivo", "negativo", "neutro"}


def kpi_card(label, valor_texto, delta_texto=None, sentido=None):
    """Monta o HTML de um card de KPI no estilo Terminal Cartesiano. `sentido`
    (quando informado) e' "positivo"/"negativo"/"neutro" - direcao do valor,
    nao o vocabulario de exposicao.gerar_sinais_exposicao."""
    delta_html = ""
    if delta_texto is not None:
        classe = sentido if sentido in _CLASSES_DELTA_VALIDAS else "neutro"
        delta_html = f'<span class="kpi-delta {classe}">{delta_texto}</span>'
    return (
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{valor_texto}{delta_html}</div>'
        f'</div>'
    )
```

- [ ] **Step 4: Adicionar o CSS de suporte em `tema.py`**

Em `tema.py`, dentro do bloco `CSS` (string), logo antes do fechamento `</style>` (depois da regra `.status-pill { ... }` existente), adicionar:

```css
    .kpi-card {{
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 0.85rem 1rem;
    }}
    .kpi-label {{
        font-size: 0.72rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--muted);
        margin-bottom: 0.35rem;
    }}
    .kpi-value {{
        font-family: 'IBM Plex Mono', 'Consolas', monospace;
        font-size: 1.5rem;
        font-weight: 600;
        color: var(--text);
    }}
    .kpi-delta {{
        font-family: 'IBM Plex Mono', 'Consolas', monospace;
        font-size: 0.85rem;
        margin-left: 0.5rem;
    }}
    .kpi-delta.positivo {{ color: var(--signal-pos); }}
    .kpi-delta.negativo {{ color: var(--signal-neg); }}
    .kpi-delta.neutro {{ color: var(--muted); }}
```

(Nota: como o resto do bloco `CSS`, estas chaves duplas `{{`/`}}` são necessárias porque `CSS` é uma f-string — chave literal em f-string escreve-se dobrada.)

- [ ] **Step 5: Rodar os dois testes para confirmar que passam**

Run: `python componentes.py`
Expected: `[OK] Caso 1...` até `[OK] Caso 7...`, seguido de `Todos os casos passaram.`, sem traceback.

Run: `python tema.py`
Expected: os 3 casos existentes continuam passando (o CSS adicionado não quebra os asserts que checam tokens/fontes).

- [ ] **Step 6: Commit**

```bash
git add componentes.py tema.py
git commit -m "feat: adicionar kpi_card e CSS de suporte"
```

---

## Task 3: `tabelas.py` — column_config, progresso e destaque condicional

**Files:**
- Create: `tabelas.py`

**Interfaces:**
- Consumes: `tema.CORES` (dict de tokens de cor, já existente).
- Produces: `colunas_dolar() -> dict`, `colunas_debentures() -> dict`, `colunas_carteira() -> dict`, `progresso_prazo(data_emissao, data_vencimento, hoje=None) -> float`, `destacar_spread(df: pd.DataFrame) -> pandas.io.formats.style.Styler`.

- [ ] **Step 1: Escrever o teste (asserts) e o esqueleto do módulo**

Criar `tabelas.py`:

```python
"""
tabelas.py - Configuracao de exibicao de tabelas (column_config nativo do
Streamlit) e destaque condicional, compartilhados entre paginas. Ao contrario
de componentes.py, este modulo IMPORTA streamlit - column_config so existe
la dentro.
"""
import pandas as pd
import streamlit as st

from tema import CORES


if __name__ == "__main__":
    # Caso 1: progresso_prazo - prazo ainda nao iniciado
    assert progresso_prazo("2026-06-01", "2026-12-01", hoje="2026-01-01") == 0.0
    print("[OK] Caso 1: progresso_prazo antes da emissao -> 0.0.")

    # Caso 2: progresso_prazo - prazo ja vencido (clamp em 1.0)
    assert progresso_prazo("2026-01-01", "2026-06-01", hoje="2026-12-01") == 1.0
    print("[OK] Caso 2: progresso_prazo apos o vencimento -> 1.0 (clamp).")

    # Caso 3: progresso_prazo - no meio do prazo
    meio = progresso_prazo("2026-01-01", "2026-01-11", hoje="2026-01-06")
    assert round(meio, 2) == 0.50
    print("[OK] Caso 3: progresso_prazo no meio do prazo -> ~0.5.")

    # Caso 4: progresso_prazo - datas invalidas/faltando -> 0.0, sem excecao
    assert progresso_prazo(None, "2026-06-01") == 0.0
    assert progresso_prazo("2026-01-01", None) == 0.0
    print("[OK] Caso 4: progresso_prazo com data faltando -> 0.0, sem excecao.")

    # Caso 5: _cor_fundo_spread - abaixo/acima/igual a media
    assert _cor_fundo_spread(1.0, 2.0) == f"background-color: {CORES['signal_pos']}33"
    assert _cor_fundo_spread(3.0, 2.0) == f"background-color: {CORES['signal_neg']}33"
    assert _cor_fundo_spread(2.0, 2.0) == ""
    assert _cor_fundo_spread(float("nan"), 2.0) == ""
    print("[OK] Caso 5: _cor_fundo_spread compara contra a media corretamente.")

    # Caso 6: destacar_spread devolve um Styler utilizavel, sem excecao
    df_teste = pd.DataFrame({"indexador": ["CDI", "CDI", "IPCA"], "spread": [1.0, 3.0, 2.0]})
    styler = destacar_spread(df_teste)
    assert hasattr(styler, "to_html")
    styler.to_html()  # nao deve lancar excecao
    print("[OK] Caso 6: destacar_spread devolve um Styler valido.")

    # Caso 7: colunas_* devolvem dicts nao vazios de ColumnConfig
    assert len(colunas_dolar()) == 2
    assert len(colunas_debentures()) == 8
    assert len(colunas_carteira()) == 2
    print("[OK] Caso 7: colunas_dolar/colunas_debentures/colunas_carteira devolvem os dicts esperados.")

    print("\nTodos os casos passaram.")
```

- [ ] **Step 2: Rodar para confirmar que falha**

Run: `python tabelas.py`
Expected: `NameError: name 'progresso_prazo' is not defined`.

- [ ] **Step 3: Implementar**

Inserir entre o `from tema import CORES` e o bloco `if __name__ == "__main__":`:

```python
def progresso_prazo(data_emissao, data_vencimento, hoje=None):
    """Fracao (0 a 1, com clamp) do prazo da debenture ja decorrida. 0.0 se
    faltar data de emissao/vencimento - nunca lanca excecao por dado ruim."""
    if data_emissao is None or data_vencimento is None or pd.isna(data_emissao) or pd.isna(data_vencimento):
        return 0.0
    inicio = pd.to_datetime(data_emissao)
    fim = pd.to_datetime(data_vencimento)
    agora = pd.to_datetime(hoje) if hoje is not None else pd.Timestamp.now()
    duracao_total = (fim - inicio).total_seconds()
    if duracao_total <= 0:
        return 1.0
    decorrido = (agora - inicio).total_seconds()
    fracao = decorrido / duracao_total
    return max(0.0, min(1.0, fracao))


def _cor_fundo_spread(spread, media):
    """Cor de fundo (com transparencia, sufixo hex '33') para uma celula de
    spread comparada a media do seu indexador. "" se nao houver comparacao
    possivel (spread ou media ausentes)."""
    if pd.isna(spread) or pd.isna(media):
        return ""
    if spread < media:
        return f"background-color: {CORES['signal_pos']}33"
    if spread > media:
        return f"background-color: {CORES['signal_neg']}33"
    return ""


def destacar_spread(df):
    """Aplica _cor_fundo_spread na coluna spread, comparando cada linha a
    media do seu indexador. Devolve um pandas.Styler pronto para
    st.dataframe(destacar_spread(df), ...). Sem-op (Styler neutro) se as
    colunas 'spread'/'indexador' nao existirem."""
    if "spread" not in df.columns or "indexador" not in df.columns:
        return df.style

    medias = df.groupby("indexador")["spread"].transform("mean")
    indice_spread = df.columns.get_loc("spread")

    def _estilo_linha(row):
        estilos = [""] * len(df.columns)
        estilos[indice_spread] = _cor_fundo_spread(row["spread"], medias.loc[row.name])
        return estilos

    return df.style.apply(_estilo_linha, axis=1)


def colunas_dolar():
    """column_config para a tabela de dolar (pagina Macro)."""
    return {
        "date": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "close": st.column_config.NumberColumn("Fechamento", format="R$ %.4f"),
    }


def colunas_debentures():
    """column_config para a tabela de debentures (pagina Macro). Colunas de
    texto puro (emissor, serie, indexador, rating, etc.) nao entram aqui -
    ficam com a renderizacao nativa, sem mudanca de comportamento."""
    return {
        "spread": st.column_config.NumberColumn("Spread (%)", format="%.2f%%"),
        "valor_serie": st.column_config.NumberColumn("Valor (R$ mi)", format="R$ %.2f"),
        "prazo_anos": st.column_config.NumberColumn("Prazo (anos)", format="%.2f"),
        "progresso_prazo": st.column_config.ProgressColumn("Prazo decorrido", min_value=0.0, max_value=1.0),
        "data_emissao": st.column_config.DateColumn("Emissão", format="DD/MM/YYYY"),
        "data_vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
        "data_encerramento": st.column_config.DateColumn("Encerramento", format="DD/MM/YYYY"),
        "link_sre": st.column_config.LinkColumn("Link SRE", display_text="Ver na CVM"),
    }


def colunas_carteira():
    """column_config para o data_editor da Carteira. Só `direcao` vira
    SelectboxColumn (valores reais confirmados: long/short, já validados por
    carteira.salvar_carteira()) - `indexador` fica texto livre (dado real tem
    valores fora do conjunto canônico documentado, ex.: "Ibov")."""
    return {
        "direcao": st.column_config.SelectboxColumn("Direção", options=["long", "short"], required=True),
        "tamanho": st.column_config.NumberColumn("Tamanho (R$)", format="R$ %.2f", min_value=0.0),
    }
```

- [ ] **Step 4: Rodar para confirmar que passa**

Run: `python tabelas.py`
Expected: `[OK] Caso 1...` até `[OK] Caso 7...`, seguido de `Todos os casos passaram.`, sem traceback.

- [ ] **Step 5: Verificar `colunas_debentures`/`destacar_spread`/`progresso_prazo` contra o banco real**

Run:
```bash
python -c "
import pandas as pd
from dados_app import carregar_debentures
from tabelas import colunas_debentures, destacar_spread, progresso_prazo

deb = carregar_debentures()
deb['data_emissao'] = pd.to_datetime(deb['data_emissao'], errors='coerce')
deb['data_vencimento'] = pd.to_datetime(deb['data_vencimento'], errors='coerce')
deb['progresso_prazo'] = deb.apply(lambda r: progresso_prazo(r['data_emissao'], r['data_vencimento']), axis=1)
print('progresso_prazo: min', deb['progresso_prazo'].min(), 'max', deb['progresso_prazo'].max())

styler = destacar_spread(deb)
styler.to_html()
print('destacar_spread OK contra', len(deb), 'linhas reais')

cfg = colunas_debentures()
print('colunas_debentures OK,', len(cfg), 'colunas configuradas')
"
```
Expected: `progresso_prazo: min` e `max` entre 0.0 e 1.0, `destacar_spread OK contra N linhas reais`, `colunas_debentures OK, 8 colunas configuradas`, sem traceback.

- [ ] **Step 6: Commit**

```bash
git add tabelas.py
git commit -m "feat: adicionar tabelas.py com column_config e destaque condicional"
```

---

## Task 4: Aplicar em `paginas/macro.py`

**Files:**
- Modify: `paginas/macro.py` (reescrita completa — o arquivo todo é substituído pelo conteúdo abaixo)

**Interfaces:**
- Consumes: `componentes.kpi_card` (Task 2); `dados_app.calcular_delta_indicador` (Task 1); `tabelas.colunas_dolar`, `tabelas.colunas_debentures`, `tabelas.destacar_spread`, `tabelas.progresso_prazo` (Task 3); `formatacao.formatar_moeda` (já existente); `graficos.grafico_barra`/`grafico_linha` (já existente).

- [ ] **Step 1: Reescrever `paginas/macro.py`**

Substituir o conteúdo inteiro do arquivo por:

```python
"""
paginas/macro.py - Pagina "Macro": indicadores do BCB, dolar e debentures.
Cards de KPI (Terminal Cartesiano) no lugar de st.metric, colunas tipadas
via tabelas.py nas tabelas, e destaque condicional do spread.
"""
import pandas as pd
import streamlit as st

from componentes import kpi_card
from dados_app import calcular_delta_indicador, carregar_debentures, carregar_dolar, carregar_indicadores, ultimo_valor
from formatacao import formatar_moeda
from graficos import grafico_barra, grafico_linha
from tabelas import colunas_debentures, colunas_dolar, destacar_spread, progresso_prazo


def _kpi_indicador(ind, nome, label, casas=2):
    valor = round(ultimo_valor(ind, nome), casas)
    valor_texto = f"{valor:.{casas}f}%"
    delta = calcular_delta_indicador(ind, nome)
    if delta is None:
        return kpi_card(label, valor_texto)
    seta = "▲" if delta > 0 else ("▼" if delta < 0 else "•")
    sentido = "positivo" if delta > 0 else ("negativo" if delta < 0 else "neutro")
    delta_texto = f"{seta} {delta:+.{casas}f} p.p."
    return kpi_card(label, valor_texto, delta_texto, sentido)


def pagina_macro():
    st.subheader("Indicadores macro")

    ind = carregar_indicadores()
    dolar = carregar_dolar()
    deb = carregar_debentures()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(_kpi_indicador(ind, "Selic", "Selic (% a.a.)"), unsafe_allow_html=True)
    with c2:
        st.markdown(_kpi_indicador(ind, "CDI", "CDI (% a.d.)", casas=4), unsafe_allow_html=True)
    with c3:
        st.markdown(_kpi_indicador(ind, "IPCA", "IPCA (% mês)"), unsafe_allow_html=True)
    with c4:
        st.markdown(_kpi_indicador(ind, "IGP-M", "IGP-M (% mês)"), unsafe_allow_html=True)

    st.subheader("Dólar (USD/BRL)")
    if not dolar.empty:
        st.plotly_chart(grafico_linha(dolar, "date", "close", titulo="USD/BRL"), width="stretch", theme=None)
        st.dataframe(dolar, width="stretch", hide_index=True, column_config=colunas_dolar())
    else:
        st.info("Sem dados de dólar disponíveis.")

    st.subheader("Debêntures")
    if not deb.empty:
        d1, d2 = st.columns(2)
        with d1:
            st.markdown(kpi_card("Séries coletadas", str(len(deb))), unsafe_allow_html=True)
        with d2:
            st.markdown(
                kpi_card("Volume total (bi)", formatar_moeda(deb["valor_serie"].sum() / 1e9)),
                unsafe_allow_html=True,
            )
        st.write("**Emissões por indexador**")
        st.plotly_chart(grafico_barra(deb["indexador"].value_counts()), width="stretch", theme=None)

        deb_display = deb[[
            "nome_emissor", "serie", "indexador", "spread", "valor_serie", "prazo_anos",
            "data_emissao", "data_vencimento", "rating", "titulo_incentivado",
            "nome_lider", "agente_fiduciario", "data_encerramento", "link_sre",
        ]].copy()
        for coluna in ["data_emissao", "data_vencimento", "data_encerramento"]:
            deb_display[coluna] = pd.to_datetime(deb_display[coluna], errors="coerce")
        deb_display["valor_serie"] = deb_display["valor_serie"] / 1e6
        deb_display["progresso_prazo"] = deb_display.apply(
            lambda linha: progresso_prazo(linha["data_emissao"], linha["data_vencimento"]), axis=1
        )
        st.dataframe(
            destacar_spread(deb_display),
            width="stretch",
            hide_index=True,
            column_config=colunas_debentures(),
        )
    else:
        st.info("Sem dados de debêntures disponíveis.")
```

- [ ] **Step 2: Verificar com dados reais**

Run: `python -c "from paginas.macro import pagina_macro; pagina_macro()"`
Expected: nenhum traceback (avisos de `ScriptRunContext` são esperados fora de `streamlit run`).

- [ ] **Step 3: Verificação manual visual**

Run: `python -m streamlit run app.py`

Na página Macro, confirmar visualmente:
- Os 4 KPIs de indicador (Selic/CDI/IPCA/IGP-M) aparecem como cards (fundo, borda), com um ▲/▼ colorido ao lado do valor quando houver leitura anterior para comparar.
- "Séries coletadas" e "Volume total" também aparecem como cards (sem seta, são totais sem "leitura anterior").
- A tabela de dólar mostra a data no formato dd/mm/aaaa e o fechamento como moeda, sem serem mais strings pré-formatadas (a ordenação por coluna deve funcionar numericamente/cronologicamente ao clicar no cabeçalho).
- A tabela de debêntures mostra: uma coluna de barra de progresso ("Prazo decorrido"), a coluna de spread com fundo verde/coral em algumas linhas (comparado à média do indexador), e a coluna "Link SRE" como link clicável.

- [ ] **Step 4: Commit**

```bash
git add paginas/macro.py
git commit -m "feat: aplicar kpi_card e column_config na pagina Macro"
```

---

## Task 5: Aplicar em `paginas/carteira.py`

**Files:**
- Modify: `paginas/carteira.py:33-39` (a chamada `st.data_editor`)

**Interfaces:**
- Consumes: `tabelas.colunas_carteira` (Task 3).

- [ ] **Step 1: Adicionar o import**

Em `paginas/carteira.py`, adicionar ao topo do arquivo (junto aos imports existentes):

```python
from tabelas import colunas_carteira
```

- [ ] **Step 2: Adicionar `column_config` na chamada existente**

Substituir:

```python
        df_editado = st.data_editor(
            df_carteira[cols],
            width="stretch",
            hide_index=True,
            key="carteira_editor",
            num_rows="dynamic",
        )
```

por:

```python
        df_editado = st.data_editor(
            df_carteira[cols],
            width="stretch",
            hide_index=True,
            key="carteira_editor",
            num_rows="dynamic",
            column_config=colunas_carteira(),
        )
```

- [ ] **Step 3: Verificar com dados reais**

Run: `python -c "from paginas.carteira import pagina_carteira; pagina_carteira()"`
Expected: nenhum traceback.

Run adicional (confirma que a carteira real não tem valor de `direcao` fora do dropdown, já verificado nesta sessão mas repetido aqui para o registro):
```bash
python -c "
from carteira import ler_carteira
print(ler_carteira()[['direcao']].drop_duplicates())
"
```
Expected: só `long`/`short` aparecem — se aparecer qualquer outro valor, PARE e reporte antes de prosseguir (indicaria que o `SelectboxColumn` de `direcao` quebraria a edição dessa linha).

- [ ] **Step 4: Verificação manual visual**

Run: `python -m streamlit run app.py`

Na página Carteira, confirmar: a coluna "Direção" do editor agora é um dropdown (long/short) em vez de texto livre; a coluna "Indexador" continua texto livre (incluindo a linha real com "Ibov"); a coluna "Tamanho" mostra o valor formatado como moeda.

- [ ] **Step 5: Commit**

```bash
git add paginas/carteira.py
git commit -m "feat: aplicar column_config no data_editor da Carteira"
```

---

## Self-Review

**Spec coverage:**
- Seção 2 (`kpi_card`, `calcular_delta_indicador`, `tabelas.py`) → Tasks 1, 2, 3.
- Seção 3 (onde aplica: Macro e Carteira) → Tasks 4, 5.
- Seção 4 (erros/testes: funções puras testadas, verificação manual para UI) → todas as tasks.

**Desvio registrado:** `indexador` na Carteira NÃO virou `SelectboxColumn` (diferente do exemplo do spec) — motivo documentado nos Global Constraints e no docstring de `colunas_carteira()`, baseado em inspeção do dado real (`indexador = "Ibov"` na carteira atual, fora do conjunto canônico). Nenhuma outra parte do spec ficou sem task.

**Placeholder scan:** nenhum "TBD"/"TODO" — todo código é completo e foi verificado contra os arquivos reais (`paginas/macro.py`, `paginas/carteira.py`, `componentes.py`, `dados_app.py`, `tema.py`) antes de escrever este plano, e as assinaturas de `st.column_config.*` foram inspecionadas diretamente no Streamlit 1.62 instalado (todos os kwargs usados — `format`, `min_value`, `max_value`, `options`, `required`, `display_text` — existem nas assinaturas reais).

**Type consistency:** `kpi_card(label, valor_texto, delta_texto=None, sentido=None)` definido na Task 2 e chamado com essa assinatura em `paginas/macro.py` (Task 4). `calcular_delta_indicador(df_indicadores, nome)` definido na Task 1, usado com essa assinatura em `paginas/macro.py` (Task 4). `colunas_dolar()`/`colunas_debentures()`/`colunas_carteira()`/`destacar_spread(df)`/`progresso_prazo(data_emissao, data_vencimento, hoje=None)` definidos na Task 3, usados com essas assinaturas exatas nas Tasks 4 e 5.
