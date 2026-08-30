# Reposicionamento do MIH + Integração Carteira → Opções Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reposicionar o MIH como ferramenta quantitativa profissional (Opções B3 como módulo principal, demais módulos como base analítica) e fazer a carteira do usuário alimentar de fato o motor de Opções: universo de coleta dinâmico + sugestões de hedge dimensionadas.

**Architecture:** Duas frentes independentes: (1) edição de conteúdo em 3 docs (`HANDOFF.md`, `ROADMAP.md`, `modules/opcoes/ROADMAP_MIH_Opcoes_Handoff.md`), sem código; (2) duas novas funções puras (`ativos_da_carteira()` em `coleta_opcoes.py`, `sugerir_hedge()` em `analises_opcoes.py`) mais a integração aditiva na UI (`view_opcoes.py`/`paginas/opcoes.py`). O screener/ranking de Opções existente não muda de comportamento.

**Tech Stack:** Python, pandas, SQLAlchemy (`db.engine`), Streamlit, `re` (regex de ticker B3).

**Spec:** [docs/superpowers/specs/2026-08-30-reposicionamento-e-hedge-carteira-design.md](../specs/2026-08-30-reposicionamento-e-hedge-carteira-design.md)

## Global Constraints

- O screener/ranking genérico de Opções (`analisar()`, aba "Ranking") continua exatamente como está — aponta oportunidades em qualquer ativo coletado, com ou sem posição na carteira. Nenhuma task pode fazer esse comportamento depender de uma posição existir na carteira.
- `tamanho` na tabela `carteira` é valor em R$, não quantidade de ações — todo dimensionamento passa por `quantidade_acoes = tamanho / spot`.
- Lote-padrão B3 = 100 ações por contrato de opção.
- Se o dimensionamento resultar em menos de 1 contrato, a função retorna uma observação explícita — nunca sugere 0 contratos como se fosse uma recomendação.
- Toda saída de `sugerir_hedge()` inclui o disclaimer padrão do módulo: "apoio à decisão e estudo quantitativo — NÃO constitui recomendação de investimento".
- Sem framework de teste automatizado no projeto: `assert`s em `if __name__ == "__main__":`, mesmo padrão de `exposicao.py`/`analises.py`/`carteira.py`.
- Ticker da carteira sem dados de opções coletados (comum no plano gratuito da brapi, que só cobre PETR4) → UI mostra nota explícita ("sem dados de opções disponíveis... requer plano Pro"), nunca quebra nem omite silenciosamente.
- Nenhuma assinatura de função existente muda de forma incompatível — `render_aba_opcoes()` ganha um parâmetro novo com default `None` (backward compatible).

---

## Task 1: Reposicionamento — edições de conteúdo (docs)

**Files:**
- Modify: `HANDOFF.md` (seções 0, 1, 2)
- Modify: `ROADMAP.md` (seção "Estrela-guia", nova seção "Visão futura condicional")
- Modify: `modules/opcoes/ROADMAP_MIH_Opcoes_Handoff.md` (seção 8, 2 bullets)

**Interfaces:** nenhuma — esta task é conteúdo, não código. Não bloqueia nem é bloqueada pelas Tasks 2-4.

- [ ] **Step 1: Editar `HANDOFF.md` seção 0**

Substituir:

```markdown
## 0. COMO USAR ESTE DOCUMENTO (instruções à IA)
Você é um **mentor de programação e mercados financeiros**. Seu papel NÃO é entregar
soluções prontas — é ENSINAR o usuário a construir. Siga rigorosamente a metodologia
da seção 2. O usuário (Alisson) está aprendendo do zero; a didática importa tanto
quanto o código.
```

por:

```markdown
## 0. COMO USAR ESTE DOCUMENTO (instruções à IA)
O MIH é uma **ferramenta quantitativa profissional** para uso próprio — não um
exercício de aprendizado nem uma peça de portfólio. Priorize entrega direta e
rigor técnico sobre explicação didática passo a passo. Siga a metodologia da
seção 2 (o que continua valendo: incremental, testável, bem documentado), mas
sem pausas pedagógicas desnecessárias — o usuário já conhece o projeto.
```

- [ ] **Step 2: Editar `HANDOFF.md` seção 1**

Substituir:

```markdown
## 1. PERFIL DO USUÁRIO
- **Nome:** Alisson (Francisco Alisson Carvalho Alves).
- **Cargo:** Estagiário — Tesouraria, Itaúsa.
- **Objetivo duplo:** (a) APRENDER (Python, eng. de dados, APIs, banco, IA, mercado,
  macro, Global Markets); (b) construir um PROJETO DE PORTFÓLIO para entrevistas em
  Global Markets, Tesouraria, ALM e Mesa.
- **Ambiente:** Windows, VS Code, Python 3.14 (MUITO recente — atenção a
  incompatibilidades), terminal PowerShell.
- **GitHub:** usuário `AlissonCarvalhoXP`, repo `plataforma-mercado`.
- **Fluxo de trabalho:** lê o chat numa máquina e programa em OUTRA. Transfere código
  via **Google Keep** (texto puro). ⚠️ NUNCA sugerir copiar código via Google Sheets —
  ele corrompe indentação e aspas (causou vários bugs).
```

por:

```markdown
## 1. PERFIL DO USUÁRIO
- **Nome:** Alisson (Francisco Alisson Carvalho Alves).
- **Cargo:** Estagiário — Tesouraria, Itaúsa.
- **Objetivo do projeto:** ferramenta quantitativa profissional para uso próprio
  na análise e recomendação de posições. O módulo de Opções B3
  (`modules/opcoes/`) é o módulo principal neste momento; os demais módulos
  (macro, crédito/debêntures, notícias, carteira) servem de base analítica que
  alimenta suas recomendações e o briefing — não são abas desconectadas.
- **Ambiente:** Windows, VS Code, Python 3.14 (MUITO recente — atenção a
  incompatibilidades), terminal PowerShell.
- **GitHub:** usuário `AlissonCarvalhoXP`, repo `plataforma-mercado`.
- **Fluxo de trabalho:** lê o chat numa máquina e programa em OUTRA. Transfere código
  via **Google Keep** (texto puro). ⚠️ NUNCA sugerir copiar código via Google Sheets —
  ele corrompe indentação e aspas (causou vários bugs).
```

- [ ] **Step 3: Editar `HANDOFF.md` seção 2**

Substituir:

```markdown
## 2. METODOLOGIA (obrigatória — foi o que funcionou)
1. **Incremental e "simplest first":** menor coisa que funciona de ponta a ponta,
   depois expande. Nunca despejar 200 linhas de uma vez.
2. **Explicar o CONCEITO antes do código.**
3. **Um passo por vez.** Esperar o usuário rodar e confirmar antes do próximo.
4. **Fatia vertical** (não construir camada inteira antes de ver algo rodar).
5. Para cada etapa, seguir: ① objetivo ② arquitetura ③ arquivos ④ explicar código
   ⑤ código ⑥ como testar ⑦ melhorias futuras.
6. **Ensinar a depurar** (ler traceback, isolar causa). Erros são aprendizado.
7. **Confirmar fontes/endpoints** (web) ANTES de passar código, pra evitar erro à toa.
8. Tom: mentor, encorajador, celebra marcos, honesto sobre trade-offs.
9. Registrar decisões e marcos (o usuário valoriza commits com boas mensagens).
```

por:

```markdown
## 2. METODOLOGIA (obrigatória — foi o que funcionou)
1. **Incremental e "simplest first":** menor coisa que funciona de ponta a ponta,
   depois expande. Nunca despejar 200 linhas de uma vez sem necessidade.
2. **Fatia vertical** (não construir camada inteira antes de ver algo rodar).
3. **Entrega direta:** vá ao código e ao resultado; explique só o que for
   necessário para uma decisão (trade-off, risco, dado incerto) — não é
   preciso ensinar o conceito antes de cada etapa.
4. **Depuração:** ao investigar um bug, isolar a causa antes de propor a
   correção — não aplicar palpites.
5. **Confirmar fontes/endpoints** (web) ANTES de passar código, pra evitar erro à toa.
6. Registrar decisões e marcos (commits com boas mensagens, specs para mudanças
   arquiteturais).
```

- [ ] **Step 4: Editar `ROADMAP.md`**

Substituir:

```markdown
## 🌟 Estrela-guia
**Briefing matinal automático de câmbio + juros (BR):** dólar, curva DI, Selic,
2–3 manchetes e uma leitura de IA com fontes citadas.
```

