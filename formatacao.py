"""
formatacao.py - Formatacao BR de datas e valores monetarios, compartilhada
entre paginas. Extraido de app.py sem mudanca de comportamento.
"""
import pandas as pd


def formatar_data_br(data):
    if pd.isna(data):
        return ""
    if isinstance(data, str):
        data = pd.to_datetime(data)
    return data.strftime("%d/%m/%Y")


def formatar_moeda(valor):
    if pd.isna(valor):
        return ""
    return f"R$ {valor:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


if __name__ == "__main__":
    import datetime

    assert formatar_data_br(datetime.datetime(2026, 8, 29)) == "29/08/2026"
    assert formatar_data_br("2026-08-29") == "29/08/2026"
    assert formatar_data_br(None) == ""
    print("[OK] Caso 1: formatar_data_br cobre datetime, string e None.")

    assert formatar_moeda(1234.5) == "R$ 1.234,50"
    assert formatar_moeda(None) == ""
    print("[OK] Caso 2: formatar_moeda cobre valor normal e None.")

    print("\nTodos os casos passaram.")
