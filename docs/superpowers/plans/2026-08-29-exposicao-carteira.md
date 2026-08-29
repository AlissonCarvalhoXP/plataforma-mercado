# Camada de Sinais de Exposição da Carteira Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cruzar a exposição da carteira do usuário (por indexador/direção) com os movimentos macro que o MIH já coleta (Selic, IPCA, USD/BRL), expondo sinais direcionais na aba Resumo do dashboard e no contexto do briefing gerado por IA.

**Architecture:** Novo módulo `exposicao.py` na raiz do projeto, com funções puras (sem efeito colateral), no mesmo padrão de `analises.py`. Nenhuma tabela nova — lê `carteira`, `indicadores_bcb` e `usd_brl`, que já existem. É consumido em dois pontos aditivos: `app.py` (aba Resumo) e `briefing.py` (contexto da IA).

**Tech Stack:** Python, pandas, SQLAlchemy (`db.engine`), Streamlit (apenas no ponto de consumo em `app.py`).

**Spec:** [docs/superpowers/specs/2026-08-29-exposicao-carteira-design.md](../specs/2026-08-29-exposicao-carteira-design.md)

## Global Constraints

- Funções de `exposicao.py` são puras: sem `subprocess`, sem escrita em banco, sem import de `streamlit` — mesmo padrão de `analises.py` (regra documentada no `HANDOFF.md` seção 9: "importação circular + efeito colateral: subprocess NUNCA em módulo importado").
- Nenhuma assinatura de módulo existente (`carteira.py`, `app.py`, `briefing.py`) muda — a integração é estritamente aditiva.
- Sem framework de teste automatizado no projeto: usar bloco `if __name__ == "__main__":` com `assert`s, seguindo a convenção já usada em `carteira.py` e `analises.py`.
- Nunca inventar um sinal quando faltar dado suficiente (regra do spec, seção 5): se uma série macro tiver menos de 2 leituras, o indexador correspondente simplesmente não gera sinal.
- Janela de comparação padronizada: última leitura vs. leitura imediatamente anterior de cada série (spec, seção 3.2) — não usar a janela de 6 leituras de `analisar_dolar()` nem a comparação com o primeiro registro histórico de `analisar_selic()`.
- Ordenação dos sinais: desfavorável primeiro (spec, seção 3.3).
- Formatação de moeda BR consistente com o resto do projeto (`R$ 1.234,56`, mesmo padrão de `formatar_moeda()` em `app.py`).

---

## Task 1: Módulo `exposicao.py` — motor de sinais

**Files:**
- Create: `exposicao.py`

**Interfaces:**
- Produces: `gerar_sinais_exposicao(df_carteira: pd.DataFrame, df_indicadores: pd.DataFrame, df_dolar: pd.DataFrame) -> list[dict]`, onde cada dict tem as chaves `indexador`, `direcao`, `valor_exposto`, `variavel_gatilho`, `delta`, `sentido_impacto` (`"favoravel"` | `"desfavoravel"` | `"neutro"`), `texto`.
- Produces: `resumo_exposicao_por_indexador(df_carteira: pd.DataFrame) -> pd.Series` (índice = indexador, valor = soma de `tamanho`).
- Consumes: `df_carteira` no formato de `carteira.ler_carteira()` (colunas `id, ativo, descricao, direcao, indexador, tamanho`); `df_indicadores` no formato da tabela `indicadores_bcb` (colunas `indicador, data, valor`); `df_dolar` no formato da tabela `usd_brl` (colunas `date, close`).

- [ ] **Step 1: Escrever o teste (bloco de asserts) antes da implementação**

Criar `exposicao.py` com apenas o import e o bloco de teste, chamando funções que ainda não existem:

```python
"""
exposicao.py - Gera sinais cruzando a exposicao da carteira do usuario com os
indicadores macro que o MIH ja coleta (Selic, IPCA, USD/BRL).

Funcoes puras, sem efeito colateral (mesmo padrao de analises.py): apenas leem
os DataFrames recebidos e devolvem estruturas de dados. Nenhuma leitura de
banco ou escrita acontece aqui - quem chama e' responsavel por montar os
DataFrames (app.py e briefing.py ja tem esses dados carregados).
"""
import pandas as pd


if __name__ == "__main__":
    # Caso 1: carteira vazia -> nenhum sinal
    carteira_vazia = pd.DataFrame(columns=["id", "ativo", "descricao", "direcao", "indexador", "tamanho"])
    indicadores_ok = pd.DataFrame({
        "indicador": ["Selic", "Selic", "IPCA", "IPCA"],
        "data": pd.to_datetime(["2026-08-01", "2026-08-15", "2026-07-01", "2026-08-01"]),
        "valor": [10.50, 10.75, 0.30, 0.45],
    })
    dolar_ok = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-27", "2026-08-28"]),
        "close": [5.40, 5.43],
    })
    assert gerar_sinais_exposicao(carteira_vazia, indicadores_ok, dolar_ok) == []
    print("[OK] Caso 1: carteira vazia -> sem sinais.")

    # Caso 2: indicador com uma unica leitura -> sem sinal para esse indexador
    carteira_cdi = pd.DataFrame([
        {"id": 1, "ativo": "CDB Banco X", "descricao": "", "direcao": "long", "indexador": "CDI", "tamanho": 10000.0},
    ])
    indicadores_uma_leitura = pd.DataFrame({
        "indicador": ["Selic"],
        "data": pd.to_datetime(["2026-08-15"]),
        "valor": [10.75],
    })
    assert gerar_sinais_exposicao(carteira_cdi, indicadores_uma_leitura, dolar_ok) == []
    print("[OK] Caso 2: indicador com 1 leitura -> sem sinal.")

    # Caso 3: CDI (long) e Prefixado (long) reagem em sentidos opostos ao mesmo delta de Selic
    carteira_mista = pd.DataFrame([
        {"id": 1, "ativo": "CDB Banco X", "descricao": "", "direcao": "long", "indexador": "CDI", "tamanho": 10000.0},
        {"id": 2, "ativo": "Tesouro Prefixado", "descricao": "", "direcao": "long", "indexador": "Prefixado", "tamanho": 5000.0},
    ])
    sinais = gerar_sinais_exposicao(carteira_mista, indicadores_ok, dolar_ok)
    por_indexador = {s["indexador"]: s for s in sinais}
    assert por_indexador["CDI"]["sentido_impacto"] == "favoravel"
    assert por_indexador["Prefixado"]["sentido_impacto"] == "desfavoravel"
    assert sinais[0]["indexador"] == "Prefixado"  # desfavoravel vem primeiro
    print("[OK] Caso 3: CDI e Prefixado reagem em sentidos opostos ao mesmo delta de Selic.")

    # Caso 4: posicao short inverte o sentido do impacto
    carteira_short = pd.DataFrame([
        {"id": 1, "ativo": "Hedge dolar", "descricao": "", "direcao": "short", "indexador": "Dólar", "tamanho": 20000.0},
    ])
    sinal_dolar = gerar_sinais_exposicao(carteira_short, indicadores_ok, dolar_ok)[0]
    assert sinal_dolar["sentido_impacto"] == "desfavoravel"  # dolar subiu, posicao short perde
    print("[OK] Caso 4: posicao short inverte o sentido do impacto.")

    # Caso 5: resumo_exposicao_por_indexador agrega por indexador
    resumo = resumo_exposicao_por_indexador(carteira_mista)
    assert resumo["CDI"] == 10000.0
    assert resumo["Prefixado"] == 5000.0
    assert resumo_exposicao_por_indexador(carteira_vazia).empty
    print("[OK] Caso 5: resumo_exposicao_por_indexador agrega corretamente.")

    print("\nTodos os casos passaram.")
```

- [ ] **Step 2: Rodar para confirmar que falha**

Run: `python exposicao.py`
Expected: `NameError: name 'gerar_sinais_exposicao' is not defined` (a função ainda não existe).

- [ ] **Step 3: Implementar o mínimo necessário**

Inserir o código abaixo entre o `import pandas as pd` e o bloco `if __name__ == "__main__":`:

```python
# indexador da carteira -> (nome da serie gatilho, sinal para posicao "long")
# sinal = +1: delta positivo do gatilho favorece quem esta "long" nesse indexador.
# sinal = -1: delta positivo do gatilho prejudica quem esta "long" (ex.: Prefixado
# perde valor de marcacao quando a Selic sobe).
REGRAS_INDEXADOR = {
    "CDI": ("Selic", 1),
    "Prefixado": ("Selic", -1),
    "IPCA": ("IPCA", 1),
    "Dólar": ("Dólar", 1),
}

UNIDADE_GATILHO = {
    "Selic": "p.p.",
    "IPCA": "p.p.",
    "Dólar": "R$",
}


def _formatar_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def _formatar_delta(gatilho, delta):
    if UNIDADE_GATILHO.get(gatilho) == "R$":
        sinal = "+" if delta >= 0 else "-"
        return f"{sinal}{_formatar_moeda(abs(delta))}"
    return f"{delta:+.2f} p.p."


def _calcular_deltas(df_indicadores, df_dolar):
    """Delta = ultima leitura - leitura imediatamente anterior, por serie.
    Series com menos de 2 leituras nao entram no dict (sem dado suficiente)."""
    deltas = {}

    if df_indicadores is not None and not df_indicadores.empty:
        for nome in ("Selic", "IPCA"):
            serie = df_indicadores[df_indicadores["indicador"] == nome].sort_values("data")
            if len(serie) >= 2:
                valores = serie["valor"].tolist()
                deltas[nome] = valores[-1] - valores[-2]

    if df_dolar is not None and len(df_dolar) >= 2:
        serie = df_dolar.sort_values("date")
        valores = serie["close"].tolist()
        deltas["Dólar"] = valores[-1] - valores[-2]

    return deltas


def _montar_texto(indexador, direcao, valor_exposto, gatilho, delta, sentido_impacto):
    verbo = {"favoravel": "favorece", "desfavoravel": "pressiona", "neutro": "não afeta"}[sentido_impacto]
    return (
        f"{gatilho} variou {_formatar_delta(gatilho, delta)} -> {verbo} "
        f"{_formatar_moeda(valor_exposto)} em {indexador} ({direcao})"
    )


def gerar_sinais_exposicao(df_carteira, df_indicadores, df_dolar):
    """Cruza a exposicao da carteira (por indexador/direcao) com os ultimos
    movimentos macro coletados. Devolve lista de sinais ordenada com os
    desfavoraveis primeiro. Nunca inventa sinal quando falta leitura anterior."""
    if df_carteira is None or df_carteira.empty:
        return []

    df = df_carteira.copy()
    df["indexador"] = df["indexador"].astype(str).str.strip()
    df["direcao"] = df["direcao"].astype(str).str.lower().str.strip()
    agrupado = df.groupby(["indexador", "direcao"], as_index=False)["tamanho"].sum()

    deltas = _calcular_deltas(df_indicadores, df_dolar)
    sinais = []

    for _, linha in agrupado.iterrows():
        indexador = linha["indexador"]
        direcao = linha["direcao"]
        valor_exposto = float(linha["tamanho"])

        regra = REGRAS_INDEXADOR.get(indexador)
        if regra is None:
            continue  # Bolsa, N/A ou indexador sem gatilho macro conhecido

        gatilho, sinal_long = regra
        delta = deltas.get(gatilho)
        if delta is None:
            continue  # sem leitura anterior suficiente: nao gera sinal

        sinal_direcao = 1 if direcao == "long" else -1
        impacto = sinal_long * sinal_direcao * delta
        if impacto > 0:
            sentido_impacto = "favoravel"
        elif impacto < 0:
            sentido_impacto = "desfavoravel"
        else:
            sentido_impacto = "neutro"

        sinais.append({
            "indexador": indexador,
            "direcao": direcao,
            "valor_exposto": valor_exposto,
            "variavel_gatilho": gatilho,
            "delta": delta,
            "sentido_impacto": sentido_impacto,
            "texto": _montar_texto(indexador, direcao, valor_exposto, gatilho, delta, sentido_impacto),
        })

    ordem = {"desfavoravel": 0, "neutro": 1, "favoravel": 2}
    sinais.sort(key=lambda s: ordem.get(s["sentido_impacto"], 1))
    return sinais


def resumo_exposicao_por_indexador(df_carteira):
    """Soma de `tamanho` agrupada por indexador, para o grafico de breakdown."""
    if df_carteira is None or df_carteira.empty:
        return pd.Series(dtype=float)
    df = df_carteira.copy()
    df["indexador"] = df["indexador"].astype(str).str.strip()
    return df.groupby("indexador")["tamanho"].sum()
```