por:

```markdown
## 🌟 Estrela-guia
**Motor de recomendação quantitativa de Opções B3**, calibrado por backtest,
que cruza a carteira do usuário (e, no futuro, macro/crédito/notícias) para
sugerir e dimensionar estruturas de hedge e renda — com trilha de expansão
para outros ativos conforme o backtest validar o modelo.

## 🔮 Visão futura condicional
- [ ] **Automação de envio de ordens à corretora** — dependente do sucesso
  contínuo dos backtests do módulo de Opções (`modules/opcoes/`). Não faz
  parte do escopo atual; entra em consideração só quando o histórico de
  backtest justificar a confiança operacional.
```

- [ ] **Step 5: Editar `modules/opcoes/ROADMAP_MIH_Opcoes_Handoff.md` seção 8**

Substituir:

```markdown
## 8. Decisões em aberto (precisam do Francisco)

- **Plano brapi:** ficar no gratuito (só PETR4) ou assinar Pro (todos os ativos + histórico completo)?
- **Universo definitivo de ativos:** PETR4 + ITSA4 + investidas? (depende do Pro)
- **Convenção de dias:** hoje corridos/365 aproximando 252; padronizar para dias úteis B3.
- **Quando polir vs. expandir:** priorizar visual (abas) ou dados (mais ativos/histórico)?
- **Governança:** fluxo de validação das sugestões antes de uso pela mesa.
```

por:

```markdown
## 8. Decisões em aberto (precisam do Francisco)

- **Plano brapi:** ✅ decidido (2026-08-30) — fica no gratuito por agora (só
  PETR4); reavaliar Pro conforme necessidade. Ver
  `docs/superpowers/specs/2026-08-30-reposicionamento-e-hedge-carteira-design.md`.
- **Universo definitivo de ativos:** ✅ resolvido de outra forma — em vez de
  uma lista fixa, o universo agora é dinâmico (`ativos_da_carteira()` em
  `coleta_opcoes.py`): cobre o que estiver na carteira do usuário, mais
  `ATIVOS_PADRAO` como base. Ainda limitado pelo plano brapi gratuito (só
  PETR4 tem dados reais hoje).
- **Convenção de dias:** hoje corridos/365 aproximando 252; padronizar para dias úteis B3.
- **Quando polir vs. expandir:** priorizar visual (abas) ou dados (mais ativos/histórico)?
- **Governança:** fluxo de validação das sugestões antes de uso pela mesa.
```

- [ ] **Step 6: Verificar**

