# Cenários Automáticos por FHS — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir a declaração manual de cenários por um modelo que gera a distribuição real-world do ativo no vencimento, e provar por avaliação estatística que ele é bem calibrado antes de colocá-lo em produção.

**Architecture:** Dois módulos novos de funções puras. `modelo_cenarios.py` faz EWMA + Filtered Historical Simulation, com retornos de-mediados e distribuição recentrada no preço a termo (o modelo prevê largura e forma, nunca o centro). `avaliacao_previsoes.py` mede calibração por PIT e CRPS em walk-forward sobre os 501 pregões já disponíveis, contra um benchmark incondicional — se o modelo não vencer, ele não entra em produção.

**Tech Stack:** Python 3, numpy, scipy.stats, sqlite3, Streamlit. Sem dependências novas.

**Spec:** `docs/superpowers/specs/2026-09-02-cenarios-automaticos-fhs-design.md`

## Global Constraints

- **Convenção de testes:** este repositório **não usa pytest** (não há `tests/`, nem config, nem pytest instalado). Testes são blocos `if __name__ == "__main__":` no próprio módulo, com `assert` e `print("[OK] Caso N: descrição.")`, terminando em `print("\nTodos os casos passaram.")`. **Não** introduzir pytest.
- **Rodar teste de um módulo:** `.venv/Scripts/python.exe modules/opcoes/<modulo>.py`
- **Módulos novos são funções puras:** sem banco, sem rede, sem efeito colateral. Quem chama monta os dados. Mesmo padrão de `exposicao.py`, `estruturas_opcoes.py` e `distribuicao_opcoes.py`.
- **Isolamento do banco:** `modules/opcoes/` usa SQLite local via `db_opcoes.DB_PATH`, ignorando `DATABASE_URL`. Nunca usar `db.engine` neste módulo.
- **Acentuação:** código e comentários em português sem acento; textos de UI com acento normal.
- **`LAMBDA_EWMA = 0.94`** (RiskMetrics para dados diários), **`DIAS_UTEIS_ANO = 252`**, **`MINIMO_PREGOES = 250`**, **`SALTO_MAXIMO = 0.35`**.
- **Aleatoriedade sempre com semente explícita** nos testes (`np.random.default_rng(semente)`), para que os casos sejam reproduzíveis.
- **A distribuição implícita continua rotulada como "embutido no preço"**, e a divergência contra o modelo é **prêmio de risco**, nunca oportunidade.

---

### Task 1: Volatilidade EWMA

**Files:**
- Create: `modules/opcoes/modelo_cenarios.py`

**Interfaces:**
- Consumes: nada
- Produces: `LAMBDA_EWMA: float`, `DIAS_UTEIS_ANO: int`, `volatilidade_ewma(retornos, lam: float = LAMBDA_EWMA) -> np.ndarray` — devolve array do mesmo tamanho de `retornos`, onde a posição `i` é a volatilidade prevista **para** o período `i`, usando apenas informação até `i-1`.

- [ ] **Step 1: Escrever o teste que falha**

Criar `modules/opcoes/modelo_cenarios.py` só com o bloco de teste:

```python
if __name__ == "__main__":
    import numpy as np

    # Caso 1: com volatilidade constante, o EWMA converge para ela
    rng = np.random.default_rng(42)
    vol_verdadeira = 0.02
    retornos_const = rng.normal(0.0, vol_verdadeira, 2000)
    vol = volatilidade_ewma(retornos_const)
    assert len(vol) == len(retornos_const)
    # EWMA e' ruidoso (janela efetiva ~1/(1-0.94) ~ 17 dias), entao a media da
    # serie e' o que converge, nao cada ponto
    assert abs(vol[100:].mean() - vol_verdadeira) < 0.15 * vol_verdadeira
    print("[OK] Caso 1: EWMA converge para a volatilidade verdadeira.")

    # Caso 2: NAO olha o futuro. vol[i] e' calculada com retornos ate' i-1,
    # entao mexer no ULTIMO retorno nao pode alterar nenhum valor da serie.
    # Sem essa propriedade, o walk-forward da Task 6 estaria contaminado.
    retornos_alterado = retornos_const.copy()
    retornos_alterado[-1] = 99.0
    vol_alterado = volatilidade_ewma(retornos_alterado)
    assert np.allclose(vol, vol_alterado)
    print("[OK] Caso 2: EWMA nao olha o futuro (ultimo retorno nao afeta a serie).")

    print("\nTodos os casos passaram.")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `.venv/Scripts/python.exe modules/opcoes/modelo_cenarios.py`
Expected: FAIL com `NameError: name 'volatilidade_ewma' is not defined`

- [ ] **Step 3: Implementar o mínimo**

Inserir no topo do arquivo, antes do bloco de teste:

```python
"""Modelo de cenarios automaticos por Filtered Historical Simulation (FHS).

Funcoes puras: nao le banco, nao acessa rede (mesmo padrao de exposicao.py).

O QUE ESTE MODELO FAZ E O QUE NAO FAZ: ele preve a LARGURA e a FORMA da
distribuicao do ativo no horizonte, nunca o CENTRO. Volatilidade e' previsivel
(clustering e' um dos fatos empiricos mais robustos em financas); direcao nao
e'. Por isso os retornos sao de-mediados antes de virar residuos, e a
distribuicao simulada e' recentrada no preco a termo - que e' nao-arbitragem,
nao opiniao. Ver secao 3.3 de
docs/superpowers/specs/2026-09-02-cenarios-automaticos-fhs-design.md.

A distribuicao produzida aqui e' a medida REAL-WORLD (P). A extraida das opcoes
(distribuicao_opcoes.py) e' a NEUTRA AO RISCO (Q). A diferenca entre as duas e'
PREMIO DE RISCO - documentado e ja precificado - nao oportunidade.
"""
from __future__ import annotations
import math
import numpy as np

LAMBDA_EWMA = 0.94      # RiskMetrics, para dados diarios
DIAS_UTEIS_ANO = 252


