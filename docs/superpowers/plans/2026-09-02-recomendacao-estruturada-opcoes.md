# Recomendação Estruturada de Operações com Opções — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir o rótulo `COMPRAR_VOL`/`VENDER_VOL` por operações completas e executáveis, com risco exato, e quantificar onde o cenário do usuário diverge do que está embutido no preço das opções.

**Architecture:** Dois módulos novos de funções puras (`estruturas_opcoes.py` para o motor de payoff e catálogo declarativo; `distribuicao_opcoes.py` para a distribuição implícita), mais quatro correções em `analises_opcoes.py` e uma tabela nova de cenários. O motor de payoff calcula risco por construção geométrica (payoff é linear por partes, quebras só nos strikes), então extremos e breakevens saem exatos, sem grade aproximada.

**Tech Stack:** Python 3, numpy, scipy.stats, sqlite3, Streamlit. Sem dependências novas.

**Spec:** `docs/superpowers/specs/2026-09-02-recomendacao-estruturada-opcoes-design.md`

## Global Constraints

- **Convenção de testes:** este repositório **não usa pytest** (não há `tests/`, nem `pytest.ini`, nem pytest instalado). Testes são blocos `if __name__ == "__main__":` no próprio módulo, com `assert` e `print("[OK] Caso N: descrição.")`, terminando em `print("\nTodos os casos passaram.")`. Seguir essa convenção; **não** introduzir pytest.
- **Rodar teste de um módulo:** `.venv/Scripts/python.exe modules/opcoes/<modulo>.py`
- **Módulos novos são funções puras:** sem banco, sem rede, sem efeito colateral. Quem chama monta os dados. Mesmo padrão de `exposicao.py`.
- **Isolamento do banco:** `modules/opcoes/` usa SQLite local via `db_opcoes.DB_PATH`, ignorando `DATABASE_URL`. Nunca usar `db.engine` dentro deste módulo.
- **Lote padrão B3:** 100 ações por contrato. Já existe como `LOTE_PADRAO_B3` em `analises_opcoes.py`.
- **Acentuação:** código e comentários em português sem acento (convenção existente do módulo); textos de UI com acento normal.
- **Disclaimer obrigatório:** toda saída de UI mantém o aviso de "apoio à decisão e estudo quantitativo — NÃO constitui recomendação de investimento".

---

### Task 1: Motor de payoff — avaliação em um preço

**Files:**
- Create: `modules/opcoes/estruturas_opcoes.py`
- Test: bloco `if __name__ == "__main__":` no próprio arquivo

**Interfaces:**
- Consumes: nada (primeira tarefa, módulo isolado)
- Produces: `LOTE_PADRAO_B3: int`, `Perna` (dataclass: `lado: str`, `tipo: str`, `strike: float`, `premio: float`, `quantidade: int = 1`, `vencimento: str = ""`), `payoff_perna(perna: Perna, preco: float) -> float` (por ação), `payoff_estrutura(pernas: list[Perna], preco: float, lote: int = LOTE_PADRAO_B3) -> float` (total em reais)

- [ ] **Step 1: Escrever o teste que falha**

Criar `modules/opcoes/estruturas_opcoes.py` contendo apenas o bloco de teste:

```python
if __name__ == "__main__":
    # Trava de alta: compra CALL 30 por R$2,00, vende CALL 35 por R$0,50.
    # Debito liquido de R$1,50 por acao.
    trava = [
        Perna(lado="comprar", tipo="CALL", strike=30.0, premio=2.00),
        Perna(lado="vender", tipo="CALL", strike=35.0, premio=0.50),
    ]

    # Abaixo de 30: as duas viram po, perde o debito inteiro.
    assert payoff_estrutura(trava, 25.0) == -150.0
    # Acima de 35: ganho travado = (35-30-1,50) * 100
    assert payoff_estrutura(trava, 40.0) == 350.0
    # No breakeven: 30 + 1,50
    assert abs(payoff_estrutura(trava, 31.50)) < 1e-9
    print("[OK] Caso 1: payoff da trava de alta bate com os valores de livro-texto.")

    # Perna isolada, por acao (sem lote)
    compra_call = Perna(lado="comprar", tipo="CALL", strike=30.0, premio=2.00)
    assert payoff_perna(compra_call, 33.0) == 1.0     # 3 de intrinseco - 2 de premio
    assert payoff_perna(compra_call, 28.0) == -2.0    # vira po, perde o premio
    venda_put = Perna(lado="vender", tipo="PUT", strike=30.0, premio=1.00)
    assert payoff_perna(venda_put, 32.0) == 1.00      # expira po, embolsa o premio
    assert payoff_perna(venda_put, 27.0) == -2.00     # 3 de intrinseco contra, +1 de premio
    print("[OK] Caso 2: payoff por perna respeita lado e tipo.")

    print("\nTodos os casos passaram.")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `.venv/Scripts/python.exe modules/opcoes/estruturas_opcoes.py`
Expected: FAIL com `NameError: name 'Perna' is not defined`

- [ ] **Step 3: Implementar o mínimo**

Inserir no topo do arquivo, antes do bloco de teste:

```python
"""Motor de payoff e catalogo de estruturas de opcoes.

Funcoes puras: nao le banco, nao acessa rede, nao tem efeito colateral - quem
chama monta os dados (mesmo padrao de exposicao.py e analises.py).

O payoff aqui e' sempre NO VENCIMENTO. Series de estilo americano podem ser
exercidas antes, e dividendos alteram esse incentivo em calls; este modulo nao
afirma qual e' a convencao vigente de cada serie na B3. Risco antes do
vencimento tambem difere: perda maxima no vencimento nao protege de marcacao a
mercado adversa nem de chamada de margem no meio do caminho.

Ver docs/superpowers/specs/2026-09-02-recomendacao-estruturada-opcoes-design.md
"""
from __future__ import annotations
from dataclasses import dataclass

LOTE_PADRAO_B3 = 100


@dataclass(frozen=True)
class Perna:
    """Uma perna de uma estrutura. `quantidade` permite ratio spreads sem
    tratamento especial. `premio` e' o preco observado da opcao, por acao."""
    lado: str          # "comprar" | "vender"
    tipo: str          # "CALL" | "PUT"
    strike: float
    premio: float
    quantidade: int = 1
    vencimento: str = ""


def payoff_perna(perna: Perna, preco: float) -> float:
    """Payoff da perna no vencimento, POR ACAO, ao preco `preco` do ativo."""
    if perna.tipo == "CALL":
        intrinseco = max(preco - perna.strike, 0.0)
    else:
        intrinseco = max(perna.strike - preco, 0.0)
    if perna.lado == "comprar":
        return (intrinseco - perna.premio) * perna.quantidade
    return (perna.premio - intrinseco) * perna.quantidade


def payoff_estrutura(pernas: list[Perna], preco: float,
                     lote: int = LOTE_PADRAO_B3) -> float:
    """Payoff total da estrutura no vencimento, em reais (ja multiplicado
    pelo lote)."""
    return sum(payoff_perna(p, preco) for p in pernas) * lote
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `.venv/Scripts/python.exe modules/opcoes/estruturas_opcoes.py`
Expected: PASS — imprime os dois `[OK]` e "Todos os casos passaram."

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/estruturas_opcoes.py
git commit -m "feat: motor de payoff de estruturas de opcoes (avaliacao em um preco)"
```

---

### Task 2: Perfil de risco — extremos e breakevens exatos

**Files:**
- Modify: `modules/opcoes/estruturas_opcoes.py`

**Interfaces:**
- Consumes: `Perna`, `payoff_estrutura`, `LOTE_PADRAO_B3` (Task 1)
- Produces: `PerfilRisco` (dataclass: `perda_maxima: float | None`, `ganho_maximo: float | None`, `breakevens: list[float]`, `premio_liquido: float`), `perfil_risco(pernas: list[Perna], lote: int = LOTE_PADRAO_B3) -> PerfilRisco`. `None` em perda/ganho significa **ilimitado**. `premio_liquido` positivo = débito pago; negativo = crédito recebido.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao bloco de teste, antes do `print("\nTodos os casos passaram.")`:

```python
    # Caso 3: trava de alta tem os quatro numeros exatos e nada ilimitado
    perfil = perfil_risco(trava)
    assert perfil.perda_maxima == -150.0
    assert perfil.ganho_maximo == 350.0
    assert perfil.breakevens == [31.5]
    assert perfil.premio_liquido == 150.0   # debito de R$1,50/acao * 100
    print("[OK] Caso 3: perfil de risco da trava de alta, com breakeven exato.")

    # Caso 4: venda descoberta de CALL tem perda ILIMITADA, ganho travado no premio
    venda_seca = [Perna(lado="vender", tipo="CALL", strike=35.0, premio=1.20)]
    p_seca = perfil_risco(venda_seca)
    assert p_seca.perda_maxima is None          # ilimitada
    assert p_seca.ganho_maximo == 120.0         # o premio recebido
    assert p_seca.breakevens == [36.2]          # 35 + 1,20
    assert p_seca.premio_liquido == -120.0      # credito
    print("[OK] Caso 4: venda descoberta e' marcada como perda ilimitada.")

    # Caso 5: straddle comprado - dois breakevens, perda maxima no strike
    straddle = [
        Perna(lado="comprar", tipo="CALL", strike=30.0, premio=1.50),
        Perna(lado="comprar", tipo="PUT", strike=30.0, premio=1.00),
    ]
    p_str = perfil_risco(straddle)
    assert p_str.perda_maxima == -250.0         # os dois premios, exatamente no strike
    assert p_str.ganho_maximo is None           # ilimitado pra cima
    assert p_str.breakevens == [27.5, 32.5]     # 30 -/+ 2,50
    print("[OK] Caso 5: straddle comprado tem dois breakevens e ganho ilimitado.")

    # Caso 6: borboleta - risco e ganho ambos travados
    borboleta = [
        Perna(lado="comprar", tipo="CALL", strike=30.0, premio=3.00),
        Perna(lado="vender", tipo="CALL", strike=35.0, premio=1.50, quantidade=2),
        Perna(lado="comprar", tipo="CALL", strike=40.0, premio=0.50),
    ]
    p_bor = perfil_risco(borboleta)
    assert p_bor.perda_maxima is not None and p_bor.ganho_maximo is not None
    assert p_bor.perda_maxima == -50.0          # debito liquido: 3 - 3 + 0,5 = 0,50
    assert p_bor.ganho_maximo == 450.0          # (35-30-0,50) * 100
    print("[OK] Caso 6: borboleta tem perda e ganho ambos limitados.")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `.venv/Scripts/python.exe modules/opcoes/estruturas_opcoes.py`
