# enriquecer_debentures.py
import re
import requests
import pandas as pd
from sqlalchemy import create_engine


def classificar_indexador(texto):
    if not isinstance(texto, str) or not texto.strip():
        return "Nao informado"
    t = texto.upper()
    if "IPCA" in t:
        return "IPCA"
    if "IGP-M" in t or "IGPM" in t:
        return "IGP-M"
    if "CDI" in t or re.search(r"\bDI\b", t):
        return "CDI"
    if "PREFIXAD" in t or re.match(r"\s*\d+[.,]\d+\s*%", t):
        return "Prefixado"
    return "Outro"


def buscar_detalhe_serie(numero):
    url = f"https://web.cvm.gov.br/sre-publico-cvm/rest/sitePublico/pesquisar/requerimento/{numero}"
    try:
        dados = requests.get(url, headers={"Accept": "application/json"}, timeout=30).json()
    except Exception:
        return []
    if not isinstance(dados, dict):
        return []

    def campo(campos, pedaco):
        for c in campos:
            if pedaco in c.get("campoNome", "").lower():
                return c.get("campoValor", "")
        return ""

    resultado = []
    for grupo in dados.get("grupos", []):
        for serie in grupo.get("series", []):
            lote = serie.get("loteInicial") or {}
            campos = lote.get("camposCadastrados", []) or []
            remus = [c.get("campoValor", "") for c in campos if "remunera" in c.get("campoNome", "").lower()]
            remuneracao = next((r for r in remus if r and r.strip()), "")
            resultado.append({
                "Numero_Requerimento": numero,
                "Serie": lote.get("valorMobiliario"),
                "Valor_Serie": lote.get("valorTotalLote"),
                "Data_Emissao": campo(campos, "data de emiss"),
                "Data_Vencimento": campo(campos, "data de vencimento"),
                "Rating": campo(campos, "avalia"),
                "Remuneracao": remuneracao,
            })
    return resultado


engine = create_engine("sqlite:///data/mercado.db")

# 1) todos os requerimentos de debentures
todos = pd.read_sql("SELECT Numero_Requerimento FROM debentures", engine)

# 2) os que JA foram enriquecidos (se a tabela existir)
try:
    feitos_df = pd.read_sql("SELECT DISTINCT Numero_Requerimento FROM debentures_series", engine)
    feitos = set(feitos_df["Numero_Requerimento"])
except Exception:
    feitos = set()   # 1a vez: a tabela ainda nao existe

# 3) so os NOVOS (ainda nao enriquecidos)
novos = [n for n in todos["Numero_Requerimento"] if n not in feitos]
print(f"{len(novos)} novos requerimentos para enriquecer (de {len(todos)} no total).")

if not novos:
    print("Nada novo. Banco de debentures ja atualizado.")
    raise SystemExit

# 4) enriquecer so os novos
todas_series = []
total = len(novos)
for i, numero in enumerate(novos, start=1):
    todas_series.extend(buscar_detalhe_serie(numero))
    if i % 20 == 0 or i == total:
        print(f"  {i}/{total} processados...")

if not todas_series:
    print("Nenhuma serie coletada - verifique a conexao.")
    raise SystemExit

detalhes = pd.DataFrame(todas_series)

# 5) limpar tipos + prazo + indexador
detalhes["Data_Emissao"] = pd.to_datetime(detalhes["Data_Emissao"], format="%d/%m/%Y", errors="coerce")
detalhes["Data_Vencimento"] = pd.to_datetime(detalhes["Data_Vencimento"], format="%d/%m/%Y", errors="coerce")
detalhes["Valor_Serie"] = (
    detalhes["Valor_Serie"].astype(str)
    .str.replace(".", "", regex=False)
    .str.replace(",", ".", regex=False)
)
detalhes["Valor_Serie"] = pd.to_numeric(detalhes["Valor_Serie"], errors="coerce")
detalhes["Prazo_Anos"] = (detalhes["Data_Vencimento"] - detalhes["Data_Emissao"]).dt.days / 365.25
detalhes["Indexador"] = detalhes["Remuneracao"].apply(classificar_indexador)

# 6) ACRESCENTAR ao banco (nao substituir)
detalhes.to_sql("debentures_series", engine, if_exists="append", index=False)
print(f"\n{len(detalhes)} novas series adicionadas.")
print(detalhes["Indexador"].value_counts())