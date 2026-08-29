"""
exposicao.py - Gera sinais cruzando a exposicao da carteira do usuario com os
indicadores macro que o MIH ja coleta (Selic, IPCA, USD/BRL).

Funcoes puras, sem efeito colateral (mesmo padrao de analises.py): apenas leem
os DataFrames recebidos e devolvem estruturas de dados. Nenhuma leitura de
banco ou escrita acontece aqui - quem chama e' responsavel por montar os
DataFrames (app.py e briefing.py ja tem esses dados carregados).
"""
import pandas as pd


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
            serie = (df_indicadores[df_indicadores["indicador"] == nome]
                     .sort_values("data")
                     .drop_duplicates(subset="data", keep="last"))
            if len(serie) >= 2:
                valores = serie["valor"].tolist()
                deltas[nome] = valores[-1] - valores[-2]

    if df_dolar is not None and len(df_dolar) >= 2:
        serie = (df_dolar.sort_values("date")
                 .drop_duplicates(subset="date", keep="last"))
        if len(serie) >= 2:
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
    assert por_indexador["CDI"]["texto"] == "Selic variou +0.25 p.p. -> favorece R$ 10.000,00 em CDI (long)"
    assert por_indexador["Prefixado"]["texto"] == "Selic variou +0.25 p.p. -> pressiona R$ 5.000,00 em Prefixado (long)"
    print("[OK] Caso 3: CDI e Prefixado reagem em sentidos opostos ao mesmo delta de Selic.")

    # Caso 4: posicao short inverte o sentido do impacto
    carteira_short = pd.DataFrame([
        {"id": 1, "ativo": "Hedge dolar", "descricao": "", "direcao": "short", "indexador": "Dólar", "tamanho": 20000.0},
    ])
    sinal_dolar = gerar_sinais_exposicao(carteira_short, indicadores_ok, dolar_ok)[0]
    assert sinal_dolar["sentido_impacto"] == "desfavoravel"  # dolar subiu, posicao short perde
    assert sinal_dolar["texto"] == "Dólar variou +R$ 0,03 -> pressiona R$ 20.000,00 em Dólar (short)"
    print("[OK] Caso 4: posicao short inverte o sentido do impacto.")

    # Caso 5: resumo_exposicao_por_indexador agrega por indexador
    resumo = resumo_exposicao_por_indexador(carteira_mista)
    assert resumo["CDI"] == 10000.0
    assert resumo["Prefixado"] == 5000.0
    assert resumo_exposicao_por_indexador(carteira_vazia).empty
    print("[OK] Caso 5: resumo_exposicao_por_indexador agrega corretamente.")

    # Caso 6: linhas duplicadas na ultima data nao podem fazer o delta colapsar para zero
    # (regressao: banco real tem leituras duplicadas por data em indicadores_bcb/usd_brl)
    dolar_com_duplicata = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-26", "2026-08-27", "2026-08-27"]),
        "close": [5.35, 5.40, 5.40],
    })
    deltas_dup = _calcular_deltas(indicadores_ok, dolar_com_duplicata)
    assert round(deltas_dup["Dólar"], 4) == 0.05  # 5.40 (27/08) - 5.35 (26/08), nao 5.40 - 5.40
    assert deltas_dup["Dólar"] != 0.0  # sem o dedup, valores[-1]-valores[-2] colapsaria pra 0.0
    print("[OK] Caso 6: linha duplicada na ultima data nao zera o delta (dedup por data aplicado).")

    print("\nTodos os casos passaram.")