Expected: FAIL com `NameError: name 'perfil_risco' is not defined`

- [ ] **Step 3: Implementar o mínimo**

Acrescentar após `payoff_estrutura`:

```python
@dataclass(frozen=True)
class PerfilRisco:
    """perda_maxima/ganho_maximo em None significam ILIMITADO (nao zero)."""
    perda_maxima: float | None
    ganho_maximo: float | None
    breakevens: list[float]
    premio_liquido: float   # positivo = debito pago; negativo = credito recebido


def _inclinacao_acima_do_maior_strike(pernas: list[Perna]) -> float:
    """Acima do maior strike, toda call esta' no dinheiro e toda put virou po -
    entao a inclinacao do payoff e' so' a quantidade liquida de calls."""
    total = 0.0
    for p in pernas:
        if p.tipo == "CALL":
            total += p.quantidade if p.lado == "comprar" else -p.quantidade
    return total


def premio_liquido(pernas: list[Perna], lote: int = LOTE_PADRAO_B3) -> float:
    """Positivo = debito pago para montar; negativo = credito recebido."""
    total = 0.0
    for p in pernas:
        sinal = 1.0 if p.lado == "comprar" else -1.0
        total += sinal * p.premio * p.quantidade
    return total * lote


def perfil_risco(pernas: list[Perna], lote: int = LOTE_PADRAO_B3) -> PerfilRisco:
    """Extremos e breakevens EXATOS, sem grade aproximada.

    O payoff combinado no vencimento e' linear por partes, com quebras apenas
    nos strikes. Entao avaliar em 0, em cada strike, e num ponto alem do maior
    strike basta: qualquer extremo esta' num desses pontos, e cada breakeven
    esta' num segmento entre dois deles, onde a interpolacao linear e' exata.

    Abaixo do menor strike o ativo e' limitado por preco >= 0, entao esse lado
    e' sempre finito. So' o lado de cima pode ser ilimitado.
    """
    strikes = sorted({p.strike for p in pernas})
    pontos = [0.0] + strikes + [strikes[-1] * 2 + 10.0]
    valores = [payoff_estrutura(pernas, s, lote) for s in pontos]

    inclinacao = _inclinacao_acima_do_maior_strike(pernas)
    ganho_maximo = None if inclinacao > 0 else max(valores)
    perda_maxima = None if inclinacao < 0 else min(valores)

    breakevens: list[float] = []
    for i in range(len(pontos) - 1):
        v1, v2 = valores[i], valores[i + 1]
        if abs(v1) < 1e-9:
            breakevens.append(round(pontos[i], 4))
        elif v1 * v2 < 0:
            # segmento e' linear, entao o cruzamento do zero e' exato
            x = pontos[i] + (pontos[i + 1] - pontos[i]) * (-v1) / (v2 - v1)
            breakevens.append(round(x, 4))
    if abs(valores[-1]) < 1e-9:
        breakevens.append(round(pontos[-1], 4))

    return PerfilRisco(
        perda_maxima=perda_maxima, ganho_maximo=ganho_maximo,
        breakevens=sorted(set(breakevens)),
        premio_liquido=premio_liquido(pernas, lote),
    )
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `.venv/Scripts/python.exe modules/opcoes/estruturas_opcoes.py`
Expected: PASS — seis casos `[OK]`

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/estruturas_opcoes.py
git commit -m "feat: perfil de risco exato (extremos, breakevens, premio liquido)"
```

---

### Task 3: Score sem liquidez + zona neutra

**Files:**
- Modify: `modules/opcoes/analises_opcoes.py` (função `calcular_score`, função `analisar`, bloco de teste)
- Modify: `modules/opcoes/backtest_opcoes.py` (chamada de `calcular_score` e o score vetorizado do Caso 4)

**Interfaces:**
- Consumes: nada de tarefas anteriores
- Produces: `calcular_score(diff_pp: float, skew_pp: float, peso_diff: float = 0.6, peso_skew: float = 0.6) -> float` (**assinatura nova**: sem `liq` e sem `peso_liq`), `LIMIAR_SINAL_PP: float`, `classificar_sinal(diff_pp: float, skew_pp: float, score: float, limiar: float = LIMIAR_SINAL_PP) -> str` devolvendo `"COMPRAR_VOL"`, `"NEUTRO"` ou `"VENDER_VOL"`

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao bloco de teste de `analises_opcoes.py`, antes do print final:

```python
    # Caso 16: Score nao usa mais liquidez. O termo de liquidez empurrava o
    # Score pra cima so' por a opcao ser negociada (log1p(10000)*0,05 ~ +0,46),
    # o bastante pra inverter o sinal de venda pra compra - liquidez e'
    # qualidade de execucao, nao evidencia de que a vol esta' barata.
    # Alem disso, o backtest sempre mediu a formula SEM liquidez (chamava com
    # liq=0 e peso_liq=0,0): so' agora producao e backtest sao a mesma coisa.
    assert calcular_score(10.0, 0.0) == -6.0            # -10 * 0,6
    assert calcular_score(0.0, 10.0) == -6.0            # -10 * 0,6
    assert calcular_score(-10.0, -10.0) == 12.0         # vol barata nos dois eixos
    print("[OK] Caso 16: Score usa so' Diff e Skew - liquidez saiu da formula.")

    # Caso 17: zona neutra - desvio pequeno nao vira sinal
    assert classificar_sinal(1.0, 0.5, calcular_score(1.0, 0.5)) == "NEUTRO"
    assert classificar_sinal(10.0, 0.0, calcular_score(10.0, 0.0)) == "VENDER_VOL"
    assert classificar_sinal(-10.0, 0.0, calcular_score(-10.0, 0.0)) == "COMPRAR_VOL"
    # basta UM dos eixos passar do limiar
    assert classificar_sinal(0.0, 10.0, calcular_score(0.0, 10.0)) == "VENDER_VOL"
    print("[OK] Caso 17: zona neutra evita rotular desvio irrelevante.")

    # Caso 18: o texto de saida descreve DESVIO OBSERVADO, nunca previsao nem
    # "sinal de compra". O backtest mostrou que o Score nao preve retorno;
    # manter o vocabulario de recomendacao seria prometer o que nao se sustenta.
    linha_texto = {
        "Codigo_Opcao": "PETRA300", "Tipo": "CALL", "Strike": 30.0, "Dias": 25,
        "Preco_Mercado": 1.80, "Justo_BS": 1.50, "Desconto": -0.20,
        "Diff_pp": 9.0, "Skew_pp": 4.0, "Liquidez": 1200,
    }
    saida = _texto_oportunidade(linha_texto, "VENDER_VOL")
    texto_gerado = saida["texto"]
    assert "sinal de" not in texto_gerado.lower()
    assert "recomend" not in texto_gerado.lower()
    assert "acima" in texto_gerado.lower() or "abaixo" in texto_gerado.lower()
    assert "PETRA300" in texto_gerado
    print("[OK] Caso 18: texto descreve desvio observado, sem vocabulario de previsao.")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `.venv/Scripts/python.exe modules/opcoes/analises_opcoes.py`
Expected: FAIL com `TypeError` (assinatura antiga exige `liq`) ou `NameError: name 'classificar_sinal' is not defined`

- [ ] **Step 3: Implementar o mínimo**

Substituir `calcular_score` inteira em `analises_opcoes.py` por:

```python
# Limiar da zona neutra, em pontos de volatilidade. ARBITRARIO e declarado como
# tal: calibra-lo exigiria poder preditivo que o backtest mostrou nao existir
# (ver secao 4.4c do ROADMAP_MIH_Opcoes_Handoff.md). Um numero honestamente
# arbitrario e' preferivel a um numero com aparencia de otimizado.
LIMIAR_SINAL_PP = 3.0


def calcular_score(diff_pp: float, skew_pp: float,
                    peso_diff: float = 0.6, peso_skew: float = 0.6) -> float:
    """Score do screener - positivo: vol parece barata; negativo: parece cara.
    Dois eixos ortogonais:
    - diff_pp: gap entre IV e HV (vol atual vs. vol realizada)
    - skew_pp: gap entre a IV desta opcao e a IV que o sorriso do dia preveria
      pro seu strike

    NAO usa liquidez (removido em 2026-09-02): liquidez e' qualidade de
    execucao, nao evidencia direcional - o termo log1p(liq)*0,05 empurrava o
    Score pra cima so' por a opcao ser negociada, o bastante pra inverter
    sinais. Alem disso, o backtest sempre mediu a formula sem liquidez, entao
    producao e backtest so' passaram a ser a mesma coisa agora.

    NAO usa "desconto" (preco-espaco): e' reexpressao nao-linear do mesmo gap
    que diff_pp mede - Black-Scholes e' monotonico em volatilidade, entao os
    dois sao colineares por construcao. Ver
    docs/superpowers/specs/2026-08-30-score-opcoes-sem-desconto-design.md."""
    return -diff_pp * peso_diff - skew_pp * peso_skew