def volatilidade_ewma(retornos, lam: float = LAMBDA_EWMA) -> np.ndarray:
    """Serie de volatilidade condicional (desvio-padrao) por EWMA:

        var_t = lam * var_{t-1} + (1 - lam) * r_{t-1}^2

    A posicao i do resultado e' a volatilidade prevista PARA o periodo i,
    usando somente retornos ate' i-1. Essa construcao sem olhar o futuro e' o
    que torna o walk-forward da avaliacao honesto.

    EWMA e nao GARCH por escopo: com ~500 observacoes, GARCH(1,1) da parametros
    instaveis; EWMA tem parametro fixo e conhecido, nao precisa de otimizacao, e
    captura o efeito que importa (clustering)."""
    r = np.asarray(retornos, dtype=float)
    if len(r) == 0:
        return np.array([])
    var = np.empty(len(r))
    var[0] = float(np.var(r)) if len(r) > 1 else float(r[0] ** 2)
    for i in range(1, len(r)):
        var[i] = lam * var[i - 1] + (1 - lam) * r[i - 1] ** 2
    return np.sqrt(var)
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `.venv/Scripts/python.exe modules/opcoes/modelo_cenarios.py`
Expected: PASS — dois casos

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/modelo_cenarios.py
git commit -m "feat: volatilidade condicional por EWMA, sem olhar o futuro"
```

---

### Task 2: Filtered Historical Simulation

**Files:**
- Modify: `modules/opcoes/modelo_cenarios.py`

**Interfaces:**
- Consumes: `LAMBDA_EWMA`, `DIAS_UTEIS_ANO`, `volatilidade_ewma` (Task 1)
- Produces: `residuos_padronizados(retornos, lam=LAMBDA_EWMA) -> tuple[np.ndarray, np.ndarray]` (resíduos, série de vol), `simular_fhs(retornos, spot: float, horizonte: int, taxa: float, n_simulacoes: int = 10000, lam: float = LAMBDA_EWMA, semente: int | None = None) -> np.ndarray` (preços terminais simulados, recentrados no termo)

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao bloco de teste, antes do print final:

```python
    # Caso 3: ESTE E' O TESTE MAIS IMPORTANTE DO MODULO.
    # Com retornos de drift forte, a distribuicao simulada tem que ficar
    # centrada no PRECO A TERMO, nao no preco extrapolado pelo drift. Sem
    # de-mediar os retornos, a simulacao herdaria o drift amostral e estaria
    # prevendo DIRECAO a partir de retorno passado - exatamente a armadilha
    # que este design existe para evitar (secao 3.3 da spec).
    drift_diario = 0.005
    retornos_drift = drift_diario + rng.normal(0.0, 0.01, 500)
    spot_teste, horizonte_teste, taxa_teste = 100.0, 45, 0.0
    precos = simular_fhs(retornos_drift, spot_teste, horizonte_teste,
                          taxa_teste, n_simulacoes=5000, semente=7)
    termo = spot_teste * math.exp(taxa_teste * horizonte_teste / DIAS_UTEIS_ANO)
    assert abs(precos.mean() - termo) < 0.01 * termo
    # extrapolar o drift daria ~100*exp(0.005*45) = 125; tem que estar longe disso
    preco_se_extrapolasse_drift = spot_teste * math.exp(drift_diario * horizonte_teste)
    assert precos.mean() < 0.9 * preco_se_extrapolasse_drift
    print("[OK] Caso 3: distribuicao recentrada no termo - drift historico nao vaza.")

    # Caso 4: a taxa entra pelo termo (juro maior desloca o centro pra cima)
    precos_juro = simular_fhs(retornos_drift, spot_teste, horizonte_teste,
                               taxa=0.12, n_simulacoes=5000, semente=7)
    termo_juro = spot_teste * math.exp(0.12 * horizonte_teste / DIAS_UTEIS_ANO)
    assert abs(precos_juro.mean() - termo_juro) < 0.01 * termo_juro
    assert precos_juro.mean() > precos.mean()
    print("[OK] Caso 4: o centro da distribuicao e' o preco a termo, com juro.")

    # Caso 5: FHS preserva a assimetria dos residuos (nao assume normal).
    # Horizonte 1 preserva mais - agregar horizonte encolhe assimetria (TCL).
    from scipy.stats import skew
    choques_assimetricos = np.concatenate([
        rng.normal(0.005, 0.005, 900),      # muitos ganhos pequenos
        rng.normal(-0.06, 0.02, 100),       # poucas quedas grandes
    ])
    precos_assim = simular_fhs(choques_assimetricos, 100.0, 1, 0.0,
                                n_simulacoes=20000, semente=11)
    assert skew(np.log(precos_assim / 100.0)) < -0.3
    print("[OK] Caso 5: FHS preserva a assimetria real, nao assume normal.")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `.venv/Scripts/python.exe modules/opcoes/modelo_cenarios.py`
Expected: FAIL com `NameError: name 'simular_fhs' is not defined`

- [ ] **Step 3: Implementar o mínimo**

Acrescentar após `volatilidade_ewma`:

```python
def residuos_padronizados(retornos, lam: float = LAMBDA_EWMA):
    """Retornos DE-MEDIADOS divididos pela volatilidade condicional.

    De-mediar e' critico e nao e' detalhe: sem isso, os residuos carregam o
    drift do periodo amostral, a simulacao o herda, e o modelo passa a prever
    direcao a partir de retorno passado. Retorno esperado e' notoriamente
    dificil de estimar - drift de 2 anos e' ruido.

    Devolve (residuos, serie_de_vol)."""
    r = np.asarray(retornos, dtype=float)
    r = r - r.mean()
    vol = volatilidade_ewma(r, lam)
    return r / np.maximum(vol, 1e-12), vol


def simular_fhs(retornos, spot: float, horizonte: int, taxa: float,
                 n_simulacoes: int = 10000, lam: float = LAMBDA_EWMA,
                 semente: int | None = None) -> np.ndarray:
    """Filtered Historical Simulation: devolve os precos terminais simulados.

    Procedimento: filtra os retornos pelo EWMA, extrai os residuos
    padronizados (que carregam cauda gorda e assimetria REAIS do ativo, sem
    assumir distribuicao), sorteia esses residuos com reposicao ao longo do
    horizonte reescalando pela volatilidade prevista, e recentra o resultado
    no preco a termo.

    A recentragem no termo (spot * exp(taxa * horizonte/252)) e' o que impede
    o drift historico de virar previsao de direcao - ver residuos_padronizados
    e a secao 3.3 da spec."""
    rng = np.random.default_rng(semente)
    z, vol = residuos_padronizados(retornos, lam)
    var_inicial = float(vol[-1] ** 2)

    # Vetorizado ao longo das simulacoes: o laco corre o horizonte (dezenas de
    # passos), nao as simulacoes (milhares). A recursao de vol e' dependente do
    # caminho, entao precisa ser iterada - mas todas as trajetorias avancam
    # juntas.
    var = np.full(n_simulacoes, var_inicial, dtype=float)
    soma_retornos = np.zeros(n_simulacoes, dtype=float)
    for _ in range(horizonte):
        choques = z[rng.integers(0, len(z), n_simulacoes)]
        retorno_passo = np.sqrt(var) * choques
        soma_retornos += retorno_passo
        var = lam * var + (1 - lam) * retorno_passo ** 2

    precos = spot * np.exp(soma_retornos)

    # Recentra a MEDIA no preco a termo (condicao de martingale sob a medida a
    # termo). O modelo entrega largura e forma; o centro vem de nao-arbitragem.
    termo = spot * math.exp(taxa * horizonte / DIAS_UTEIS_ANO)
    return precos * (termo / precos.mean())
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `.venv/Scripts/python.exe modules/opcoes/modelo_cenarios.py`
Expected: PASS — cinco casos

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/modelo_cenarios.py
git commit -m "feat: FHS com residuos de-mediados e recentragem no preco a termo"
```

