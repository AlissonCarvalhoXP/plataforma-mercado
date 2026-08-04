# enriquecer_debentures.py
import re
import requests
import pandas as pd
from db import engine


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
                "numero_requerimento": numero,
                "serie": lote.get("valorMobiliario"),
                "valor_serie": lote.get("valorTotalLote"),
                "data_emissao": campo(campos, "data de emiss"),
                "data_vencimento": campo(campos, "data de vencimento"),
                "rating": campo(campos, "avalia"),
                "remuneracao": remuneracao,
            })
    return resultado


todos = pd.read_sql("SELECT numero_requerimento FROM debentures", engine)

try:
    feitos_df = pd.read_sql("SELECT DISTINCT numero_requerimento FROM debentures_series", engine)
    feitos = set(feitos_df["numero_requerimento"])
except Exception:
    feitos = set()

novos = [n for n in todos["numero_requerimento"] if n not in feitos]
print(f"{len(novos)} novos requerimentos para enriquecer (de {len(todos)} no total).")

if not novos:
    print("Nada novo. Banco de debentures ja atualizado.")
    raise SystemExit

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
detalhes["data_emissao"] = pd.to_datetime(detalhes["data_emissao"], format="%d/%m/%Y", errors="coerce")
detalhes["data_vencimento"] = pd.to_datetime(detalhes["data_vencimento"], format="%d/%m/%Y", errors="coerce")
detalhes["valor_serie"] = (
    detalhes["valor_serie"].astype(str)
    .str.replace(".", "", regex=False)
    .str.replace(",", ".", regex=False)
)
detalhes["valor_serie"] = pd.to_numeric(detalhes["valor_serie"], errors="coerce")
detalhes["prazo_anos"] = (detalhes["data_vencimento"] - detalhes["data_emissao"]).dt.days / 365.25
detalhes["indexador"] = detalhes["remuneracao"].apply(classificar_indexador)

detalhes.to_sql("debentures_series", engine, if_exists="append", index=False,
                chunksize=500, method="multi")
print(f"\n{len(detalhes)} novas series adicionadas.")
print(detalhes["indexador"].value_counts())