def classificar_sinal(diff_pp: float, skew_pp: float, score: float,
                       limiar: float = LIMIAR_SINAL_PP) -> str:
    """Tres estados, com zona neutra explicita. Sem ela, o corte em zero
    rotulava TODA linha da cadeia como compra ou venda, inclusive desvios
    irrelevantes. Basta um dos eixos passar do limiar pra virar sinal."""
    if max(abs(diff_pp), abs(skew_pp)) < limiar:
        return "NEUTRO"
    return "COMPRAR_VOL" if score > 0 else "VENDER_VOL"
```

Em `analisar()`, trocar as duas linhas do cálculo:

```python
        score = calcular_score(diff, skew, peso_diff, peso_skew)
        sinal = classificar_sinal(diff, skew, score)
```

Remover o parâmetro `peso_liq` da assinatura de `analisar()` e da sua docstring.

Substituir `_texto_oportunidade` inteira por uma versão que descreve desvio em
vez de prescrever operação:

```python
def _texto_oportunidade(linha: dict, sinal: str) -> dict:
    """Descreve o DESVIO OBSERVADO, nao uma previsao.

    O vocabulario antigo ("sinal de COMPRA de volatilidade") era duplamente
    impreciso: sugeria poder preditivo que o backtest mostrou nao existir (ver
    secao 4.4c do ROADMAP_MIH_Opcoes_Handoff.md), e a operacao implicada - uma
    call solta - carrega delta, ou seja, nao e' exposicao a volatilidade."""
    posicao = "acima" if sinal == "VENDER_VOL" else "abaixo"
    texto = (
        f"{linha['Codigo_Opcao']} ({linha['Tipo']}, strike R$ {linha['Strike']:.2f}, "
        f"vence em {linha['Dias']} dias) — IV {posicao} da referência: "
        f"{linha['Diff_pp']:+.1f}pp vs. HV, {linha['Skew_pp']:+.1f}pp vs. o sorriso "
        f"do dia. Liquidez {linha['Liquidez']}. Desvio de preço observado — "
        f"não é previsão de retorno."
    )
    return {
        "codigo_opcao": linha["Codigo_Opcao"], "tipo": linha["Tipo"],
        "sinal": sinal, "texto": texto,
    }