- [ ] **Step 4: Rodar para confirmar que passa**

Run: `python exposicao.py`
Expected: as 5 linhas `[OK] Caso N: ...` impressas em ordem, seguidas de `Todos os casos passaram.`, sem `AssertionError` nem traceback.

- [ ] **Step 5: Commit**

```bash
git add exposicao.py
git commit -m "feat: adicionar motor de sinais de exposicao da carteira"
```

---

## Task 2: Integrar sinais de exposição na aba Resumo (`app.py`)

**Files:**
- Modify: `app.py:1-9` (imports)
- Modify: `app.py:230-232` (bloco de dados carregados no topo do arquivo, logo após o try/except de `deb`)
- Modify: `app.py:269-273` (corpo do `overview_tab`, removendo as 4 métricas soltas)

**Interfaces:**
- Consumes: `gerar_sinais_exposicao(df_carteira, df_indicadores, df_dolar) -> list[dict]` e `resumo_exposicao_por_indexador(df_carteira) -> pd.Series`, de `exposicao.py` (Task 1); `ler_carteira() -> pd.DataFrame`, já existente em `carteira.py`; `ind` (DataFrame de `indicadores_bcb`) e `dolar` (DataFrame de `usd_brl`), já carregados em `app.py`.

- [ ] **Step 1: Adicionar o import no topo do arquivo**

Em `app.py`, logo abaixo de `from modules.opcoes.view_opcoes import render_aba_opcoes` (linha 9):

```python
from exposicao import gerar_sinais_exposicao, resumo_exposicao_por_indexador
```

- [ ] **Step 2: Carregar a carteira no bloco de dados compartilhados**

Em `app.py`, logo após o bloco `try/except` que monta `deb` (depois da linha `deb = pd.DataFrame()` do `except`, antes do comentário `# Helpers de download`), adicionar:

```python
try:
    from carteira import ler_carteira
    carteira_df = ler_carteira()
except Exception:
    carteira_df = pd.DataFrame(columns=["id", "ativo", "descricao", "direcao", "indexador", "tamanho"])
```

- [ ] **Step 3: Redesenhar o bloco final do `overview_tab`**

Substituir estas 5 linhas (as métricas soltas de Selic/IPCA/IGP-M/Dólar no `overview_tab`):

```python
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Selic", f"{ultimo_valor('Selic'):.2f}%")
    c2.metric("IPCA", f"{ultimo_valor('IPCA'):.2f}%")
    c3.metric("IGP-M", f"{ultimo_valor('IGP-M'):.2f}%")
    c4.metric("Dólar", formatar_moeda(float(dolar["close"].iloc[-1]) if not dolar.empty else 0))
```

por:

```python
    st.markdown("**Exposição da carteira**")
    resumo_exposicao = resumo_exposicao_por_indexador(carteira_df)
    if resumo_exposicao.empty:
        st.info("Carteira vazia, sem sinais a mostrar.")
    else:
        st.bar_chart(resumo_exposicao)

        st.markdown("**Sinais do dia**")
        sinais = gerar_sinais_exposicao(carteira_df, ind, dolar)
        if not sinais:
            st.caption("Sem sinais no momento (dados insuficientes para calcular variação).")
        else:
            badges = {"desfavoravel": "🔴", "favoravel": "🟢", "neutro": "⚪"}
            for sinal in sinais:
                st.markdown(f"{badges[sinal['sentido_impacto']]} {sinal['texto']}")
```

(As métricas de Selic/IPCA/IGP-M/Dólar continuam disponíveis na aba Macro, que já as exibe.)

- [ ] **Step 4: Verificar manualmente**

Run: `python -m streamlit run app.py`

