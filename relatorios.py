"""
relatorios.py - Gera relatórios formatados em .xlsx com padrão BR.

Formatos BR:
- Datas: dd/mm/aaaa
- Números: usar locale 'pt_BR' (separador decimal virgula, milhar ponto)
- Moeda: R$ com 2 decimais
- Taxa: % com 2-4 casas decimais

Saídas:
- relatorio_debentures.xlsx: emissões com CDI+X%, spread, prazo
- relatorio_indicadores.xlsx: série temporal de Selic, CDI, IPCA, IGP-M
- relatorio_dolar.xlsx: histórico USD/BRL
"""

import pandas as pd
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows
from db import engine


def formatar_moeda(valor):
    """Formata valor numérico como R$ dd.ddd,dd."""
    if pd.isna(valor):
        return ""
    return f"R$ {valor:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def formatar_taxa(valor):
    """Formata taxa como X,XX% ou X,XXXX%."""
    if pd.isna(valor):
        return ""
    return f"{valor:.2f}%"


def formatar_data_br(data):
    """Converte data para dd/mm/aaaa."""
    if pd.isna(data):
        return ""
    if isinstance(data, str):
        data = pd.to_datetime(data)
    return data.strftime("%d/%m/%Y")


def gerar_relatorio_debentures():
    """Gera relatório de debêntures com spread, indexador e formatação BR."""
    try:
        # Juntar series com ofertas
        series = pd.read_sql("SELECT * FROM debentures_series", engine)
        ofertas = pd.read_sql(
            """
            SELECT numero_requerimento, nome_emissor, cnpj_emissor, emissao,
                   data_requerimento, data_encerramento, valor_total_registrado,
                   nome_lider, agente_fiduciario, titulo_incentivado
            FROM debentures
            """,
            engine,
        )
        
        deb = series.merge(ofertas, on="numero_requerimento", how="left")
        
        # Selecionar e renomear colunas
        relatorio = deb[[
            'numero_requerimento', 'nome_emissor', 'serie',
            'indexador', 'spread', 'valor_serie', 'prazo_anos',
            'data_emissao', 'data_vencimento', 'rating',
            'valor_total_registrado', 'data_requerimento'
        ]].copy()
        
        relatorio.columns = [
            'Requerimento', 'Emissor', 'Serie',
            'Indexador', 'Spread (%)', 'Valor (R$)', 'Prazo (anos)',
            'Emissao', 'Vencimento', 'Rating',
            'Volume Total (R$)', 'Data Req.'
        ]
        
        # Formatar datas
        for col_data in ['Emissao', 'Vencimento', 'Data Req.']:
            relatorio[col_data] = relatorio[col_data].apply(formatar_data_br)
        
        # Formatar moedas e taxas
        relatorio['Valor (R$)'] = relatorio['Valor (R$)'].apply(formatar_moeda)
        relatorio['Volume Total (R$)'] = relatorio['Volume Total (R$)'].apply(formatar_moeda)
        relatorio['Spread (%)'] = relatorio['Spread (%)'].apply(formatar_taxa)
        relatorio['Prazo (anos)'] = relatorio['Prazo (anos)'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")
        
        # Salvar em Excel
        arquivo = "relatorio_debentures.xlsx"
        relatorio.to_excel(arquivo, sheet_name="Debentures", index=False)
        print(f"[OK] Relatório de debêntures salvo: {arquivo}")
        return arquivo
    except Exception as e:
        print(f"[ERRO] Falha ao gerar relatório de debêntures: {e}")
        return None


def gerar_relatorio_indicadores():
    """Gera relatório de série temporal de indicadores macro."""
    try:
        ind = pd.read_sql(
            "SELECT indicador, data, valor FROM indicadores_bcb ORDER BY data DESC",
            engine
        )
        
        # Pivotar por indicador
        relatorio = ind.pivot_table(index='data', columns='indicador', values='valor')
        relatorio.columns.name = None
        relatorio = relatorio.reset_index()
        relatorio.columns = ['Data', 'CDI (%)', 'IPCA (% mês)', 'IGP-M (% mês)', 'Selic (% a.a.)']
        
        # Formatar data
        relatorio['Data'] = relatorio['Data'].apply(formatar_data_br)
        
        # Formatar taxas
        for col in ['CDI (%)', 'IPCA (% mês)', 'IGP-M (% mês)', 'Selic (% a.a.)']:
            relatorio[col] = relatorio[col].apply(formatar_taxa)
        
        # Salvar
        arquivo = "relatorio_indicadores.xlsx"
        relatorio.to_excel(arquivo, sheet_name="Indicadores", index=False)
        print(f"[OK] Relatório de indicadores salvo: {arquivo}")
        return arquivo
    except Exception as e:
        print(f"[ERRO] Falha ao gerar relatório de indicadores: {e}")
        return None


def gerar_relatorio_dolar():
    """Gera relatório do dólar USD/BRL com formatação."""
    try:
        dolar = pd.read_sql(
            "SELECT date, close, high, low, open, volume FROM usd_brl ORDER BY date DESC",
            engine
        )
        
        relatorio = dolar.copy()
        relatorio.columns = ['Data', 'Fechamento', 'Maxima', 'Minima', 'Abertura', 'Volume']
        
        # Formatar data
        relatorio['Data'] = relatorio['Data'].apply(formatar_data_br)
        
        # Formatar moedas/taxas
        for col in ['Fechamento', 'Maxima', 'Minima', 'Abertura']:
            relatorio[col] = relatorio[col].apply(lambda x: f"R$ {x:.4f}" if pd.notna(x) else "")
        
        relatorio['Volume'] = relatorio['Volume'].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "")
        
        # Salvar (sem barra no nome da sheet)
        arquivo = "relatorio_dolar.xlsx"
        relatorio.to_excel(arquivo, sheet_name="Dolar", index=False)
        print(f"[OK] Relatório do dólar salvo: {arquivo}")
        return arquivo
    except Exception as e:
        print(f"[ERRO] Falha ao gerar relatório do dólar: {e}")
        return None


def exportar_todos_relatorios():
    """Gera todos os relatórios e retorna lista de arquivos."""
    print("=== Gerando Relatórios ===\n")
    arquivos = []
    
    arquivo = gerar_relatorio_debentures()
    if arquivo:
        arquivos.append(arquivo)
    
    arquivo = gerar_relatorio_indicadores()
    if arquivo:
        arquivos.append(arquivo)
    
    arquivo = gerar_relatorio_dolar()
    if arquivo:
        arquivos.append(arquivo)
    
    print(f"\n[OK] {len(arquivos)} relatórios gerados!")
    return arquivos


if __name__ == "__main__":
    exportar_todos_relatorios()