---

### Task 3: Resumo em três cenários

**Files:**
- Modify: `modules/opcoes/modelo_cenarios.py`

**Interfaces:**
- Consumes: nada das tarefas anteriores (opera sobre o array de preços)
- Produces: `resumir_em_cenarios(precos_simulados) -> list[dict]` — três dicts com as chaves `Cenario` (`"baixa"`/`"base"`/`"alta"`), `Preco_Alvo` (float) e `Probabilidade` (float), no mesmo formato que `distribuicao_opcoes.probabilidade_cenario` e `valor_esperado` já consomem

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao bloco de teste:

```python
    # Caso 6: o resumo em tres cenarios e' COERENTE com a distribuicao.
    # O preco de cada cenario e' a MEDIA CONDICIONAL da sua regiao, nao o
    # quantil de corte - por isso a media ponderada dos tres recupera a media
    # da distribuicao completa. Usar o quantil como preco quebraria isso: o
    # ponto exibido nao representaria a regiao que ele resume.
    amostra = simular_fhs(retornos_drift, 100.0, 45, 0.0,
                           n_simulacoes=20000, semente=3)
    cenarios = resumir_em_cenarios(amostra)
    assert [c["Cenario"] for c in cenarios] == ["baixa", "base", "alta"]
    assert abs(sum(c["Probabilidade"] for c in cenarios) - 1.0) < 1e-9
    media_ponderada = sum(c["Preco_Alvo"] * c["Probabilidade"] for c in cenarios)
    assert abs(media_ponderada - amostra.mean()) < 1e-6 * amostra.mean()
    print("[OK] Caso 6: resumo por media condicional recupera a media da distribuicao.")

    # Caso 7: ordenacao e proporcoes por construcao (cortes em 25% e 75%)
    assert cenarios[0]["Preco_Alvo"] < cenarios[1]["Preco_Alvo"] < cenarios[2]["Preco_Alvo"]
    assert abs(cenarios[0]["Probabilidade"] - 0.25) < 0.01
    assert abs(cenarios[1]["Probabilidade"] - 0.50) < 0.01
    assert abs(cenarios[2]["Probabilidade"] - 0.25) < 0.01
    print("[OK] Caso 7: cortes em 25%/75% dao 25/50/25, com precos ordenados.")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `.venv/Scripts/python.exe modules/opcoes/modelo_cenarios.py`
Expected: FAIL com `NameError: name 'resumir_em_cenarios' is not defined`

- [ ] **Step 3: Implementar o mínimo**

Acrescentar após `simular_fhs`:

```python
def resumir_em_cenarios(precos_simulados) -> list[dict]:
    """Resume a distribuicao simulada em tres cenarios, no mesmo formato que a
    UI e distribuicao_opcoes.py ja consomem.

    O preco de cada cenario e' a MEDIA CONDICIONAL da sua regiao, nao o quantil
    de corte. Isso torna o resumo coerente: a media ponderada dos tres pontos
    recupera a media da distribuicao completa. Exibir o quantil 10% como "preco
    do cenario de baixa" e ao mesmo tempo atribuir a ele a massa abaixo do
    quantil 25% seria incoerente - o ponto nao representaria a regiao.

    O resumo e' para EXIBICAO. O valor esperado das estruturas continua sendo
    calculado sobre a distribuicao completa (ver secao 3.4 da spec)."""
    p = np.asarray(precos_simulados, dtype=float)
    q25, q75 = np.quantile(p, [0.25, 0.75])
    regioes = (
        ("baixa", p[p <= q25]),
        ("base", p[(p > q25) & (p <= q75)]),
        ("alta", p[p > q75]),
    )
    return [
        {"Cenario": nome,
         "Preco_Alvo": float(valores.mean()),
         "Probabilidade": float(len(valores) / len(p))}
        for nome, valores in regioes
    ]
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `.venv/Scripts/python.exe modules/opcoes/modelo_cenarios.py`
Expected: PASS — sete casos

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/modelo_cenarios.py
git commit -m "feat: resumo da distribuicao em tres cenarios por media condicional"
```

---

### Task 4: Carga da série e guardas de qualidade

**Files:**
- Modify: `modules/opcoes/modelo_cenarios.py`

**Interfaces:**
- Consumes: nada
- Produces: `MINIMO_PREGOES: int`, `SALTO_MAXIMO: float`, `validar_serie(precos) -> str | None` (motivo da recusa, ou `None` se a série serve), `retornos_log(precos) -> np.ndarray`
- Nota: a leitura do banco **não** fica aqui (módulo é de funções puras). Quem chama monta a lista de preços — a UI usa `db_opcoes`, e a avaliação recebe a série pronta.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao bloco de teste:

```python
    # Caso 8: serie curta demais e' recusada com motivo, nao produz modelo ruim
    curta = list(np.linspace(30.0, 32.0, 100))
    motivo = validar_serie(curta)
    assert motivo is not None and "pregoes" in motivo.lower()
    print("[OK] Caso 8: serie com menos de 250 pregoes e' recusada com motivo.")

    # Caso 9: salto de evento societario e' detectado. O COTAHIST traz preco
    # BRUTO, sem ajuste - o grupamento do MGLU foi de R$1,32 para R$13,15 num
    # pregao (+896%). Sem esta guarda, o modelo leria isso como volatilidade.
    com_grupamento = [10.0] * 300
    com_grupamento[150] = 100.0   # salto de +900%
    motivo_salto = validar_serie(com_grupamento)
    assert motivo_salto is not None and "salto" in motivo_salto.lower()
    print("[OK] Caso 9: salto de evento societario e' detectado e recusado.")

    # Caso 10: serie boa passa, e os retornos log saem com o tamanho certo
    boa = list(100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.015, 400))))
    assert validar_serie(boa) is None
    assert len(retornos_log(boa)) == len(boa) - 1
    print("[OK] Caso 10: serie valida passa e produz retornos log.")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `.venv/Scripts/python.exe modules/opcoes/modelo_cenarios.py`
Expected: FAIL com `NameError: name 'validar_serie' is not defined`

- [ ] **Step 3: Implementar o mínimo**

Acrescentar ao módulo (junto das outras constantes no topo, e as funções após `resumir_em_cenarios`):

```python
MINIMO_PREGOES = 250
SALTO_MAXIMO = 0.35     # variacao em um pregao acima disso = provavel evento societario
```