Ler os 3 arquivos editados e confirmar que o texto final é consistente (nenhuma
menção residual a "objetivo duplo"/"portfólio para entrevistas"/"mentor
didático" nos trechos editados) e que os links para o spec (`docs/superpowers/specs/2026-08-30-reposicionamento-e-hedge-carteira-design.md`) existem de fato.

- [ ] **Step 7: Commit**

```bash
git add HANDOFF.md ROADMAP.md modules/opcoes/ROADMAP_MIH_Opcoes_Handoff.md
git commit -m "docs: reposicionar o MIH como ferramenta quantitativa (Opcoes como modulo principal)"
```

---

## Task 2: Universo dinâmico de coleta (`coleta_opcoes.py`)

**Files:**
- Modify: `modules/opcoes/coleta_opcoes.py`

**Interfaces:**
- Produces: `PADRAO_TICKER_B3` (`re.Pattern`, módulo `coleta_opcoes`) — usado pela Task 4 para filtrar linhas da carteira na UI.
- Produces: `_filtrar_tickers_b3(valores: list) -> list[str]` — função pura, testável sem banco.
- Produces: `ativos_da_carteira() -> list[str]` — lê `carteira.ler_carteira()`, nunca levanta exceção.
- Consumes: `carteira.ler_carteira()` (já existe em `carteira.py`, devolve DataFrame com coluna `ativo`).

- [ ] **Step 1: Escrever o teste (assert) antes da implementação**

No final do arquivo `modules/opcoes/coleta_opcoes.py`, substituir o bloco atual:

```python
if __name__ == "__main__":
    main(sys.argv[1:] or None)
```

por (chama uma função que ainda não existe — vai falhar):

```python
if __name__ == "__main__":
    # Auto-teste rapido (o arquivo tambem e um CLI, entao nao ha bloco de teste
    # separado como em exposicao.py/analises.py) - roda antes de coletar de verdade.
    assert _filtrar_tickers_b3(
        ["PETR4", "ITUB4", "CDB Banco X", "USD/BRL", "petr4", "B3SA3"]
    ) == ["B3SA3", "ITUB4", "PETR4"]
    assert _filtrar_tickers_b3([]) == []
    print("[OK] _filtrar_tickers_b3 reconhece tickers B3 e ignora o resto, deduplicando.")

    main(sys.argv[1:] or None)
```

- [ ] **Step 2: Rodar para confirmar que falha**

Run: `python modules\opcoes\coleta_opcoes.py --help` (ou sem argumentos — qualquer
invocação direta do arquivo dispara o bloco `if __name__`)

Expected: `NameError: name '_filtrar_tickers_b3' is not defined`

- [ ] **Step 3: Implementar o mínimo necessário**

No topo do arquivo, substituir:

```python
from __future__ import annotations
import os
import sys
import math
from datetime import date

# permite rodar tanto como módulo quanto script
sys.path.insert(0, os.path.dirname(__file__))
import db_opcoes

BASE = "https://brapi.dev/api"
ATIVOS_PADRAO = ["PETR4"]          # amplie para ITSA4/investidas quando tiver plano Pro
DIAS_ALVO = 35
```

por:

```python
from __future__ import annotations
import os
import re
import sys
import math
from datetime import date
from pathlib import Path

# permite rodar tanto como módulo quanto script
sys.path.insert(0, os.path.dirname(__file__))
import db_opcoes

# repo root, para "from carteira import ler_carteira" (universo dinamico da carteira)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

BASE = "https://brapi.dev/api"
ATIVOS_PADRAO = ["PETR4"]          # amplie para ITSA4/investidas quando tiver plano Pro
DIAS_ALVO = 35
PADRAO_TICKER_B3 = re.compile(r"^[A-Z]{4}\d{1,2}$")
```

Logo antes de `def main(ativos: list[str] | None = None):`, inserir estas duas
funções (e ajustar a primeira linha de `main` conforme mostrado):

```python
def _filtrar_tickers_b3(valores) -> list[str]:
    """Filtra uma lista de valores (ex.: coluna 'ativo' da carteira) para os que
    parecem tickers B3 (4 letras + 1-2 digitos, ex.: PETR4, ITUB4). Deduplica e
    ordena. Ignora tudo que nao bate com o padrao (ex.: 'CDB Banco X', 'USD/BRL')."""
    tickers = set()
    for valor in valores:
        ticker = str(valor).strip().upper()
        if PADRAO_TICKER_B3.match(ticker):
            tickers.add(ticker)
    return sorted(tickers)


def ativos_da_carteira() -> list[str]:
    """Le a tabela carteira do MIH (via carteira.ler_carteira()) e devolve os
    tickers B3 unicos reconhecidos. Nunca levanta excecao: banco indisponivel
    ou carteira vazia devolvem lista vazia."""
    try:
        from carteira import ler_carteira
        df = ler_carteira()
    except Exception:
        return []
    if df is None or df.empty or "ativo" not in df.columns:
        return []
    return _filtrar_tickers_b3(df["ativo"].tolist())


def main(ativos: list[str] | None = None):
    token = _token()
    db_opcoes.init_schema()
    ativos = ativos or sorted(set(ativos_da_carteira()) | set(ATIVOS_PADRAO))
```

(As linhas seguintes de `main` — `print(...)`, o loop `for a in ativos:` —
continuam exatamente como estão hoje, não mudam.)

- [ ] **Step 4: Rodar para confirmar que passa**

Run: `python modules\opcoes\coleta_opcoes.py PETR4`

Expected: a linha `[OK] _filtrar_tickers_b3 reconhece tickers B3 e ignora o resto, deduplicando.`
aparece antes de `Coleta de opções — ...`, sem `AssertionError` nem traceback
(a coleta de PETR4 em si depende de rede/token — o que importa aqui é que o
assert passou e o script prosseguiu).

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/coleta_opcoes.py
git commit -m "feat: adicionar universo dinamico de coleta a partir da carteira"
```

---

## Task 3: Sugestão de hedge dimensionada (`analises_opcoes.py`)

**Files:**
- Modify: `modules/opcoes/analises_opcoes.py`

**Interfaces:**
- Produces: `sugerir_hedge(posicao: dict, ranking: list[dict], spot: float, regime: str) -> dict | None`. Dict de saída: `{"ativo": str, "direcao_posicao": str, "tipo_estrutura": str, "codigo_opcao_sugerida": str | None, "contratos": int, "texto": str}`.
- Consumes: `ranking` no formato de saída de `analisar()` (lista de dicts com chaves `Codigo_Opcao, Tipo, Strike, Data_Vencimento, ..., Moneyness, Score, ...`, já existente neste arquivo); `regime` no formato de saída de `regime_volatilidade()` (`"ALTA" | "BAIXA" | "NEUTRA"`, já existente); `posicao` no formato de uma linha de `carteira.ler_carteira()` (`ativo`, `direcao`, `tamanho`).

- [ ] **Step 1: Escrever o teste (assert) antes da implementação**

No final de `modules/opcoes/analises_opcoes.py` (o arquivo hoje termina em
`regime_volatilidade`, sem bloco `if __name__`), adicionar:

```python
if __name__ == "__main__":
    ranking_exemplo = [
        {"Codigo_Opcao": "PETRC300", "Tipo": "CALL", "Strike": 32.0,
         "Data_Vencimento": "2026-10-16", "Moneyness": "OTM", "Score": 5.0},
        {"Codigo_Opcao": "PETRC310", "Tipo": "CALL", "Strike": 33.0,
         "Data_Vencimento": "2026-10-16", "Moneyness": "OTM", "Score": 8.0},
        {"Codigo_Opcao": "PETRP280", "Tipo": "PUT", "Strike": 28.0,
         "Data_Vencimento": "2026-10-16", "Moneyness": "OTM", "Score": 6.0},
        {"Codigo_Opcao": "PETRP290", "Tipo": "PUT", "Strike": 29.0,
         "Data_Vencimento": "2026-10-16", "Moneyness": "OTM", "Score": 9.0},
    ]
    spot = 30.0
    posicao_long = {"ativo": "PETR4", "direcao": "long", "tamanho": 30000.0}
    posicao_short = {"ativo": "PETR4", "direcao": "short", "tamanho": 30000.0}

    # Caso 1: long + ALTA -> venda coberta de CALL, melhor Score entre as CALLs OTM
    r = sugerir_hedge(posicao_long, ranking_exemplo, spot, "ALTA")
    assert r["tipo_estrutura"] == "venda coberta de CALL"
    assert r["codigo_opcao_sugerida"] == "PETRC310"  # Score 8.0 > 5.0
    assert r["contratos"] == 10  # 30000/30 = 1000 acoes / 100 = 10 contratos
    print("[OK] Caso 1: long + ALTA -> venda coberta de CALL, melhor Score, dimensionado.")

    # Caso 2: long + BAIXA -> protecao via compra de PUT
    r = sugerir_hedge(posicao_long, ranking_exemplo, spot, "BAIXA")
    assert r["tipo_estrutura"] == "proteção via compra de PUT"
    assert r["codigo_opcao_sugerida"] == "PETRP290"  # Score 9.0 > 6.0
    print("[OK] Caso 2: long + BAIXA -> proteção via compra de PUT.")

    # Caso 3: short + ALTA -> venda coberta de PUT
    r = sugerir_hedge(posicao_short, ranking_exemplo, spot, "ALTA")
    assert r["tipo_estrutura"] == "venda coberta de PUT"
    assert r["codigo_opcao_sugerida"] == "PETRP290"
    print("[OK] Caso 3: short + ALTA -> venda coberta de PUT.")

    # Caso 4: short + NEUTRA -> protecao via compra de CALL
    r = sugerir_hedge(posicao_short, ranking_exemplo, spot, "NEUTRA")
    assert r["tipo_estrutura"] == "proteção via compra de CALL"
    assert r["codigo_opcao_sugerida"] == "PETRC310"
    print("[OK] Caso 4: short + NEUTRA -> proteção via compra de CALL.")

    # Caso 5: posicao menor que 1 lote-padrao -> nao sugere 0 contratos, retorna aviso
    posicao_pequena = {"ativo": "PETR4", "direcao": "long", "tamanho": 500.0}
    r = sugerir_hedge(posicao_pequena, ranking_exemplo, spot, "ALTA")
    assert r["contratos"] == 0
    assert r["codigo_opcao_sugerida"] is None
    assert "lote-padrão" in r["texto"]
    print("[OK] Caso 5: posição menor que 1 lote-padrão -> aviso, sem sugestão de 0 contratos.")

    # Caso 6: sem ranking disponivel -> None
    assert sugerir_hedge(posicao_long, [], spot, "ALTA") is None
    print("[OK] Caso 6: sem ranking disponível -> None.")

    print("\nTodos os casos passaram.")
```

- [ ] **Step 2: Rodar para confirmar que falha**

Run: `python modules\opcoes\analises_opcoes.py`
Expected: `NameError: name 'sugerir_hedge' is not defined`

- [ ] **Step 3: Implementar o mínimo necessário**

Inserir este bloco entre `regime_volatilidade()` e o novo `if __name__ ==
"__main__":` do Step 1:

```python
# ---------------- Sugestao de hedge (Fase E — carteira -> Opcoes) ----------------
DISCLAIMER_HEDGE = ("⚠️ Sugestão de apoio à decisão e estudo quantitativo — "
                     "NÃO constitui recomendação de investimento.")

LOTE_PADRAO_B3 = 100

# (direcao da posicao, regime de vol) -> (tipo de estrutura, Tipo de opcao, lado)
REGRAS_HEDGE = {
    ("long", "ALTA"): ("venda coberta de CALL", "CALL", "vender"),
    ("long", "BAIXA"): ("proteção via compra de PUT", "PUT", "comprar"),
    ("long", "NEUTRA"): ("proteção via compra de PUT", "PUT", "comprar"),
    ("short", "ALTA"): ("venda coberta de PUT", "PUT", "vender"),
    ("short", "BAIXA"): ("proteção via compra de CALL", "CALL", "comprar"),
    ("short", "NEUTRA"): ("proteção via compra de CALL", "CALL", "comprar"),
}


def _formatar_moeda(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def sugerir_hedge(posicao: dict, ranking: list[dict], spot: float, regime: str) -> dict | None:
    """Sugere um tipo de estrutura de opcoes (com serie e dimensionamento) para
    uma posicao existente na carteira, cruzando direcao x regime de vol.
    Devolve None se nao houver ranking disponivel para o ativo (sem dados de
    opcoes coletados) ou se a direcao/regime nao forem reconhecidos.

    Nao substitui nem depende do screener/ranking generico (analisar()), que
    continua apontando oportunidades em qualquer ativo, com ou sem posicao."""
    if not ranking or spot <= 0:
        return None

    direcao = str(posicao.get("direcao", "")).strip().lower()
    regra = REGRAS_HEDGE.get((direcao, regime))
    if regra is None:
        return None

    tipo_estrutura, tipo_opcao, lado = regra
    ativo = posicao.get("ativo", "")

    candidatas = [linha for linha in ranking
                  if linha["Tipo"] == tipo_opcao and linha["Moneyness"] == "OTM"]
    if not candidatas:
        return None
    melhor = max(candidatas, key=lambda linha: linha["Score"])

    tamanho = float(posicao.get("tamanho", 0) or 0)
    quantidade_acoes = tamanho / spot
    contratos = int(quantidade_acoes // LOTE_PADRAO_B3)

    if contratos < 1:
        texto = (
            f"Posição de {_formatar_moeda(tamanho)} em {ativo} é menor que 1 "
            f"lote-padrão ({LOTE_PADRAO_B3} ações) ao preço atual "
            f"(R$ {spot:.2f}) — hedge via opções não é viável neste tamanho. "
            f"{DISCLAIMER_HEDGE}"
        )
        return {
            "ativo": ativo, "direcao_posicao": direcao, "tipo_estrutura": tipo_estrutura,
            "codigo_opcao_sugerida": None, "contratos": 0, "texto": texto,
        }

    texto = (
        f"{ativo} ({direcao}, {_formatar_moeda(tamanho)}): {tipo_estrutura} — "
        f"{lado} {contratos} contrato(s) de {melhor['Codigo_Opcao']} "
        f"(strike R$ {melhor['Strike']:.2f}, vencimento {melhor['Data_Vencimento']}). "
        f"{DISCLAIMER_HEDGE}"
    )
    return {
        "ativo": ativo, "direcao_posicao": direcao, "tipo_estrutura": tipo_estrutura,
        "codigo_opcao_sugerida": melhor["Codigo_Opcao"], "contratos": contratos, "texto": texto,
    }
```

- [ ] **Step 4: Rodar para confirmar que passa**

Run: `python modules\opcoes\analises_opcoes.py`
Expected: as 6 linhas `[OK] Caso N: ...` impressas em ordem, seguidas de
`Todos os casos passaram.`, sem `AssertionError` nem traceback.

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/analises_opcoes.py
git commit -m "feat: adicionar sugestao de hedge dimensionada por posicao da carteira"
```

---

## Task 4: Integração na UI (`view_opcoes.py` + `paginas/opcoes.py`)

**Files:**
- Modify: `modules/opcoes/view_opcoes.py`
- Modify: `paginas/opcoes.py`

**Interfaces:**
- Consumes: `PADRAO_TICKER_B3` (Task 2, módulo `coleta_opcoes`); `sugerir_hedge()` (Task 3, módulo `analises_opcoes`); `db_opcoes.read_latest_chain(ativo, db_path) -> (dict | None, list[dict])` (já existe); `carteira.ler_carteira() -> pd.DataFrame` (já existe).
- Produces: `render_aba_opcoes(selic, db_path=None, carteira_df=None)` — assinatura estendida (backward compatible, `carteira_df` tem default `None`).

- [ ] **Step 1: Editar a assinatura e os imports locais de `render_aba_opcoes`**

Em `modules/opcoes/view_opcoes.py`, substituir:

```python
def render_aba_opcoes(selic: float = 0.1415, db_path: str | None = None):
    import streamlit as st
    import pandas as pd
    import plotly.graph_objects as go
    import db_opcoes
    import analises_opcoes as ao
```

por:

```python
def render_aba_opcoes(selic: float = 0.1415, db_path: str | None = None,
                       carteira_df: "pd.DataFrame | None" = None):
    import streamlit as st
    import pandas as pd
    import plotly.graph_objects as go
    import db_opcoes
    import analises_opcoes as ao
    import coleta_opcoes as co
```

- [ ] **Step 2: Adicionar a seção de sugestões de hedge ao final da função**

Substituir o bloco final (o `with aba3:` inteiro) por ele mesmo seguido da
nova seção:

```python
    with aba3:
        st.markdown(f"**Regime de volatilidade: `{regime}`**")
        if regime == "ALTA":
            st.write("IV cara → **vender prêmio**: venda coberta, trava de alta de "
                     "crédito, Iron Condor (theta a favor).")
        elif regime == "BAIXA":
            st.write("IV barata → **comprar volatilidade**: long call/put, straddle, calendar.")
        else:
            st.write("Sem distorção clara → **travas de débito direcionais** ou aguardar assimetria.")
        st.caption(DISCLAIMER)

    # Sugestoes de hedge para a carteira do usuario - secao aditiva, nao
    # substitui nem depende do ranking/screener acima (que continua cobrindo
    # qualquer ativo coletado, com ou sem posicao na carteira).
    if carteira_df is not None and not carteira_df.empty:
        st.markdown("---")
        st.subheader("🛡️ Sugestões de hedge para sua carteira")
        st.caption(DISCLAIMER)

        posicoes_acoes = [
            row for row in carteira_df.to_dict("records")
            if co.PADRAO_TICKER_B3.match(str(row.get("ativo", "")).strip().upper())
        ]
        if not posicoes_acoes:
            st.info("Nenhuma posição em ações reconhecida na carteira.")
        else:
            for posicao in posicoes_acoes:
                ticker = str(posicao["ativo"]).strip().upper()
                posicao_norm = {**posicao, "ativo": ticker}
                und_pos, series_pos = db_opcoes.read_latest_chain(ticker, db_path)
                if not und_pos or not series_pos:
                    st.warning(
                        f"Sem dados de opções disponíveis para {ticker} "
                        "(requer plano Pro da brapi)."
                    )
                    continue
                rank_pos = ao.analisar(und_pos, series_pos, selic=selic)
                regime_pos = ao.regime_volatilidade(series_pos, und_pos["HV_60d"])
                sugestao = ao.sugerir_hedge(posicao_norm, rank_pos, und_pos["Spot"], regime_pos)
                if sugestao is None:
                    st.caption(
                        f"{ticker}: sem sugestão de hedge no momento "
                        f"(regime `{regime_pos}` sem série OTM adequada)."
                    )
                else:
                    st.markdown(f"- {sugestao['texto']}")
```

- [ ] **Step 3: Atualizar `paginas/opcoes.py` para carregar e repassar a carteira**

Substituir o arquivo inteiro:

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

por:

```python
"""
paginas/opcoes.py - Pagina "Opcoes": wrapper fino em torno do modulo de
Opcoes B3 (modules/opcoes), que ja tem sua propria UI Plotly.
"""
from carteira import ler_carteira
from dados_app import carregar_indicadores, ultimo_valor
from modules.opcoes.view_opcoes import render_aba_opcoes


def pagina_opcoes():
    ind = carregar_indicadores()
    carteira_df = ler_carteira()
    render_aba_opcoes(selic=ultimo_valor(ind, "Selic") / 100, carteira_df=carteira_df)
```

- [ ] **Step 4: Verificar (sem browser — adaptação do padrão já usado no plano de `exposicao.py`)**

**A. Checagem de dados reais**, sem depender de UI:

```python
import sys
sys.path.insert(0, "modules/opcoes")
import db_opcoes
import analises_opcoes as ao
import coleta_opcoes as co
from carteira import ler_carteira

carteira_df = ler_carteira()
posicoes_acoes = [
    row for row in carteira_df.to_dict("records")
    if co.PADRAO_TICKER_B3.match(str(row.get("ativo", "")).strip().upper())
]
print("posicoes_acoes:", posicoes_acoes)
for posicao in posicoes_acoes:
    ticker = str(posicao["ativo"]).strip().upper()
    und, series = db_opcoes.read_latest_chain(ticker)
    print(ticker, "dados:", bool(und and series))
    if und and series:
        rank = ao.analisar(und, series, selic=0.14)
        regime = ao.regime_volatilidade(series, und["HV_60d"])
        print(ticker, ao.sugerir_hedge({**posicao, "ativo": ticker}, rank, und["Spot"], regime))
```

Confirmar que roda sem traceback (com a carteira atual — ITUB4/B3SA3 — o
esperado é `dados: False` para ambos, já que só PETR4 tem cadeia real no
plano gratuito; isso deve aparecer como aviso na UI, não como erro).

**B. Checagem de start do Streamlit:**

```
streamlit run app.py --server.headless true
```

em background por ~15s, capturar a saída do console, confirmar que aparece a
mensagem de start do servidor e nenhum traceback. Parar o processo depois.
Deixar explícito no relatório que confirmação visual/browser não foi feita.

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/view_opcoes.py paginas/opcoes.py
git commit -m "feat: plugar sugestoes de hedge da carteira na pagina de Opcoes"
```

---

## Self-Review

**Spec coverage:**
- Seção 2 (reposicionamento/docs) → Task 1.
- Seção 3 (universo dinâmico) → Task 2.
- Seção 4 (sugestão de hedge dimensionada, screener genérico inalterado) → Task 3.
- Seção 4 (integração na UI, nota de "sem dados disponíveis") → Task 4.
- Seção 5 (erros e casos vazios: sem posição reconhecida, sem dados, posição pequena, falha de coleta por ativo) → cobertos nos Steps 3-4 da Task 4 (UI) e nos Casos 5-6 da Task 3 (função).
- Seção 6 (teste via assert) → Tasks 2 e 3.

**Placeholder scan:** nenhum "TBD"/"TODO" — todos os steps têm código ou texto completo.

**Type consistency:** `sugerir_hedge(posicao, ranking, spot, regime) -> dict | None` usado com a mesma assinatura na definição (Task 3) e no consumo (Task 4). `PADRAO_TICKER_B3` e `_filtrar_tickers_b3`/`ativos_da_carteira` definidos na Task 2 e referenciados exatamente pelos mesmos nomes na Task 4 (`co.PADRAO_TICKER_B3`). Chaves do dict de saída de `sugerir_hedge` (`ativo, direcao_posicao, tipo_estrutura, codigo_opcao_sugerida, contratos, texto`) usadas de forma consistente entre Task 3 e Task 4.