No navegador, na aba "Resumo", confirmar:
- Se a carteira (aba Carteira) tiver ao menos uma posição com indexador `CDI`, `Prefixado`, `IPCA` ou `Dólar`: aparece um gráfico de barras "Exposição da carteira" e, abaixo, a lista "Sinais do dia" com os itens 🔴 (desfavorável) antes dos 🟢 (favorável).
- Com a carteira vazia (remover todas as posições na aba Carteira e salvar): a aba Resumo mostra "Carteira vazia, sem sinais a mostrar." sem traceback no terminal.
- A aba Macro continua mostrando as métricas de Selic/IPCA/IGP-M/Dólar normalmente (nada quebrou lá).

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: exibir sinais de exposicao da carteira na aba Resumo"
```

---

## Task 3: Injetar sinais de exposição no contexto do briefing (`briefing.py`)

**Files:**
- Modify: `briefing.py:16-21` (bloco de injeção de contexto da carteira)

**Interfaces:**
- Consumes: `gerar_sinais_exposicao(df_carteira, df_indicadores, df_dolar) -> list[dict]`, de `exposicao.py` (Task 1); `ler_carteira()`, de `carteira.py`; `engine`, de `db.py` (já importado em `briefing.py`).

- [ ] **Step 1: Adicionar o bloco de injeção logo após o contexto da carteira**

Em `briefing.py`, logo após este bloco existente:

```python
# Injetar contexto da carteira do usuario
try:
    from carteira import gerar_contexto_carteira
    contexto += "\n\n" + gerar_contexto_carteira()
except Exception:
    pass
```

adicionar:

```python
# Injetar sinais de exposicao (carteira x indicadores macro)
try:
    from exposicao import gerar_sinais_exposicao
    from carteira import ler_carteira

    indicadores_df = pd.read_sql("SELECT * FROM indicadores_bcb", engine)
    dolar_df = pd.read_sql("SELECT * FROM usd_brl ORDER BY date", engine)
    carteira_df = ler_carteira()

    sinais = gerar_sinais_exposicao(carteira_df, indicadores_df, dolar_df)
    if sinais:
        contexto += "\n\nSinais de exposição da carteira:\n" + "\n".join(f"- {s['texto']}" for s in sinais)
except Exception:
    pass
```

- [ ] **Step 2: Verificar manualmente**

Run: `python briefing.py`

Confirmar no console:
- Nenhum traceback é lançado antes da etapa "a IA escreve o briefing" (ou seja, o bloco novo não quebra o script mesmo se a carteira estiver vazia ou algum indicador faltar).
- Se houver `GEMINI_API_KEY` configurada no `.env`: o texto do briefing impresso pode citar a exposição da carteira (ex.: menção a CDI/Prefixado/Selic). Isso é best-effort — a IA pode ou não usar a informação no texto final; o que importa é que o contexto foi montado sem erro.

- [ ] **Step 3: Commit**

```bash
git add briefing.py
git commit -m "feat: incluir sinais de exposicao da carteira no contexto do briefing"
```

---

## Self-Review

**Spec coverage:**
- Seção 3 (modelo de sinal, regras de indexador, janela de comparação, ordenação) → Task 1.
- Seção 4 (integração aditiva app.py/briefing.py) → Tasks 2 e 3.
- Seção 4 UI (breakdown + lista de sinais na aba Resumo, remoção das métricas soltas) → Task 2.
- Seção 5 (erros e casos vazios: sem leitura anterior, carteira vazia) → cobertos pelos Casos 1 e 2 do teste da Task 1, e pela mensagem "Carteira vazia, sem sinais a mostrar." na Task 2.
- Seção 6 (teste via assert em `if __name__`) → Task 1, Steps 1-4.

**Placeholder scan:** nenhum "TBD"/"TODO" — todos os steps têm código completo.

**Type consistency:** `gerar_sinais_exposicao` e `resumo_exposicao_por_indexador` usados com a mesma assinatura em Task 1 (definição), Task 2 (`app.py`) e Task 3 (`briefing.py`). Chaves do dict de sinal (`indexador`, `direcao`, `valor_exposto`, `variavel_gatilho`, `delta`, `sentido_impacto`, `texto`) usadas de forma consistente em todas as tasks.