```python
def retornos_log(precos) -> np.ndarray:
    """Retornos logaritmicos diarios a partir da serie de precos."""
    p = np.asarray(precos, dtype=float)
    return np.diff(np.log(p))


def validar_serie(precos) -> str | None:
    """Devolve o motivo da recusa, ou None se a serie serve para o modelo.

    Recusa em vez de produzir estimativa ruim silenciosamente - mesmo principio
    das recusas de distribuicao_opcoes.py."""
    p = np.asarray(precos, dtype=float)
    if len(p) < MINIMO_PREGOES:
        return (f"serie curta demais: {len(p)} pregoes, minimo {MINIMO_PREGOES} "
                f"para estimar volatilidade e extrair residuos")
    if np.any(p <= 0):
        return "serie contem preco zero ou negativo"

    variacoes = np.abs(np.diff(p) / p[:-1])
    if np.any(variacoes > SALTO_MAXIMO):
        indice = int(np.argmax(variacoes))
        return (f"salto de {variacoes[indice]:.0%} em um pregao (de {p[indice]:.2f} "
                f"para {p[indice + 1]:.2f}) - provavel evento societario nao "
                f"ajustado; o COTAHIST traz preco bruto")
    return None
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `.venv/Scripts/python.exe modules/opcoes/modelo_cenarios.py`
Expected: PASS — dez casos

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/modelo_cenarios.py
git commit -m "feat: guardas de qualidade da serie (minimo de pregoes, salto societario)"
```

---

### Task 5: Métricas de calibração (PIT e CRPS)

**Files:**
- Create: `modules/opcoes/avaliacao_previsoes.py`

**Interfaces:**
- Consumes: nada
- Produces: `pit(previsao_simulada, realizado: float) -> float` (posição do realizado na distribuição prevista, em [0,1]), `crps(previsao_simulada, realizado: float) -> float` (menor é melhor)

- [ ] **Step 1: Escrever o teste que falha**

Criar `modules/opcoes/avaliacao_previsoes.py` só com o bloco de teste:

```python
if __name__ == "__main__":
    import numpy as np
    from scipy.stats import kstest

    rng = np.random.default_rng(123)

    # Caso 1: o PIT de um modelo PERFEITO e' uniforme. Gerando dados de uma
    # distribuicao e prevendo com essa MESMA distribuicao, os valores de PIT
    # tem que passar num teste de uniformidade. Isso trava a metrica contra a
    # matematica, nao contra a propria implementacao.
    valores_pit = []
    for _ in range(500):
        previsao = rng.normal(0.0, 1.0, 4000)
        realizado = float(rng.normal(0.0, 1.0))
        valores_pit.append(pit(previsao, realizado))
    estatistica, valor_p = kstest(valores_pit, "uniform")
    assert valor_p > 0.05, (estatistica, valor_p)
    print("[OK] Caso 1: PIT de um modelo perfeito passa no teste de uniformidade.")

    # Caso 2: modelo com cauda ESTREITA demais acumula PIT nas pontas.
    # E' o diagnostico que a metrica precisa dar - nao basta detectar erro,
    # tem que apontar o tipo do erro.
    valores_estreito = []
    for _ in range(500):
        previsao = rng.normal(0.0, 0.3, 4000)     # subestima a vol
        realizado = float(rng.normal(0.0, 1.0))   # realidade e' mais larga
        valores_estreito.append(pit(previsao, realizado))
    nas_pontas = np.mean([(v < 0.05) or (v > 0.95) for v in valores_estreito])
    assert nas_pontas > 0.30   # bem acima dos 10% esperados se calibrado
    print("[OK] Caso 2: PIT acusa cauda estreita demais (acumulo nas pontas).")

    # Caso 3: CRPS de previsao DETERMINISTICA reduz ao erro absoluto.
    # Verificavel na mao: sem dispersao, o segundo termo da formula zera.
    deterministica = np.full(1000, 10.0)
    assert abs(crps(deterministica, 12.0) - 2.0) < 1e-9
    assert abs(crps(deterministica, 10.0) - 0.0) < 1e-9
    print("[OK] Caso 3: CRPS de previsao deterministica == erro absoluto.")

    # Caso 4: CRPS premia a previsao mais bem centrada
    certeira = rng.normal(10.0, 1.0, 5000)
    torta = rng.normal(15.0, 1.0, 5000)
    assert crps(certeira, 10.0) < crps(torta, 10.0)
    print("[OK] Caso 4: CRPS premia a previsao mais proxima do realizado.")

    print("\nTodos os casos passaram.")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `.venv/Scripts/python.exe modules/opcoes/avaliacao_previsoes.py`
Expected: FAIL com `NameError: name 'pit' is not defined`

- [ ] **Step 3: Implementar o mínimo**

Inserir no topo do arquivo:

```python
"""Avaliacao de previsao de densidade: o modelo e' bem calibrado?

Funcoes puras: nao le banco, nao acessa rede.

Por que este modulo existe ANTES da integracao com a UI: calibracao de
densidade e' uma pergunta BEM-POSTA - "quando o modelo diz 10% de chance,
acontece 10% das vezes?" tem resposta objetiva. Isso e' diferente do Score,
que so' conseguimos invalidar depois de muito trabalho (secao 4.4c do
ROADMAP_MIH_Opcoes_Handoff.md).

Se a calibracao nao passar, o modelo NAO entra em producao. Ver secao 5 de
docs/superpowers/specs/2026-09-02-cenarios-automaticos-fhs-design.md.

AVISO: calibracao nao implica lucro. Um modelo perfeitamente calibrado
descreve bem a distribuicao e ainda assim nao gera vantagem - a distribuicao
real-world estar correta nao diz que a neutra ao risco esta' errada.
"""
from __future__ import annotations
import numpy as np


def pit(previsao_simulada, realizado: float) -> float:
    """Probability Integral Transform: a posicao percentual do valor realizado
    dentro da distribuicao prevista.

    Se o modelo for bem calibrado, esses valores sao uniformes em [0,1] ao
    longo de muitas previsoes. O desvio da uniformidade diagnostica o defeito:
    acumulo nas PONTAS significa cauda estreita demais (o modelo se surpreende
    com frequencia); acumulo no MEIO, cauda larga demais."""
    p = np.asarray(previsao_simulada, dtype=float)
    return float((p <= realizado).mean())