```

A função `_texto_desconto` deixa de ser usada por `_texto_oportunidade`. Se
nenhum outro ponto do módulo a chamar (conferir com
`grep -n "_texto_desconto" modules/opcoes/*.py`), removê-la junto com o Caso do
bloco de teste que a exercita.

Em `backtest_opcoes.py`, na função `preparar_pontos` não há chamada a mudar; no Caso 4 do bloco de teste, trocar a chamada:

```python
            esperado = calcular_score(diff_, skew_, pd_, ps_)
```

- [ ] **Step 4: Rodar os dois módulos e confirmar que passam**

Run: `.venv/Scripts/python.exe modules/opcoes/analises_opcoes.py`
Expected: PASS — 18 casos

Run: `.venv/Scripts/python.exe modules/opcoes/backtest_opcoes.py --ativo PETR`
Expected: PASS nos 4 casos, e o sweep roda até o fim

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/analises_opcoes.py modules/opcoes/backtest_opcoes.py
git commit -m "fix: tirar liquidez do Score direcional e adicionar zona neutra"
```

---

### Task 4: Sorriso ajustado por vencimento

**Files:**
- Modify: `modules/opcoes/analises_opcoes.py` (função `analisar`)
- Modify: `modules/opcoes/backtest_opcoes.py` (função `_construir_sorrisos_por_dia` e o ponto de consulta em `preparar_pontos`)

**Interfaces:**
- Consumes: `calcular_score`, `classificar_sinal` (Task 3)
- Produces: nenhuma assinatura pública nova; muda a chave interna do dicionário de sorrisos para incluir o vencimento

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao bloco de teste de `analises_opcoes.py`:

```python
    # Caso 19: o sorriso e' ajustado por (Tipo, Vencimento), nao so' por Tipo.
    # A superficie de vol tem estrutura a termo: uma serie de 7 dias e outra de
    # 90 tem niveis de IV sistematicamente diferentes. Juntando as duas na mesma
    # parabola, parte do Skew_pp passa a medir diferenca de PRAZO em vez de
    # desvio de STRIKE - que e' o que ele deveria medir.
    from datetime import date as _date
    hoje_teste = _date(2026, 1, 5)
    underlying_teste = {"Spot": 30.0, "HV_60d": 0.30}
    # Dois vencimentos, cada um com 4 strikes; o curto tem IV bem mais alta
    series_teste = []
    for strike, iv in ((28.0, 0.50), (30.0, 0.48), (32.0, 0.49), (34.0, 0.52)):
        series_teste.append({"Codigo_Opcao": f"CURTA{strike:.0f}", "Tipo": "CALL",
                             "Strike": strike, "Data_Vencimento": "2026-01-16",
                             "Ultimo": 1.20, "IV_Fonte": iv, "Volume": 100})
    for strike, iv in ((28.0, 0.30), (30.0, 0.28), (32.0, 0.29), (34.0, 0.32)):
        series_teste.append({"Codigo_Opcao": f"LONGA{strike:.0f}", "Tipo": "CALL",
                             "Strike": strike, "Data_Vencimento": "2026-04-17",
                             "Ultimo": 2.50, "IV_Fonte": iv, "Volume": 100})

    ranking_teste = analisar(underlying_teste, series_teste, selic=0.12, hoje=hoje_teste)
    por_codigo = {linha["Codigo_Opcao"]: linha for linha in ranking_teste}
    # Cada serie e' comparada ao sorriso do SEU vencimento, entao o Skew fica
    # pequeno nos dois grupos. Com a chave errada (so' Tipo), o grupo curto
    # apareceria ~20pp acima e o longo ~20pp abaixo de um sorriso medio.
    for codigo, linha in por_codigo.items():
        assert abs(linha["Skew_pp"]) < 5.0, (codigo, linha["Skew_pp"])
    print("[OK] Caso 19: sorriso por (Tipo, Vencimento) - nao mistura prazos.")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `.venv/Scripts/python.exe modules/opcoes/analises_opcoes.py`
Expected: FAIL no assert do Caso 19, com `Skew_pp` de magnitude bem maior que 5 (as duas curvas viram uma parábola média)

- [ ] **Step 3: Implementar o mínimo**

Em `analisar()`, trocar a acumulação e o ajuste dos sorrisos. Onde hoje é `pontos_por_tipo` chaveado só por `tipo`, passar a chavear por `(tipo, vencimento)`:

```python
    calculados = []
    pontos_por_chave: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for s in series:
        # ... corpo existente inalterado ate' o calculo de liq ...
        chave_sorriso = (tipo, s["Data_Vencimento"][:10])
        calculados.append((s, mkt, tipo, dias_corridos, T, iv, liq, chave_sorriso))
        pontos_por_chave.setdefault(chave_sorriso, []).append((s["Strike"], iv))

    # Sorriso por (Tipo, Vencimento): a superficie de vol tem estrutura a termo,
    # entao juntar prazos diferentes na mesma parabola faz o Skew_pp medir
    # diferenca de prazo em vez de desvio de strike.
    sorrisos = {chave: ajustar_sorriso(pontos)
                for chave, pontos in pontos_por_chave.items()}
```

E na segunda passada, desempacotar a chave e usá-la:

```python
    for s, mkt, tipo, dias_corridos, T, iv, liq, chave_sorriso in calculados:
        # ... calculo de justo/delta/desconto/diff inalterado ...
        sorriso = sorrisos.get(chave_sorriso)
```

Em `backtest_opcoes.py`, acrescentar `Data_Vencimento` à chave de `_construir_sorrisos_por_dia`:

```python
            chave = (h["Data"], h.get("Tipo", "CALL"), h.get("Ativo_Objeto"),
                     h.get("Data_Vencimento"))
```

e no ponto de consulta dentro de `preparar_pontos`:

```python
            sorriso = sorrisos.get((p["Data"], p.get("Tipo", "CALL"),
                                    p.get("Ativo_Objeto"), p.get("Data_Vencimento")))
```

Atualizar a docstring de `_construir_sorrisos_por_dia` para citar o vencimento na chave, e ajustar o Caso 3 do bloco de teste do backtest, que hoje usa chave de 3 elementos:

```python
    assert ("2026-01-05", "CALL", "AAAA", "2026-02-20") in sorrisos_teste
```

acrescentando `"Data_Vencimento": "2026-02-20"` a cada um dos 8 dicionários de `hist_dois_ativos`, e trocando a asserção da chave antiga por:

```python
    assert ("2026-01-05", "CALL", "AAAA") not in sorrisos_teste  # chave sem vencimento nao existe mais
    iv_ajustada_aaaa = sorrisos_teste[("2026-01-05", "CALL", "AAAA", "2026-02-20")](11.5)
```

- [ ] **Step 4: Rodar os dois módulos e confirmar que passam**

Run: `.venv/Scripts/python.exe modules/opcoes/analises_opcoes.py`
Expected: PASS — 19 casos

Run: `.venv/Scripts/python.exe modules/opcoes/backtest_opcoes.py --ativo PETR`
Expected: PASS nos 4 casos

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/analises_opcoes.py modules/opcoes/backtest_opcoes.py
git commit -m "fix: ajustar sorriso por (Tipo, Vencimento) em vez de so' por Tipo"
```

---

### Task 5: Escada de strikes e seletores

**Files:**
- Modify: `modules/opcoes/estruturas_opcoes.py`

**Interfaces:**
- Consumes: `Perna` (Task 1)
- Produces: `escada_strikes(cadeia: list[dict], tipo: str, vencimento: str) -> list[float]` (strikes distintos, ordenados), `selecionar_strike(escada: list[float], spot: float, seletor: str, tipo: str) -> float | None` aceitando `"ATM"`, `"OTM1"`, `"OTM2"`, `"OTM3"`, `"ITM1"`, `"ITM2"`. Devolve `None` quando o seletor não existe na escada.

**Nota sobre semântica:** OTM/ITM dependem do tipo. Para CALL, OTM é acima do spot; para PUT, abaixo. Por isso `selecionar_strike` recebe a escada **já filtrada por tipo** e o parâmetro `tipo` é embutido na direção — ver implementação.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao bloco de teste de `estruturas_opcoes.py`:

```python
    # Caso 7: escada de strikes sai ordenada, sem repetir, filtrada por
    # tipo e vencimento
    cadeia_teste = [
        {"Tipo": "CALL", "Strike": 32.0, "Data_Vencimento": "2026-02-20"},
        {"Tipo": "CALL", "Strike": 30.0, "Data_Vencimento": "2026-02-20"},
        {"Tipo": "CALL", "Strike": 34.0, "Data_Vencimento": "2026-02-20"},
        {"Tipo": "CALL", "Strike": 30.0, "Data_Vencimento": "2026-02-20"},  # repetido
        {"Tipo": "PUT",  "Strike": 28.0, "Data_Vencimento": "2026-02-20"},
        {"Tipo": "CALL", "Strike": 99.0, "Data_Vencimento": "2026-03-20"},  # outro venc.
    ]
    esc = escada_strikes(cadeia_teste, "CALL", "2026-02-20")
    assert esc == [30.0, 32.0, 34.0]
    print("[OK] Caso 7: escada de strikes ordenada, sem repeticao, filtrada.")

    # Caso 8: seletores indexam a escada real (nao usam delta - delta dependeria
    # de qual vol alimenta o modelo; indice na escada e' verificavel por
    # inspecao e nao carrega premissa)
    assert selecionar_strike(esc, spot=30.4, seletor="ATM", tipo="CALL") == 30.0
    assert selecionar_strike(esc, spot=30.4, seletor="OTM1", tipo="CALL") == 32.0
    assert selecionar_strike(esc, spot=30.4, seletor="OTM2", tipo="CALL") == 34.0
    assert selecionar_strike(esc, spot=30.4, seletor="OTM3", tipo="CALL") is None
    # pra PUT, OTM e' pra BAIXO do spot
    esc_put = [26.0, 28.0, 30.0, 32.0]
    assert selecionar_strike(esc_put, spot=30.2, seletor="ATM", tipo="PUT") == 30.0
    assert selecionar_strike(esc_put, spot=30.2, seletor="OTM1", tipo="PUT") == 28.0
    assert selecionar_strike(esc_put, spot=30.2, seletor="ITM1", tipo="PUT") == 32.0
    print("[OK] Caso 8: seletores respeitam a direcao de OTM/ITM por tipo.")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `.venv/Scripts/python.exe modules/opcoes/estruturas_opcoes.py`
Expected: FAIL com `NameError: name 'escada_strikes' is not defined`

- [ ] **Step 3: Implementar o mínimo**

Acrescentar a `estruturas_opcoes.py`:

```python
def escada_strikes(cadeia: list[dict], tipo: str, vencimento: str) -> list[float]:
    """Strikes distintos e ordenados que realmente existem na cadeia para
    aquele tipo e vencimento."""
    return sorted({
        float(linha["Strike"]) for linha in cadeia
        if linha.get("Tipo") == tipo
        and str(linha.get("Data_Vencimento", ""))[:10] == vencimento[:10]
    })


def selecionar_strike(escada: list[float], spot: float, seletor: str,
                       tipo: str) -> float | None:
    """Indexa a escada de strikes REAL, em vez de selecionar por delta.

    Delta dependeria de qual volatilidade alimenta o modelo; indice sobre a
    cadeia listada e' verificavel por inspecao e nao carrega premissa nenhuma.

    ATM = strike mais proximo do spot. OTM anda no sentido de "sem valor
    intrinseco" (pra cima em CALL, pra baixo em PUT); ITM no sentido oposto.
    Devolve None quando o degrau pedido nao existe na cadeia."""
    if not escada:
        return None
    atm = min(escada, key=lambda k: abs(k - spot))
    indice_atm = escada.index(atm)

    if seletor == "ATM":
        return atm
    if len(seletor) < 4:
        return None
    direcao_texto, passo_texto = seletor[:3], seletor[3:]
    if not passo_texto.isdigit():
        return None
    passo = int(passo_texto)

    if direcao_texto == "OTM":
        deslocamento = passo if tipo == "CALL" else -passo
    elif direcao_texto == "ITM":
        deslocamento = -passo if tipo == "CALL" else passo
    else:
        return None

    indice = indice_atm + deslocamento
    if 0 <= indice < len(escada):
        return escada[indice]
    return None
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `.venv/Scripts/python.exe modules/opcoes/estruturas_opcoes.py`
Expected: PASS — oito casos

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/estruturas_opcoes.py
git commit -m "feat: escada de strikes e seletores indexados na cadeia real"
```

---

### Task 6: Catálogo declarativo e montagem com viabilidade

**Files:**
- Modify: `modules/opcoes/estruturas_opcoes.py`

**Interfaces:**
- Consumes: `Perna`, `perfil_risco`, `escada_strikes`, `selecionar_strike` (Tasks 1, 2, 5)
- Produces: `CATALOGO: list[DeclaracaoEstrutura]`, `DeclaracaoEstrutura` (dataclass: `nome: str`, `tese_vol: str`, `tese_direcao: str`, `pernas: tuple[tuple[str, str, str, int], ...]` onde cada tupla é `(lado, tipo, seletor, quantidade)`), `EstruturaMontada` (dataclass: `nome: str`, `pernas: list[Perna]`, `perfil: PerfilRisco`), `montar_estruturas(cadeia, spot, vencimento, tese_vol, tese_direcao, liquidez_min=0, tem_posicao=False) -> tuple[list[EstruturaMontada], list[str]]` devolvendo as montadas e a lista de motivos das recusadas.
- `tese_vol` ∈ `{"cara", "barata"}`; `tese_direcao` ∈ `{"alta", "baixa", "neutra"}`.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao bloco de teste:

```python
    # Caso 9: monta as estruturas viaveis da tese e devolve perfil de risco
    cadeia_completa = []
    for strike, premio in ((28.0, 3.20), (30.0, 1.80), (32.0, 0.90), (34.0, 0.40)):
        cadeia_completa.append({"Codigo_Opcao": f"C{strike:.0f}", "Tipo": "CALL",
                                "Strike": strike, "Data_Vencimento": "2026-02-20",
                                "Preco_Mercado": premio, "Liquidez": 500})
    for strike, premio in ((28.0, 0.50), (30.0, 1.10), (32.0, 2.30), (34.0, 4.10)):
        cadeia_completa.append({"Codigo_Opcao": f"P{strike:.0f}", "Tipo": "PUT",
                                "Strike": strike, "Data_Vencimento": "2026-02-20",
                                "Preco_Mercado": premio, "Liquidez": 500})

    montadas, recusas = montar_estruturas(
        cadeia_completa, spot=30.0, vencimento="2026-02-20",
        tese_vol="barata", tese_direcao="alta")
    nomes = {m.nome for m in montadas}
    assert "compra de CALL" in nomes
    assert "trava de alta com calls" in nomes
    # tese direcional de ALTA nao pode oferecer estrutura de BAIXA
    assert "trava de baixa com puts" not in nomes
    for m in montadas:
        assert m.perfil is not None and len(m.pernas) >= 1
    print("[OK] Caso 9: monta as estruturas da tese, com perfil de risco.")

    # Caso 10: sem visao direcional, so' estruturas neutras em delta
    neutras, _ = montar_estruturas(
        cadeia_completa, spot=30.0, vencimento="2026-02-20",
        tese_vol="barata", tese_direcao="neutra")
    nomes_neutros = {m.nome for m in neutras}
    assert "compra de straddle" in nomes_neutros
    assert "compra de CALL" not in nomes_neutros   # carrega delta, exige visao
    print("[OK] Caso 10: sem visao declarada, so' estruturas neutras em delta.")

    # Caso 11: cadeia pobre recusa a estrutura E diz o motivo, sem silencio
    cadeia_pobre = [
        {"Codigo_Opcao": "C30", "Tipo": "CALL", "Strike": 30.0,
         "Data_Vencimento": "2026-02-20", "Preco_Mercado": 1.80, "Liquidez": 500},
    ]
    poucas, motivos = montar_estruturas(
        cadeia_pobre, spot=30.0, vencimento="2026-02-20",
        tese_vol="barata", tese_direcao="alta")
    assert any("trava de alta com calls" in m for m in motivos)
    assert all(isinstance(m, str) and len(m) > 0 for m in motivos)
    print("[OK] Caso 11: estrutura inviavel e' recusada com motivo explicito.")

    # Caso 12: perna sem liquidez minima barra a estrutura
    cadeia_ilquida = [dict(linha, Liquidez=1) for linha in cadeia_completa]
    nenhuma, motivos_liq = montar_estruturas(
        cadeia_ilquida, spot=30.0, vencimento="2026-02-20",
        tese_vol="barata", tese_direcao="alta", liquidez_min=100)
    assert nenhuma == []
    assert any("liquidez" in m.lower() for m in motivos_liq)
    print("[OK] Caso 12: perna abaixo da liquidez minima barra a estrutura.")

    # Caso 13: venda coberta exige ter a acao. Sem posicao na carteira, a
    # estrutura nao e' oferecida - vender call sem ter o papel e' venda
    # descoberta, perfil de risco completamente diferente do que o nome sugere.
    sem_posicao, motivos_pos = montar_estruturas(
        cadeia_completa, spot=30.0, vencimento="2026-02-20",
        tese_vol="cara", tese_direcao="baixa", tem_posicao=False)
    assert "venda coberta de CALL" not in {m.nome for m in sem_posicao}
    assert any("posicao" in m.lower() for m in motivos_pos)

    com_posicao, _ = montar_estruturas(
        cadeia_completa, spot=30.0, vencimento="2026-02-20",
        tese_vol="cara", tese_direcao="baixa", tem_posicao=True)
    assert "venda coberta de CALL" in {m.nome for m in com_posicao}
    print("[OK] Caso 13: venda coberta so' aparece com posicao na carteira.")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `.venv/Scripts/python.exe modules/opcoes/estruturas_opcoes.py`
Expected: FAIL com `NameError: name 'montar_estruturas' is not defined`

- [ ] **Step 3: Implementar o mínimo**

Acrescentar a `estruturas_opcoes.py`:

```python
@dataclass(frozen=True)
class DeclaracaoEstrutura:
    """Uma estrutura e' DECLARADA, nao codificada: acrescentar uma linha ao
    CATALOGO basta, porque a matematica de risco (perfil_risco) e' escrita e
    testada uma vez so'. Cada perna e' (lado, tipo, seletor, quantidade)."""
    nome: str
    tese_vol: str        # "cara" | "barata"
    tese_direcao: str    # "alta" | "baixa" | "neutra"
    pernas: tuple[tuple[str, str, str, int], ...]
    exige_posicao: bool = False   # True = so' viavel tendo a acao (venda coberta)


# A ferramenta NUNCA sugere direcao - o eixo direcional vem do cenario
# declarado pelo usuario (ver distribuicao_opcoes.py). Estruturas com
# tese_direcao "neutra" sao as neutras em delta, oferecidas quando nao ha
# visao direcional declarada.
CATALOGO: list[DeclaracaoEstrutura] = [
    # --- neutras em delta: expressam so' a tese de volatilidade ---
    DeclaracaoEstrutura("compra de straddle", "barata", "neutra",
                        (("comprar", "CALL", "ATM", 1), ("comprar", "PUT", "ATM", 1))),
    DeclaracaoEstrutura("compra de strangle", "barata", "neutra",
                        (("comprar", "CALL", "OTM1", 1), ("comprar", "PUT", "OTM1", 1))),
    DeclaracaoEstrutura("venda de straddle", "cara", "neutra",
                        (("vender", "CALL", "ATM", 1), ("vender", "PUT", "ATM", 1))),
    DeclaracaoEstrutura("venda de strangle", "cara", "neutra",
                        (("vender", "CALL", "OTM1", 1), ("vender", "PUT", "OTM1", 1))),
    DeclaracaoEstrutura("borboleta comprada com calls", "cara", "neutra",
                        (("comprar", "CALL", "ITM1", 1), ("vender", "CALL", "ATM", 2),
                         ("comprar", "CALL", "OTM1", 1))),
    DeclaracaoEstrutura("condor com calls", "cara", "neutra",
                        (("comprar", "CALL", "ITM2", 1), ("vender", "CALL", "ITM1", 1),
                         ("vender", "CALL", "OTM1", 1), ("comprar", "CALL", "OTM2", 1))),
    # --- direcionais: so' aparecem com visao declarada ---
    DeclaracaoEstrutura("compra de CALL", "barata", "alta",
                        (("comprar", "CALL", "ATM", 1),)),
    DeclaracaoEstrutura("trava de alta com calls", "barata", "alta",
                        (("comprar", "CALL", "ATM", 1), ("vender", "CALL", "OTM1", 1))),
    DeclaracaoEstrutura("venda de PUT", "cara", "alta",
                        (("vender", "PUT", "OTM1", 1),)),
    DeclaracaoEstrutura("trava de alta com puts", "cara", "alta",
                        (("vender", "PUT", "ATM", 1), ("comprar", "PUT", "OTM1", 1))),
    DeclaracaoEstrutura("compra de PUT", "barata", "baixa",
                        (("comprar", "PUT", "ATM", 1),)),
    DeclaracaoEstrutura("trava de baixa com puts", "barata", "baixa",
                        (("comprar", "PUT", "ATM", 1), ("vender", "PUT", "OTM1", 1))),
    DeclaracaoEstrutura("venda coberta de CALL", "cara", "baixa",
                        (("vender", "CALL", "OTM1", 1),), exige_posicao=True),
    DeclaracaoEstrutura("trava de baixa com calls", "cara", "baixa",
                        (("vender", "CALL", "ATM", 1), ("comprar", "CALL", "OTM1", 1))),
]


@dataclass(frozen=True)
class EstruturaMontada:
    nome: str
    pernas: list[Perna]
    perfil: PerfilRisco


def _indexar_cadeia(cadeia: list[dict], vencimento: str) -> dict[tuple[str, float], dict]:
    return {
        (linha["Tipo"], float(linha["Strike"])): linha
        for linha in cadeia
        if str(linha.get("Data_Vencimento", ""))[:10] == vencimento[:10]
    }


def montar_estruturas(cadeia: list[dict], spot: float, vencimento: str,
                       tese_vol: str, tese_direcao: str, liquidez_min: int = 0,
                       tem_posicao: bool = False) -> tuple[list[EstruturaMontada], list[str]]:
    """Monta toda estrutura do catalogo compativel com a tese, para o
    vencimento dado. Devolve (montadas, motivos_das_recusas).

    Uma estrutura so' e' oferecida se TODAS as pernas existem na cadeia e
    passam na liquidez minima. Quando nao e' possivel, o motivo entra na
    segunda lista - silencio inexplicado seria pior que ausencia."""
    indice = _indexar_cadeia(cadeia, vencimento)
    escadas = {tipo: escada_strikes(cadeia, tipo, vencimento) for tipo in ("CALL", "PUT")}

    # "neutra" oferece so' as neutras em delta; uma visao direcional oferece
    # as daquela direcao MAIS as neutras (que continuam validas).
    if tese_direcao == "neutra":
        direcoes_aceitas = {"neutra"}
    else:
        direcoes_aceitas = {"neutra", tese_direcao}

    montadas: list[EstruturaMontada] = []
    motivos: list[str] = []

    for decl in CATALOGO:
        if decl.tese_vol != tese_vol or decl.tese_direcao not in direcoes_aceitas:
            continue
        if decl.exige_posicao and not tem_posicao:
            # Vender call sem ter o papel nao e' venda coberta, e' venda
            # descoberta - perda ilimitada, perfil totalmente diferente do que
            # o nome da estrutura sugere. Melhor nao oferecer.
            motivos.append(f"{decl.nome}: exige posicao no ativo, que nao ha na carteira")
            continue

        pernas: list[Perna] = []
        motivo_recusa = None
        for lado, tipo, seletor, quantidade in decl.pernas:
            strike = selecionar_strike(escadas[tipo], spot, seletor, tipo)
            if strike is None:
                motivo_recusa = (f"{decl.nome}: cadeia nao tem o strike {seletor} "
                                 f"de {tipo} neste vencimento")
                break
            linha = indice.get((tipo, strike))
            if linha is None:
                motivo_recusa = f"{decl.nome}: serie {tipo} {strike:.2f} nao existe na cadeia"
                break
            if float(linha.get("Liquidez", 0) or 0) < liquidez_min:
                motivo_recusa = (f"{decl.nome}: perna {tipo} {strike:.2f} tem liquidez "
                                 f"abaixo do minimo ({liquidez_min})")
                break
            premio = float(linha.get("Preco_Mercado") or 0)
            pernas.append(Perna(lado=lado, tipo=tipo, strike=strike, premio=premio,
                                quantidade=quantidade, vencimento=vencimento[:10]))

        if motivo_recusa:
            motivos.append(motivo_recusa)
            continue
        montadas.append(EstruturaMontada(nome=decl.nome, pernas=pernas,
                                          perfil=perfil_risco(pernas)))

    return montadas, motivos
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `.venv/Scripts/python.exe modules/opcoes/estruturas_opcoes.py`
Expected: PASS — treze casos

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/estruturas_opcoes.py
git commit -m "feat: catalogo declarativo de estruturas com viabilidade explicita"
```

---

### Task 7: Distribuição implícita (Breeden-Litzenberger)

**Files:**
- Create: `modules/opcoes/distribuicao_opcoes.py`

**Interfaces:**
- Consumes: `ajustar_sorriso` e `bs_price_delta` de `analises_opcoes.py` (já existentes)
- Produces: `FaixaProbabilidade` (dataclass: `limite_inferior: float`, `limite_superior: float`, `probabilidade: float`), `distribuicao_implicita(strikes: list[float], ivs: list[float], spot: float, prazo: float, taxa: float, n_faixas: int = 20) -> list[FaixaProbabilidade] | None`. Devolve `None` quando não é possível extrair distribuição confiável (menos de 4 strikes distintos, ou densidade negativa).

- [ ] **Step 1: Escrever o teste que falha**

Criar `modules/opcoes/distribuicao_opcoes.py` com o bloco de teste:

```python
if __name__ == "__main__":
    import math
    from scipy.stats import norm

    # Caso 1: TESTE ANALITICO EXATO. Com IV constante, a distribuicao neutra ao
    # risco E' lognormal, com parametros em forma fechada. Entao da' pra afirmar
    # que a extracao numerica bate com a formula - isso trava o metodo contra a
    # matematica, nao contra um valor que a propria implementacao produziu.
    spot_teste, iv_teste, prazo_teste, taxa_teste = 30.0, 0.30, 0.25, 0.12
    strikes_teste = [float(k) for k in range(20, 43, 2)]
    ivs_teste = [iv_teste] * len(strikes_teste)

    faixas = distribuicao_implicita(strikes_teste, ivs_teste, spot_teste,
                                     prazo_teste, taxa_teste, n_faixas=12)
    assert faixas is not None

    def prob_lognormal(a, b):
        """P(a < S_T < b) sob a medida neutra ao risco."""
        def d(x):
            return ((math.log(x / spot_teste)
                     - (taxa_teste - iv_teste ** 2 / 2) * prazo_teste)
                    / (iv_teste * math.sqrt(prazo_teste)))
        return float(norm.cdf(d(b)) - norm.cdf(d(a)))

    for faixa in faixas:
        esperado = prob_lognormal(faixa.limite_inferior, faixa.limite_superior)
        assert abs(faixa.probabilidade - esperado) < 0.02, (faixa, esperado)
    print("[OK] Caso 1: distribuicao extraida bate com a lognormal analitica.")

    # Caso 2: as probabilidades somam ~1 (o intervalo coberto e' quase toda a massa)
    total = sum(f.probabilidade for f in faixas)
    assert 0.90 < total < 1.02, total
    print("[OK] Caso 2: probabilidades somam aproximadamente 1.")

    # Caso 3: poucos strikes -> recusa, nao inventa distribuicao
    assert distribuicao_implicita([30.0, 32.0], [0.3, 0.3], 30.0, 0.25, 0.12) is None
    print("[OK] Caso 3: menos de 4 strikes distintos -> recusa a distribuicao.")

    print("\nTodos os casos passaram.")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `.venv/Scripts/python.exe modules/opcoes/distribuicao_opcoes.py`
Expected: FAIL com `NameError: name 'distribuicao_implicita' is not defined`

- [ ] **Step 3: Implementar o mínimo**

Inserir no topo de `distribuicao_opcoes.py`:

```python
"""Distribuicao de probabilidade implicita nos precos das opcoes.

Funcoes puras: nao le banco, nao acessa rede (mesmo padrao de exposicao.py).

ATENCAO CONCEITUAL: a distribuicao extraida aqui e' NEUTRA AO RISCO. Ela embute
premio de risco de variancia, que para acoes infla sistematicamente a cauda de
baixa. O mercado precificar 12% de chance de queda forte NAO significa que ele
atribua 12% de crenca a esse evento - parte disso e' o custo do seguro.

Consequencia obrigatoria pra quem exibe esses numeros: rotular sempre como
"embutido no preco", NUNCA como "o mercado acha". Ver secao 6.2 de
docs/superpowers/specs/2026-09-02-recomendacao-estruturada-opcoes-design.md.
"""
from __future__ import annotations
import os, sys
from dataclasses import dataclass
import math
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from analises_opcoes import ajustar_sorriso, bs_price_delta

MINIMO_STRIKES = 4


@dataclass(frozen=True)
class FaixaProbabilidade:
    limite_inferior: float
    limite_superior: float
    probabilidade: float


def distribuicao_implicita(strikes: list[float], ivs: list[float], spot: float,
                            prazo: float, taxa: float,
                            n_faixas: int = 20) -> list[FaixaProbabilidade] | None:
    """Densidade neutra ao risco por Breeden-Litzenberger: a probabilidade de
    terminar entre dois strikes e' o preco de uma borboleta estreita ali.

    Ou seja, a probabilidade E' um preco observavel, nao uma estimativa do
    modelo - o unico modelo usado e' o sorriso ajustado, pra interpolar precos
    de call em strikes que a cadeia nao lista.

    Devolve None quando nao da' pra extrair distribuicao confiavel:
    - menos de MINIMO_STRIKES strikes distintos (sorriso nao ajustavel)
    - densidade negativa em qualquer faixa (a parabola extrapolada violou
      nao-arbitragem) - nesse caso RECUSA em vez de truncar silenciosamente
    """
    if len({float(k) for k in strikes}) < MINIMO_STRIKES:
        return None
    sorriso = ajustar_sorriso(list(zip(strikes, ivs)))
    if sorriso is None:
        return None

    inferior, superior = min(strikes), max(strikes)
    bordas = np.linspace(inferior, superior, n_faixas + 1)
    passo = float(bordas[1] - bordas[0])

    def preco_call(k: float) -> float:
        vol = max(float(sorriso(k)), 1e-4)
        preco, _delta = bs_price_delta("CALL", spot, k, prazo, taxa, vol)
        return float(preco)

    desconto = math.exp(taxa * prazo)
    faixas: list[FaixaProbabilidade] = []
    for i in range(n_faixas):
        centro = float((bordas[i] + bordas[i + 1]) / 2)
        # segunda diferenca central = preco da borboleta estreita nesse centro
        segunda = preco_call(centro - passo) - 2 * preco_call(centro) + preco_call(centro + passo)
        prob = desconto * segunda / passo
        if prob < -1e-6:
            return None   # densidade negativa: ajuste violou nao-arbitragem
        faixas.append(FaixaProbabilidade(
            limite_inferior=float(bordas[i]),
            limite_superior=float(bordas[i + 1]),
            probabilidade=max(prob, 0.0),
        ))
    return faixas
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `.venv/Scripts/python.exe modules/opcoes/distribuicao_opcoes.py`
Expected: PASS — três casos

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/distribuicao_opcoes.py
git commit -m "feat: distribuicao implicita neutra ao risco (Breeden-Litzenberger)"
```

---

### Task 8: Cenários — persistência

**Files:**
- Modify: `modules/opcoes/db_opcoes.py`

**Interfaces:**
- Consumes: `db_opcoes.DB_PATH` (já existente)
- Produces: `init_schema_cenarios(db_path=None) -> None`, `gravar_cenario(ativo: str, data_declaracao: str, vencimento: str, cenario: str, preco_alvo: float, probabilidade: float, premissa: str, db_path=None) -> None`, `ler_cenarios(ativo: str, vencimento: str, db_path=None) -> list[dict]`

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar (ou criar, se não houver) bloco `if __name__ == "__main__":` em `db_opcoes.py`:

```python
if __name__ == "__main__":
    import tempfile, os as _os

    with tempfile.TemporaryDirectory() as tmp:
        banco = _os.path.join(tmp, "teste_cenarios.db")
        init_schema_cenarios(banco)

        gravar_cenario("PETR4", "2026-09-02", "2026-10-16", "alta",
                       42.0, 0.25, "Selic cai, Brent > 80", banco)
        gravar_cenario("PETR4", "2026-09-02", "2026-10-16", "base",
                       35.0, 0.55, "cenario atual se mantem", banco)
        lidos = ler_cenarios("PETR4", "2026-10-16", banco)
        assert len(lidos) == 2
        assert {linha["Cenario"] for linha in lidos} == {"alta", "base"}
        alta = [linha for linha in lidos if linha["Cenario"] == "alta"][0]
        assert alta["Preco_Alvo"] == 42.0 and alta["Probabilidade"] == 0.25
        assert alta["Premissa"] == "Selic cai, Brent > 80"
        print("[OK] Caso 1: cenario gravado e lido com premissa preservada.")

        # regravar o mesmo (ativo, data, vencimento, cenario) atualiza, nao duplica
        gravar_cenario("PETR4", "2026-09-02", "2026-10-16", "alta",
                       44.0, 0.30, "revisado", banco)
        lidos2 = ler_cenarios("PETR4", "2026-10-16", banco)
        assert len(lidos2) == 2
        alta2 = [linha for linha in lidos2 if linha["Cenario"] == "alta"][0]
        assert alta2["Preco_Alvo"] == 44.0 and alta2["Premissa"] == "revisado"
        print("[OK] Caso 2: regravar o mesmo cenario atualiza em vez de duplicar.")

    print("\nTodos os casos passaram.")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `.venv/Scripts/python.exe modules/opcoes/db_opcoes.py`
Expected: FAIL com `NameError: name 'init_schema_cenarios' is not defined`

- [ ] **Step 3: Implementar o mínimo**

Acrescentar a `db_opcoes.py` (antes do bloco de teste):

```python
def init_schema_cenarios(db_path=None) -> None:
    """Tabela de cenarios declarados pelo usuario.

    Data_Declaracao e' o que torna a afericao posterior possivel: com o tempo,
    da' pra medir se os cenarios do usuario acertam mais que o preco implicito.
    Isso e' genuinamente calibravel, ao contrario do Score (ver secao 4.4c do
    ROADMAP_MIH_Opcoes_Handoff.md)."""
    con = sqlite3.connect(db_path or DB_PATH)
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS opcoes_cenarios (
                Ativo TEXT NOT NULL,
                Data_Declaracao TEXT NOT NULL,
                Data_Vencimento TEXT NOT NULL,
                Cenario TEXT NOT NULL CHECK(Cenario IN ('alta','base','baixa')),
                Preco_Alvo REAL NOT NULL,
                Probabilidade REAL NOT NULL,
                Premissa TEXT,
                PRIMARY KEY (Ativo, Data_Declaracao, Data_Vencimento, Cenario)
            )
        """)
        con.commit()
    finally:
        con.close()


def gravar_cenario(ativo: str, data_declaracao: str, vencimento: str,
                    cenario: str, preco_alvo: float, probabilidade: float,
                    premissa: str, db_path=None) -> None:
    """Idempotente: regravar o mesmo (ativo, data, vencimento, cenario)
    atualiza os valores em vez de duplicar a linha."""
    con = sqlite3.connect(db_path or DB_PATH)
    try:
        con.execute("""
            INSERT INTO opcoes_cenarios
                (Ativo, Data_Declaracao, Data_Vencimento, Cenario,
                 Preco_Alvo, Probabilidade, Premissa)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(Ativo, Data_Declaracao, Data_Vencimento, Cenario)
            DO UPDATE SET Preco_Alvo=excluded.Preco_Alvo,
                          Probabilidade=excluded.Probabilidade,
                          Premissa=excluded.Premissa
        """, (ativo, data_declaracao, vencimento, cenario,
              preco_alvo, probabilidade, premissa))
        con.commit()
    finally:
        con.close()


def ler_cenarios(ativo: str, vencimento: str, db_path=None) -> list[dict]:
    """Cenarios mais recentes declarados para o par (ativo, vencimento)."""
    con = sqlite3.connect(db_path or DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        linhas = con.execute("""
            SELECT * FROM opcoes_cenarios
            WHERE Ativo = ? AND Data_Vencimento = ?
              AND Data_Declaracao = (
                  SELECT MAX(Data_Declaracao) FROM opcoes_cenarios
                  WHERE Ativo = ? AND Data_Vencimento = ?)
            ORDER BY Cenario
        """, (ativo, vencimento, ativo, vencimento)).fetchall()
        return [dict(linha) for linha in linhas]
    finally:
        con.close()
```

Confirmar que `import sqlite3` já está no topo de `db_opcoes.py`; se não estiver, acrescentar.

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `.venv/Scripts/python.exe modules/opcoes/db_opcoes.py`
Expected: PASS — dois casos

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/db_opcoes.py
git commit -m "feat: tabela e acesso a cenarios declarados pelo usuario"
```

---

### Task 9: Comparação cenário × implícita e valor esperado

**Files:**
- Modify: `modules/opcoes/distribuicao_opcoes.py`

**Interfaces:**
- Consumes: `FaixaProbabilidade`, `distribuicao_implicita` (Task 7); `EstruturaMontada`, `payoff_estrutura` (Tasks 1, 6)
- Produces: `probabilidade_cenario(cenarios: list[dict], limite_inferior: float, limite_superior: float) -> float`, `comparar_distribuicoes(faixas: list[FaixaProbabilidade], cenarios: list[dict]) -> list[dict]` (cada dict com `limite_inferior`, `limite_superior`, `implicita`, `cenario`, `divergencia`), `valor_esperado(pernas, faixas_ou_cenarios) -> float`

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao bloco de teste de `distribuicao_opcoes.py`:

```python
    # Caso 4: probabilidade do cenario numa faixa - cada cenario e' um ponto
    # (preco-alvo) com massa; a faixa recebe a massa dos alvos que caem nela
    cenarios_teste = [
        {"Cenario": "alta", "Preco_Alvo": 42.0, "Probabilidade": 0.25},
        {"Cenario": "base", "Preco_Alvo": 35.0, "Probabilidade": 0.55},
        {"Cenario": "baixa", "Preco_Alvo": 28.0, "Probabilidade": 0.20},
    ]
    assert probabilidade_cenario(cenarios_teste, 40.0, 45.0) == 0.25
    assert probabilidade_cenario(cenarios_teste, 33.0, 37.0) == 0.55
    assert probabilidade_cenario(cenarios_teste, 50.0, 60.0) == 0.0
    print("[OK] Caso 4: probabilidade do cenario por faixa de preco.")

    # Caso 5: comparacao expoe a divergencia faixa a faixa
    faixas_simples = [
        FaixaProbabilidade(26.0, 32.0, 0.50),
        FaixaProbabilidade(32.0, 38.0, 0.35),
        FaixaProbabilidade(38.0, 44.0, 0.15),
    ]
    comparacao = comparar_distribuicoes(faixas_simples, cenarios_teste)
    assert len(comparacao) == 3
    faixa_alta = comparacao[2]
    assert abs(faixa_alta["implicita"] - 0.15) < 1e-9
    assert abs(faixa_alta["cenario"] - 0.25) < 1e-9
    assert abs(faixa_alta["divergencia"] - 0.10) < 1e-9
    print("[OK] Caso 5: comparacao mostra divergencia entre cenario e preco.")

    # Caso 6: valor esperado da mesma estrutura sob as duas distribuicoes
    import estruturas_opcoes as est
    trava_ve = [
        est.Perna(lado="comprar", tipo="CALL", strike=30.0, premio=2.00),
        est.Perna(lado="vender", tipo="CALL", strike=35.0, premio=0.50),
    ]
    ve_implicito = valor_esperado(trava_ve, faixas_simples)
    ve_cenario = valor_esperado(trava_ve, cenarios_teste)
    # sob o cenario, que poe 25% acima de 40, a trava vale mais que sob o preco
    assert ve_cenario > ve_implicito
    print("[OK] Caso 6: valor esperado calculado sob as duas distribuicoes.")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `.venv/Scripts/python.exe modules/opcoes/distribuicao_opcoes.py`
Expected: FAIL com `NameError: name 'probabilidade_cenario' is not defined`

- [ ] **Step 3: Implementar o mínimo**

Acrescentar a `distribuicao_opcoes.py`:

```python
def probabilidade_cenario(cenarios: list[dict], limite_inferior: float,
                           limite_superior: float) -> float:
    """Massa de probabilidade que os cenarios declarados poem nessa faixa.

    Cada cenario e' um ponto (preco-alvo) com massa concentrada - o usuario
    declara tres pontos, nao uma curva. Faixa fechada embaixo, aberta em cima,
    pra nao contar o mesmo alvo duas vezes em faixas adjacentes."""
    total = 0.0
    for cenario in cenarios:
        alvo = float(cenario["Preco_Alvo"])
        if limite_inferior <= alvo < limite_superior:
            total += float(cenario["Probabilidade"])
    return total


def comparar_distribuicoes(faixas: list[FaixaProbabilidade],
                            cenarios: list[dict]) -> list[dict]:
    """Divergencia faixa a faixa entre o que esta' embutido no preco e o que o
    usuario declarou.

    LEMBRETE OBRIGATORIO pra quem exibe: parte da diferenca e' premio de risco
    de variancia, nao discordancia de opiniao - a distribuicao implicita e'
    neutra ao risco (ver docstring do modulo)."""
    saida = []
    for faixa in faixas:
        prob_cenario = probabilidade_cenario(
            cenarios, faixa.limite_inferior, faixa.limite_superior)
        saida.append({
            "limite_inferior": faixa.limite_inferior,
            "limite_superior": faixa.limite_superior,
            "implicita": faixa.probabilidade,
            "cenario": prob_cenario,
            "divergencia": prob_cenario - faixa.probabilidade,
        })
    return saida


def valor_esperado(pernas, distribuicao) -> float:
    """Valor esperado do payoff no vencimento sob a distribuicao dada.

    `distribuicao` aceita as duas formas: lista de FaixaProbabilidade (a
    implicita, avaliada no centro de cada faixa) ou lista de cenarios
    declarados (avaliada no preco-alvo de cada um).

    Exibir os DOIS lado a lado e' o desenho: a ferramenta nao elege estrutura
    vencedora - ela mostra a consequencia de cada uma sob as duas visoes e
    deixa a comparacao com o usuario."""
    import estruturas_opcoes as est
    total = 0.0
    for item in distribuicao:
        if isinstance(item, FaixaProbabilidade):
            preco = (item.limite_inferior + item.limite_superior) / 2
            peso = item.probabilidade
        else:
            preco = float(item["Preco_Alvo"])
            peso = float(item["Probabilidade"])
        total += peso * est.payoff_estrutura(pernas, preco)
    return total
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `.venv/Scripts/python.exe modules/opcoes/distribuicao_opcoes.py`
Expected: PASS — seis casos

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/distribuicao_opcoes.py
git commit -m "feat: comparacao cenario x implicita e valor esperado das estruturas"
```

---

### Task 10: UI — declarar cenário e ver operações

**Files:**
- Modify: `modules/opcoes/view_opcoes.py` (final da função `render_aba_opcoes`)

**Interfaces:**
- Consumes: `montar_estruturas`, `EstruturaMontada.perfil` (Task 6); `distribuicao_implicita`, `comparar_distribuicoes`, `valor_esperado` (Tasks 7, 9); `init_schema_cenarios`, `gravar_cenario`, `ler_cenarios` (Task 8)
- Produces: seção nova na aba de Opções. Nada consumido por outros módulos.

**Contexto do arquivo** (confirmado por leitura, não suposto):
- A UI de Opções é `modules/opcoes/view_opcoes.py`; `paginas/opcoes.py` é só um wrapper de 12 linhas que chama `render_aba_opcoes`.
- O módulo faz `sys.path.insert(0, os.path.dirname(__file__))` no topo, então módulos irmãos são importados por nome puro (`import db_opcoes`), **não** por `from modules.opcoes import ...`.
- Todos os imports ficam **dentro** de `render_aba_opcoes`, não no topo do arquivo. Seguir esse padrão.
- Variáveis já disponíveis no escopo ao final da função: `ativo` (str), `und` (dict com `Spot`, `HV_60d`, `Data_Referencia`), `series`, `rank` (saída de `ao.analisar`), `liq_min` (int), `selic` (float), `db_path`, `carteira_df`, e a constante de módulo `DISCLAIMER`.

- [ ] **Step 1: Acrescentar os imports novos**

Dentro de `render_aba_opcoes`, junto dos imports existentes (`import db_opcoes`, `import analises_opcoes as ao`, ...), acrescentar:

```python
    import estruturas_opcoes as eo
    import distribuicao_opcoes as dop
    from datetime import date as _date
```

- [ ] **Step 2: Acrescentar o formulário de cenário ao final da função**

```python
    st.divider()
    st.subheader("Montar operação a partir de um cenário")
    st.caption(
        "O desvio de preço observado (IV vs. HV e vs. o sorriso) **não prevê "
        "retorno**: o backtest sobre 3,87 milhões de linhas do COTAHIST não "
        "encontrou vantagem estatística nos ativos líquidos. A direção vem do "
        "seu cenário, não da ferramenta. " + DISCLAIMER
    )

    vencimentos = sorted({linha["Data_Vencimento"] for linha in rank})
    if not vencimentos:
        st.info("Sem vencimentos na cadeia atual.")
        return

    vencimento_escolhido = st.selectbox("Vencimento", vencimentos, key="venc_cenario")
    spot = float(und["Spot"])

    st.markdown("**Seu cenário** — preço-alvo e probabilidade que você atribui")
    colunas = st.columns(3)
    entradas = []
    padroes = (("alta", spot * 1.15, 0.25),
               ("base", spot, 0.50),
               ("baixa", spot * 0.85, 0.25))
    for coluna, (nome, alvo_padrao, prob_padrao) in zip(colunas, padroes):
        with coluna:
            st.markdown(f"*{nome.capitalize()}*")
            entradas.append({
                "Cenario": nome,
                "Preco_Alvo": st.number_input(
                    f"Alvo ({nome})", value=float(round(alvo_padrao, 2)),
                    key=f"alvo_{nome}"),
                "Probabilidade": st.number_input(
                    f"Probabilidade ({nome})", 0.0, 1.0, float(prob_padrao), 0.05,
                    key=f"prob_{nome}"),
                "Premissa": st.text_input(f"Premissa ({nome})", key=f"premissa_{nome}"),
            })

    soma = sum(e["Probabilidade"] for e in entradas)
    if abs(soma - 1.0) > 0.01:
        st.warning(f"As probabilidades somam {soma:.0%} — ajuste para 100%.")
    elif st.button("Salvar cenário"):
        db_opcoes.init_schema_cenarios(db_path)
        for cenario in entradas:
            db_opcoes.gravar_cenario(
                ativo, str(_date.today()), vencimento_escolhido, cenario["Cenario"],
                cenario["Preco_Alvo"], cenario["Probabilidade"],
                cenario["Premissa"], db_path)
        st.success("Cenário salvo. A data de declaração fica registrada para aferição futura.")
```

- [ ] **Step 3: Acrescentar a comparação de distribuições**

```python
    db_opcoes.init_schema_cenarios(db_path)
    cenarios_salvos = db_opcoes.ler_cenarios(ativo, vencimento_escolhido, db_path)
    if not cenarios_salvos:
        st.info("Declare e salve um cenário acima para ver as operações.")
        return

    do_vencimento = [linha for linha in rank
                     if linha["Data_Vencimento"] == vencimento_escolhido]
    strikes = [linha["Strike"] for linha in do_vencimento]
    ivs = [linha["IV"] for linha in do_vencimento]
    dias = do_vencimento[0]["Dias"] if do_vencimento else 30

    faixas = dop.distribuicao_implicita(strikes, ivs, spot, dias / 365, selic)

    if faixas is None:
        st.info(
            "Não foi possível extrair a distribuição implícita deste vencimento "
            "(menos de 4 strikes distintos, ou o ajuste do sorriso ficou "
            "inconsistente com não-arbitragem). As estruturas abaixo continuam "
            "válidas — só a comparação de probabilidades fica indisponível."
        )
    else:
        st.markdown("**Embutido no preço vs. seu cenário**")
        st.caption(
            "A distribuição implícita é **neutra ao risco**: ela embute prêmio de "
            "risco de variância, que para ações infla a cauda de baixa. Ela mostra "
            "o que está *embutido no preço*, não o que o mercado *acredita* — "
            "parte da divergência é remuneração de risco, não discordância de opinião."
        )
        comparacao = dop.comparar_distribuicoes(faixas, cenarios_salvos)
        st.dataframe(pd.DataFrame([{
            "Faixa": f"R$ {linha['limite_inferior']:.2f} – {linha['limite_superior']:.2f}",
            "Embutido no preço": f"{linha['implicita']:.1%}",
            "Seu cenário": f"{linha['cenario']:.1%}",
            "Divergência (p.p.)": f"{linha['divergencia'] * 100:+.1f}",
        } for linha in comparacao]), use_container_width=True, hide_index=True)
```

- [ ] **Step 4: Acrescentar a tabela de estruturas**

```python
    # A direcao vem do CENARIO declarado, nunca da ferramenta.
    alvo_base = next((float(c["Preco_Alvo"]) for c in cenarios_salvos
                      if c["Cenario"] == "base"), spot)
    if alvo_base > spot * 1.02:
        tese_direcao = "alta"
    elif alvo_base < spot * 0.98:
        tese_direcao = "baixa"
    else:
        tese_direcao = "neutra"

    iv_media = sum(ivs) / len(ivs) if ivs else 0.0
    tese_vol = "cara" if iv_media > float(und["HV_60d"]) else "barata"

    # Posicao na carteira entra como VIABILIDADE (habilita venda coberta),
    # nunca como visao direcional inferida.
    tem_posicao = False
    if carteira_df is not None and not carteira_df.empty and "ativo" in carteira_df:
        tickers = {str(t).strip().upper() for t in carteira_df["ativo"]}
        tem_posicao = any(t.startswith(ativo[:4].upper()) for t in tickers)

    montadas, recusas = eo.montar_estruturas(
        do_vencimento, spot, vencimento_escolhido, tese_vol, tese_direcao,
        liquidez_min=int(liq_min), tem_posicao=tem_posicao)

    st.markdown(
        f"**Operações viáveis** — vol {tese_vol}, direção *{tese_direcao}* "
        f"(do seu cenário)"
    )

    linhas_tabela = []
    for estrutura in montadas:
        perfil = estrutura.perfil
        linhas_tabela.append({
            "Estrutura": estrutura.nome,
            "Pernas": " / ".join(f"{p.lado} {p.tipo} {p.strike:.2f}"
                                 for p in estrutura.pernas),
            "Prêmio líquido": f"R$ {perfil.premio_liquido:,.2f}",
            "Perda máxima": ("ILIMITADA" if perfil.perda_maxima is None
                             else f"R$ {perfil.perda_maxima:,.2f}"),
            "Ganho máximo": ("ILIMITADO" if perfil.ganho_maximo is None
                             else f"R$ {perfil.ganho_maximo:,.2f}"),
            "Breakevens": ", ".join(f"{b:.2f}" for b in perfil.breakevens),
            "VE sob seu cenário": f"R$ {dop.valor_esperado(estrutura.pernas, cenarios_salvos):,.2f}",
            "VE embutido no preço": ("—" if faixas is None
                                     else f"R$ {dop.valor_esperado(estrutura.pernas, faixas):,.2f}"),
        })

    if linhas_tabela:
        st.dataframe(pd.DataFrame(linhas_tabela), use_container_width=True, hide_index=True)
        st.caption(
            "As duas últimas colunas mostram o mesmo payoff sob as duas visões — "
            "a diferença é o ganho que existe **se a sua premissa estiver certa**. "
            "A ferramenta não elege uma estrutura vencedora. "
            "**Perda máxima é no vencimento**: não protege de marcação a mercado "
            "adversa nem de chamada de margem antes disso. Margem exigida não é "
            "calculada aqui — consulte sua corretora."
        )
    else:
        st.info("Nenhuma estrutura do catálogo é viável nesta cadeia.")

    if recusas:
        with st.expander(f"{len(recusas)} estruturas não puderam ser montadas"):
            for motivo in recusas:
                st.write(f"- {motivo}")
```

- [ ] **Step 5: Verificar na aplicação**

Run: `.venv/Scripts/python.exe -m streamlit run app.py`

Na aba de Opções, conferir:
1. Declarar um cenário com probabilidades somando 100% e salvar.
2. A tabela de comparação aparece (ou a mensagem explicando por que não).
3. A tabela de estruturas traz perda máxima, breakevens e as duas colunas de valor esperado.
4. O expander lista as estruturas recusadas com motivo.
5. Os três avisos estão visíveis: desvio não prevê retorno; implícita é neutra ao risco; perda máxima é no vencimento.
6. Probabilidades que não somam 100% bloqueiam o salvamento com aviso.

- [ ] **Step 6: Commit**

```bash
git add modules/opcoes/view_opcoes.py
git commit -m "feat: montar operacoes a partir de cenario declarado na aba de Opcoes"
```

---

## Notas de execução

**Ordem e independência.** Tasks 1-2 (motor) e Task 7 (distribuição) são independentes entre si. Tasks 3-4 (correções) são independentes de tudo. Task 5 depende de 1; Task 6 depende de 1, 2 e 5; Task 9 depende de 6 e 7; Task 10 depende de todas.

**Se algum teste de valores de livro-texto falhar por centavos**, não relaxar a tolerância: a matemática de payoff no vencimento é exata, e discrepância indica erro de sinal ou de lote, não imprecisão numérica.

**Sobre a UI:** a aba de Opcoes vive em `modules/opcoes/view_opcoes.py`; `paginas/opcoes.py` e' so' um wrapper de 12 linhas. Os imports ficam DENTRO de `render_aba_opcoes`, e modulos irmaos sao importados por nome puro (`import db_opcoes`) por causa do `sys.path.insert` no topo do arquivo.

**Sobre a Task 4:** ela reduz o número de sorrisos ajustáveis, porque agora cada vencimento precisa dos seus próprios 4 strikes distintos. Séries que antes herdavam um sorriso de outro prazo passarão a ter `Skew_pp = 0`. Isso é o comportamento correto — não é regressão.