def crps(previsao_simulada, realizado: float) -> float:
    """Continuous Ranked Probability Score para previsao por conjunto.

        CRPS = E|X - y| - 0.5 * E|X - X'|

    O primeiro termo premia acerto; o segundo penaliza dispersao - por isso e'
    uma regra de pontuacao PROPRIA: nao da' para melhorar a nota mentindo sobre
    a incerteza. Menor e' melhor.

    O segundo termo usa a identidade da diferenca media de Gini sobre a amostra
    ordenada, que sai em O(n log n) em vez do O(n^2) da dupla somatoria."""
    p = np.asarray(previsao_simulada, dtype=float)
    termo_acerto = float(np.abs(p - realizado).mean())

    ordenada = np.sort(p)
    n = len(ordenada)
    indices = np.arange(1, n + 1)
    dispersao = float(2.0 * np.sum((2 * indices - n - 1) * ordenada) / (n * n))

    return termo_acerto - 0.5 * dispersao
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `.venv/Scripts/python.exe modules/opcoes/avaliacao_previsoes.py`
Expected: PASS — quatro casos

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/avaliacao_previsoes.py
git commit -m "feat: metricas de calibracao de densidade (PIT e CRPS)"
```

---

### Task 6: Walk-forward contra benchmark incondicional

**Files:**
- Modify: `modules/opcoes/avaliacao_previsoes.py`

**Interfaces:**
- Consumes: `pit`, `crps` (Task 5); `simular_fhs`, `retornos_log`, `MINIMO_PREGOES` de `modelo_cenarios` (Tasks 1-4)
- Produces: `simular_incondicional(retornos, spot, horizonte, taxa, n_simulacoes=10000, semente=None) -> np.ndarray` (benchmark: bootstrap dos retornos de-mediados, sem modelo de vol), `walk_forward(precos, horizonte, taxa, janela_minima=MINIMO_PREGOES, n_simulacoes=4000, semente=None) -> list[dict]` (cada dict com `indice`, `realizado`, `pit_modelo`, `crps_modelo`, `pit_benchmark`, `crps_benchmark`), `resumir_avaliacao(resultados) -> dict` (com `n_janelas`, `crps_modelo`, `crps_benchmark`, `ganho_percentual`, `pit_ks_valor_p`, `veredito`)

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao bloco de teste de `avaliacao_previsoes.py`:

```python
    # Caso 5: as janelas do walk-forward NAO se sobrepoem. Previsoes em datas
    # consecutivas com horizonte h compartilham periodo e nao sao
    # independentes - usa-las infla a confianca nas metricas.
    precos_teste = list(100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.015, 500))))
    resultados = walk_forward(precos_teste, horizonte=45, taxa=0.10,
                               n_simulacoes=800, semente=5)
    indices = [r["indice"] for r in resultados]
    assert all(indices[i + 1] - indices[i] >= 45 for i in range(len(indices) - 1))
    # 500 pregoes, janela minima 250, horizonte 45 -> poucas janelas mesmo
    assert 3 <= len(resultados) <= 8, len(resultados)
    print(f"[OK] Caso 5: walk-forward usa {len(resultados)} janelas nao sobrepostas.")

    # Caso 6: NAO OLHA O FUTURO. Alterar os precos DEPOIS da ultima janela
    # avaliada nao pode mudar nenhuma previsao ja feita. Sem isso, toda a
    # avaliacao seria contaminada e diria que o modelo e' melhor do que e'.
    precos_alterados = list(precos_teste)
    ultimo_indice = max(indices)
    for i in range(ultimo_indice + 46, len(precos_alterados)):
        precos_alterados[i] = precos_alterados[i] * 3.0
    resultados_alterados = walk_forward(precos_alterados, horizonte=45, taxa=0.10,
                                         n_simulacoes=800, semente=5)
    for antes, depois in zip(resultados, resultados_alterados):
        assert abs(antes["crps_modelo"] - depois["crps_modelo"]) < 1e-9
    print("[OK] Caso 6: walk-forward nao olha o futuro (dados posteriores nao afetam).")

    # Caso 7: o benchmark incondicional tambem e' recentrado no termo - a
    # comparacao tem que isolar o MODELO DE VOL, nao premiar o FHS por um
    # detalhe de centragem que o benchmark nao teria.
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import modelo_cenarios as mc
    retornos_bench = mc.retornos_log(precos_teste)
    amostra_bench = simular_incondicional(retornos_bench, 100.0, 45, 0.0,
                                           n_simulacoes=5000, semente=9)
    assert abs(amostra_bench.mean() - 100.0) < 1.0
    print("[OK] Caso 7: benchmark incondicional tambem recentrado no termo.")

    # Caso 8: o resumo reporta o numero de janelas e avisa quando sao poucas
    resumo = resumir_avaliacao(resultados)
    assert resumo["n_janelas"] == len(resultados)
    assert "crps_modelo" in resumo and "crps_benchmark" in resumo
    assert isinstance(resumo["veredito"], str) and len(resumo["veredito"]) > 0
    if resumo["n_janelas"] < 8:
        assert "amostra" in resumo["veredito"].lower()
    print("[OK] Caso 8: resumo reporta n de janelas e avisa amostra insuficiente.")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `.venv/Scripts/python.exe modules/opcoes/avaliacao_previsoes.py`
Expected: FAIL com `NameError: name 'walk_forward' is not defined`

- [ ] **Step 3: Implementar o mínimo**

Acrescentar os imports no topo de `avaliacao_previsoes.py`, logo após `import numpy as np`:

```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import math
from scipy.stats import kstest
import modelo_cenarios as mc
```

E as funções, após `crps`:

```python
def simular_incondicional(retornos, spot: float, horizonte: int, taxa: float,
                           n_simulacoes: int = 10000,
                           semente: int | None = None) -> np.ndarray:
    """Benchmark: distribuicao empirica INCONDICIONAL.

    Mesmo horizonte e mesma recentragem no termo que o FHS, mas SEM modelo de
    volatilidade - apenas bootstrap dos retornos de-mediados. Isola exatamente
    a contribuicao do EWMA: se o FHS nao vencer isso, o modelo de vol nao esta'
    agregando e a complexidade nao se justifica."""
    rng = np.random.default_rng(semente)
    r = np.asarray(retornos, dtype=float)
    r = r - r.mean()
    sorteados = r[rng.integers(0, len(r), (n_simulacoes, horizonte))]
    precos = spot * np.exp(sorteados.sum(axis=1))
    termo = spot * math.exp(taxa * horizonte / mc.DIAS_UTEIS_ANO)
    return precos * (termo / precos.mean())


def walk_forward(precos, horizonte: int, taxa: float,
                  janela_minima: int = mc.MINIMO_PREGOES,
                  n_simulacoes: int = 4000,
                  semente: int | None = None) -> list[dict]:
    """Avalia o modelo em janelas NAO SOBREPOSTAS, usando em cada data apenas
    informacao disponivel ate' ali.

    Janelas nao sobrepostas porque previsoes em datas consecutivas com
    horizonte h compartilham periodo e nao sao independentes - trata-las como
    independentes inflaria a confianca nas metricas. O custo e' ter poucas
    janelas (com h=45 e 501 pregoes, ~5 por ativo), e por isso resumir_avaliacao
    sempre reporta quantas foram."""
    p = np.asarray(precos, dtype=float)
    resultados: list[dict] = []
    indice = janela_minima
    while indice + horizonte < len(p):
        historico = p[:indice + 1]                 # so' ate' a data da previsao
        retornos = mc.retornos_log(historico)
        spot = float(historico[-1])
        realizado = float(p[indice + horizonte])

        previsao_modelo = mc.simular_fhs(retornos, spot, horizonte, taxa,
                                          n_simulacoes=n_simulacoes, semente=semente)
        previsao_bench = simular_incondicional(retornos, spot, horizonte, taxa,
                                                n_simulacoes=n_simulacoes, semente=semente)
        resultados.append({
            "indice": indice,
            "realizado": realizado,
            "pit_modelo": pit(previsao_modelo, realizado),
            "crps_modelo": crps(previsao_modelo, realizado),
            "pit_benchmark": pit(previsao_bench, realizado),
            "crps_benchmark": crps(previsao_bench, realizado),
        })
        indice += horizonte                        # sem sobreposicao
    return resultados


def resumir_avaliacao(resultados: list[dict]) -> dict:
    """Consolida o walk-forward num veredito legivel.

    CRPS sozinho nao diz se o modelo e' bom - so' compara. Por isso o veredito
    e' sempre relativo ao benchmark incondicional, e sempre acompanhado do
    numero de janelas em que se baseia."""
    if not resultados:
        return {"n_janelas": 0, "crps_modelo": None, "crps_benchmark": None,
                "ganho_percentual": None, "pit_ks_valor_p": None,
                "veredito": "sem janelas suficientes para avaliar"}

    crps_modelo = float(np.mean([r["crps_modelo"] for r in resultados]))
    crps_bench = float(np.mean([r["crps_benchmark"] for r in resultados]))
    ganho = (crps_bench - crps_modelo) / crps_bench * 100 if crps_bench else 0.0

    valores_pit = [r["pit_modelo"] for r in resultados]
    valor_p = float(kstest(valores_pit, "uniform").pvalue) if len(valores_pit) >= 3 else None

    partes = []
    partes.append(f"CRPS do modelo {crps_modelo:.4f} vs. benchmark {crps_bench:.4f} "
                  f"({ganho:+.1f}%)")
    if ganho <= 0:
        partes.append("o modelo de volatilidade NAO venceu o benchmark incondicional")
    if valor_p is not None:
        partes.append(f"uniformidade do PIT: p={valor_p:.3f}"
                      + (" (calibracao rejeitada)" if valor_p < 0.05 else ""))
    if len(resultados) < 8:
        partes.append(f"ATENCAO: apenas {len(resultados)} janelas independentes - "
                      "amostra insuficiente para conclusao firme")

    return {"n_janelas": len(resultados), "crps_modelo": crps_modelo,
            "crps_benchmark": crps_bench, "ganho_percentual": ganho,
            "pit_ks_valor_p": valor_p, "veredito": "; ".join(partes)}
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `.venv/Scripts/python.exe modules/opcoes/avaliacao_previsoes.py`
Expected: PASS — oito casos

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/avaliacao_previsoes.py
git commit -m "feat: walk-forward sem olhar o futuro, contra benchmark incondicional"
```

---

### Task 7: Rodar a avaliação nos dados reais — o gate

**Files:**
- Create: `modules/opcoes/rodar_avaliacao.py`

**Interfaces:**
- Consumes: `walk_forward`, `resumir_avaliacao` (Task 6); `validar_serie` (Task 4); `db_opcoes.DB_PATH`
- Produces: script de linha de comando. Não exporta interface para outras tarefas.

**Este é o gate da seção 5.5 da spec: se a calibração não passar, as Tasks 8 e 9 não são implementadas e o cenário manual permanece.**

- [ ] **Step 1: Escrever o script**

Criar `modules/opcoes/rodar_avaliacao.py`:

```python
"""Roda a avaliacao de calibracao do modelo FHS sobre os dados reais.

Este script E' o gate: se o modelo nao vencer o benchmark incondicional e nao
passar na uniformidade do PIT, ele NAO entra em producao e a declaracao manual
de cenarios permanece (secao 5.5 da spec).

Uso:
    python modules/opcoes/rodar_avaliacao.py --horizonte 45
    python modules/opcoes/rodar_avaliacao.py --horizonte 45 --ativos PETR VALE ITUB
"""
from __future__ import annotations
import os, sys, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import db_opcoes
import modelo_cenarios as mc
import avaliacao_previsoes as av

TAXA_PADRAO = 0.1415


def carregar_precos(ativo: str, db_path=None) -> list[float]:
    """Serie de preco diario do ativo-objeto, a partir do historico COTAHIST."""
    con = sqlite3.connect(db_path or db_opcoes.DB_PATH, timeout=120)
    try:
        linhas = con.execute("""
            SELECT Data, MAX(Preco_Ativo) FROM opcoes_historico
            WHERE Ativo_Objeto = ? AND Preco_Ativo > 0
            GROUP BY Data ORDER BY Data
        """, (ativo,)).fetchall()
    finally:
        con.close()
    return [float(v) for _data, v in linhas]


def avaliar(ativos: list[str], horizonte: int, taxa: float, db_path=None) -> None:
    todos: list[dict] = []
    for ativo in ativos:
        precos = carregar_precos(ativo, db_path)
        motivo = mc.validar_serie(precos) if precos else "sem serie no banco"
        if motivo:
            print(f"{ativo}: RECUSADO - {motivo}", flush=True)
            continue
        resultados = av.walk_forward(precos, horizonte, taxa, semente=42)
        resumo = av.resumir_avaliacao(resultados)
        print(f"{ativo}: {resumo['n_janelas']} janelas | "
              f"CRPS {resumo['crps_modelo']:.4f} vs {resumo['crps_benchmark']:.4f} "
              f"({resumo['ganho_percentual']:+.1f}%)", flush=True)
        todos.extend(resultados)

    print("\n" + "=" * 70)
    print("VEREDITO AGREGADO (todos os ativos)")
    print("=" * 70)
    resumo_geral = av.resumir_avaliacao(todos)
    print(resumo_geral["veredito"])
    print(f"\njanelas independentes no total: {resumo_geral['n_janelas']}")

    aprovado = (resumo_geral["ganho_percentual"] or 0) > 0 and (
        resumo_geral["pit_ks_valor_p"] is None or resumo_geral["pit_ks_valor_p"] >= 0.05)
    print("\nGATE:", "APROVADO - modelo pode ir para producao" if aprovado
          else "REPROVADO - manter cenario manual, nao integrar o modelo")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizonte", type=int, default=45,
                    help="dias uteis ate' o vencimento (default 45)")
    ap.add_argument("--taxa", type=float, default=TAXA_PADRAO)
    ap.add_argument("--ativos", nargs="*", default=["PETR", "VALE", "ITUB", "BBAS", "BBDC"])
    args = ap.parse_args()
    avaliar(args.ativos, args.horizonte, args.taxa)
```

- [ ] **Step 2: Rodar contra os dados reais**

Run: `.venv/Scripts/python.exe modules/opcoes/rodar_avaliacao.py --horizonte 45`

Este comando lê os 501 pregões de cada ativo e faz walk-forward. Esperado: uma
linha por ativo e o veredito agregado ao final, terminando em `GATE: APROVADO`
ou `GATE: REPROVADO`.

- [ ] **Step 3: Registrar o resultado e decidir**

Anotar o veredito na seção 4.4d nova do
`modules/opcoes/ROADMAP_MIH_Opcoes_Handoff.md`, com os números reais (CRPS do
modelo, do benchmark, ganho percentual, p-valor do PIT, número de janelas).

**Se REPROVADO:** parar aqui. Não implementar as Tasks 8 e 9. Relatar ao
usuário que o modelo não passou, com os números, e que o cenário manual
permanece. Um modelo mal calibrado em produção é pior que a entrada manual,
porque tem aparência de rigor.

**Se APROVADO:** seguir para a Task 8.

- [ ] **Step 4: Commit**

```bash
git add modules/opcoes/rodar_avaliacao.py modules/opcoes/ROADMAP_MIH_Opcoes_Handoff.md
git commit -m "feat: avaliacao de calibracao do FHS nos dados reais (gate de producao)"
```

---

### Task 8: Persistência das previsões

**Files:**
- Modify: `modules/opcoes/db_opcoes.py`

**Interfaces:**
- Consumes: `_conn`, `DB_PATH` (já existentes)
- Produces: `init_schema_previsoes(db_path=None) -> None`, `gravar_previsao(ativo, data_previsao, horizonte, origem, q10, q25, q50, q75, q90, db_path=None) -> None`, `ler_previsoes_pendentes(db_path=None) -> list[dict]` (previsões sem realizado preenchido), `registrar_realizado(ativo, data_previsao, horizonte, preco_realizado, db_path=None) -> None`

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao bloco de teste de `db_opcoes.py`, antes do print final:

```python
    with tempfile.TemporaryDirectory() as tmp2:
        banco2 = _os.path.join(tmp2, "teste_previsoes.db")
        init_schema_previsoes(banco2)

        gravar_previsao("PETR", "2026-09-02", 45, "modelo",
                        28.0, 30.0, 32.0, 34.0, 36.0, banco2)
        pendentes = ler_previsoes_pendentes(banco2)
        assert len(pendentes) == 1
        assert pendentes[0]["Origem"] == "modelo"
        assert pendentes[0]["Q50"] == 32.0
        assert pendentes[0]["Preco_Realizado"] is None
        print("[OK] Caso 3: previsao gravada fica pendente ate' ter o realizado.")

        registrar_realizado("PETR", "2026-09-02", 45, 33.5, banco2)
        assert ler_previsoes_pendentes(banco2) == []
        print("[OK] Caso 4: registrar o realizado tira a previsao da fila de pendentes.")

        # modelo e override manual convivem: mesma data, origens diferentes
        gravar_previsao("PETR", "2026-09-02", 45, "manual",
                        29.0, 31.0, 33.0, 35.0, 37.0, banco2)
        con_teste = sqlite3.connect(banco2)
        total = con_teste.execute("SELECT COUNT(*) FROM opcoes_previsoes").fetchone()[0]
        con_teste.close()
        assert total == 2
        print("[OK] Caso 5: modelo e override manual coexistem para comparacao futura.")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `.venv/Scripts/python.exe modules/opcoes/db_opcoes.py`
Expected: FAIL com `NameError: name 'init_schema_previsoes' is not defined`

- [ ] **Step 3: Implementar o mínimo**

Acrescentar a `db_opcoes.py`, antes de `list_existing_tables`:

```python
def init_schema_previsoes(db_path: str | Path | None = None) -> None:
    """Tabela de previsoes de distribuicao, para afericao continua.

    Guarda os quantis (nao a simulacao inteira) porque e' o que basta para
    calcular PIT depois, e cabe numa linha. Origem distingue "modelo" de
    "manual", para responder com o tempo se a visao do usuario acerta mais que
    o modelo - comparacao que tambem e' bem-posta."""
    con = _conn(db_path)
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS opcoes_previsoes (
                Ativo TEXT NOT NULL,
                Data_Previsao TEXT NOT NULL,
                Horizonte INTEGER NOT NULL,
                Origem TEXT NOT NULL CHECK(Origem IN ('modelo','manual')),
                Q10 REAL NOT NULL, Q25 REAL NOT NULL, Q50 REAL NOT NULL,
                Q75 REAL NOT NULL, Q90 REAL NOT NULL,
                Preco_Realizado REAL,
                PRIMARY KEY (Ativo, Data_Previsao, Horizonte, Origem)
            )
        """)
        con.commit()
    finally:
        con.close()


def gravar_previsao(ativo: str, data_previsao: str, horizonte: int, origem: str,
                     q10: float, q25: float, q50: float, q75: float, q90: float,
                     db_path: str | Path | None = None) -> None:
    """Idempotente: regravar a mesma chave atualiza os quantis."""
    con = _conn(db_path)
    try:
        con.execute("""
            INSERT INTO opcoes_previsoes
                (Ativo, Data_Previsao, Horizonte, Origem, Q10, Q25, Q50, Q75, Q90)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(Ativo, Data_Previsao, Horizonte, Origem) DO UPDATE SET
                Q10=excluded.Q10, Q25=excluded.Q25, Q50=excluded.Q50,
                Q75=excluded.Q75, Q90=excluded.Q90
        """, (ativo, data_previsao, horizonte, origem, q10, q25, q50, q75, q90))
        con.commit()
    finally:
        con.close()


def ler_previsoes_pendentes(db_path: str | Path | None = None) -> list[dict]:
    """Previsoes que ainda nao tem o preco realizado preenchido."""
    con = _conn(db_path)
    con.row_factory = sqlite3.Row
    try:
        linhas = con.execute(
            "SELECT * FROM opcoes_previsoes WHERE Preco_Realizado IS NULL "
            "ORDER BY Data_Previsao").fetchall()
        return [dict(linha) for linha in linhas]
    finally:
        con.close()


def registrar_realizado(ativo: str, data_previsao: str, horizonte: int,
                         preco_realizado: float,
                         db_path: str | Path | None = None) -> None:
    """Fecha o ciclo: preenche o que de fato aconteceu, habilitando o calculo
    de PIT/CRPS sobre previsoes feitas de verdade, no passado."""
    con = _conn(db_path)
    try:
        con.execute("""
            UPDATE opcoes_previsoes SET Preco_Realizado = ?
            WHERE Ativo = ? AND Data_Previsao = ? AND Horizonte = ?
        """, (preco_realizado, ativo, data_previsao, horizonte))
        con.commit()
    finally:
        con.close()
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `.venv/Scripts/python.exe modules/opcoes/db_opcoes.py`
Expected: PASS — cinco casos

- [ ] **Step 5: Commit**

```bash
git add modules/opcoes/db_opcoes.py
git commit -m "feat: persistencia de previsoes de distribuicao para afericao continua"
```

---

### Task 9: Integração na UI — modelo como padrão, manual como override

**Files:**
- Modify: `modules/opcoes/view_opcoes.py` (a seção "Montar operação a partir de um cenário")

**Interfaces:**
- Consumes: `simular_fhs`, `resumir_em_cenarios`, `validar_serie`, `retornos_log` (Tasks 1-4); `gravar_previsao`, `init_schema_previsoes` (Task 8); `carregar_precos` de `rodar_avaliacao` (Task 7)
- Produces: nada consumido por outros módulos.

**Contexto do arquivo** (confirmado por leitura): a UI de Opções é `modules/opcoes/view_opcoes.py`; `paginas/opcoes.py` é um wrapper de 12 linhas. Os imports ficam **dentro** de `render_aba_opcoes`, e módulos irmãos são importados por nome puro (`import db_opcoes`) por causa do `sys.path.insert` no topo. Variáveis disponíveis: `ativo`, `und` (com `Spot`, `HV_60d`), `rank`, `liq_min`, `selic`, `db_path`, `carteira_df`, e a constante `DISCLAIMER`.

- [ ] **Step 1: Acrescentar os imports**

Junto dos imports existentes dentro de `render_aba_opcoes`:

```python
    import modelo_cenarios as mc
    import rodar_avaliacao as ra
```

- [ ] **Step 2: Substituir o formulário manual pelo seletor de origem**

Localizar o bloco que começa em `st.markdown("**Seu cenário** — preço-alvo e probabilidade que você atribui")` e vai até o `st.success("Cenário salvo. ...")`. Substituir inteiro por:

```python
    origem = st.radio(
        "Origem do cenário",
        ["Modelo (FHS)", "Declarar manualmente"],
        horizontal=True, key="origem_cenario",
        help="O modelo estima a distribuição a partir do histórico do ativo. "
             "A declaração manual existe para quando você sabe algo sobre a "
             "empresa que não está no preço — a única entrada que um modelo "
             "estatístico não replica.",
    )

    dias_ate_venc = next((l["Dias"] for l in rank
                          if l["Data_Vencimento"] == vencimento_escolhido), 45)
    horizonte_uteis = max(1, int(dias_ate_venc * 252 / 365))

    if origem == "Modelo (FHS)":
        precos_hist = ra.carregar_precos(ativo, db_path)
        motivo = mc.validar_serie(precos_hist) if precos_hist else "sem série no banco"
        if motivo:
            st.warning(
                f"O modelo não pôde ser usado para {ativo}: {motivo}. "
                "Use a declaração manual."
            )
            cenarios_salvos = []
        else:
            simulados = mc.simular_fhs(
                mc.retornos_log(precos_hist), spot, horizonte_uteis, selic,
                n_simulacoes=10000, semente=42)
            cenarios_salvos = mc.resumir_em_cenarios(simulados)
            st.caption(
                f"Distribuição estimada por Filtered Historical Simulation sobre "
                f"{len(precos_hist)} pregões, horizonte de {horizonte_uteis} dias úteis. "
                "O modelo estima a **largura e a forma** da distribuição; o centro é o "
                "preço a termo (não-arbitragem), nunca uma previsão de direção."
            )
            db_opcoes.init_schema_previsoes(db_path)
            q10, q25, q50, q75, q90 = [float(q) for q in
                                        np.quantile(simulados, [0.1, 0.25, 0.5, 0.75, 0.9])]
            db_opcoes.gravar_previsao(ativo, str(_date.today()), horizonte_uteis,
                                       "modelo", q10, q25, q50, q75, q90, db_path)
    else:
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
            cenarios_salvos = []
        else:
            db_opcoes.init_schema_cenarios(db_path)
            for cenario in entradas:
                db_opcoes.gravar_cenario(
                    ativo, str(_date.today()), vencimento_escolhido, cenario["Cenario"],
                    cenario["Preco_Alvo"], cenario["Probabilidade"],
                    cenario["Premissa"], db_path)
            cenarios_salvos = entradas
```

Acrescentar `import numpy as np` aos imports da função, se ainda não estiver lá.

- [ ] **Step 3: Ajustar o bloco seguinte, que lia os cenários do banco**

O trecho abaixo do formulário lia `cenarios_salvos` de `db_opcoes.ler_cenarios`.
Agora `cenarios_salvos` já vem definido pelo Step 2 nos dois caminhos. Localizar
e **remover** estas duas linhas:

```python
    db_opcoes.init_schema_cenarios(db_path)
    cenarios_salvos = db_opcoes.ler_cenarios(ativo, vencimento_escolhido, db_path)
```

Manter a guarda que vem logo depois, ajustando a mensagem:

```python
    if not cenarios_salvos:
        st.info("Ajuste as entradas acima para ver as operações.")
        return
```

- [ ] **Step 4: Rotular a origem na comparação de distribuições**

Localizar `st.markdown("**Embutido no preço vs. seu cenário**")` e trocar por:

```python
        rotulo_origem = "modelo (FHS)" if origem == "Modelo (FHS)" else "seu cenário"
        st.markdown(f"**Embutido no preço vs. {rotulo_origem}**")
```

E na tabela de comparação, trocar a chave `"Seu cenário"` por
`rotulo_origem.capitalize()`, para que a coluna diga de onde a distribuição veio.

- [ ] **Step 5: Verificar na aplicação**

Run: `.venv/Scripts/python.exe -m streamlit run app.py`

Na aba de Opções, conferir:
1. Com "Modelo (FHS)" selecionado, as operações aparecem **sem** exigir nenhuma entrada sua.
2. A legenda do modelo cita o número de pregões e diz que o centro é o preço a termo.
3. Trocando para "Declarar manualmente", o formulário volta e funciona como antes.
4. A coluna da comparação muda de nome conforme a origem.
5. Para um ativo sem série suficiente, aparece o aviso com o motivo em vez de erro.

- [ ] **Step 6: Commit**

```bash
git add modules/opcoes/view_opcoes.py
git commit -m "feat: modelo FHS como origem padrao do cenario, manual como override"
```

---

## Notas de execução

**A Task 7 é um gate, não uma formalidade.** Se o veredito for REPROVADO, as Tasks 8 e 9 não devem ser implementadas. Um modelo mal calibrado em produção é pior que a entrada manual, porque carrega aparência de rigor sem o conteúdo.

**Independência.** Tasks 1-4 (`modelo_cenarios.py`) e Task 5 (métricas) são independentes entre si. Task 6 depende de 1-5; Task 7 de 6; Tasks 8-9 do resultado de 7.

**Sobre a aleatoriedade.** Toda função que simula recebe `semente`. Nos testes ela é sempre explícita — sem isso os casos falhariam de forma intermitente, que é o pior tipo de teste.

**Sobre o Caso 3 da Task 2.** É o teste mais importante do conjunto: trava a decisão de de-mediar os retornos e recentrar no termo. Se ele falhar, o modelo voltou a prever direção a partir de retorno passado, que é exatamente o que este design existe para evitar. Não relaxar a tolerância desse caso.

**Evento de resultado (seção 4 da spec)** fica fora deste plano de propósito: é segunda fase, condicionada ao núcleo passar no gate, e depende de entrada manual de datas que ainda não existe na UI.
