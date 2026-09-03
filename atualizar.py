# atualizar.py — roda toda a coleta diaria do MIH, em sequencia.
#
# Uso:
#     python atualizar.py            # roda a coleta
#     python atualizar.py --teste    # roda os auto-testes deste arquivo
#
# Cada passo reporta sucesso ou falha, e o script termina com codigo diferente
# de zero se algum passo falhou. Antes disso os subprocess.run eram disparados
# sem verificar retorno nenhum: um coletor podia quebrar e o script ainda
# imprimia "Pronto! Todos os dados foram atualizados" - a falha passava
# despercebida justamente porque isto roda desatendido, agendado.
import subprocess
import sys

PASSOS = [
    ("dolar (USD/BRL)", "coleta.py"),
    ("indicadores do BCB", "coleta_bcb.py"),
    ("lista de debentures (CVM)", "coleta_debentures.py"),
    ("enriquecimento de debentures", "enriquecer_debentures.py"),
    ("noticias", "coleta_noticias.py"),
    ("classificacao de noticias com IA", "classificar_noticias.py"),
    ("cadeia de opcoes B3", "modules/opcoes/coleta_opcoes.py"),
    ("briefing do dia", "briefing.py"),
    ("envio do briefing por e-mail", "enviar_briefing.py"),
    ("alertas", "alertas.py"),
]


def rodar(nome: str, script: str, executavel: str | None = None) -> bool:
    """Roda um passo da coleta. Devolve True se terminou com codigo 0.

    Nao levanta excecao em caso de falha: a coleta diaria deve seguir para os
    passos seguintes mesmo quando um coletor quebra (uma fonte fora do ar nao
    deve impedir as outras). Quem chama e' responsavel por somar as falhas e
    refleti-las no codigo de saida."""
    print(f"\n>>> {nome}...", flush=True)
    resultado = subprocess.run([executavel or sys.executable, script])
    if resultado.returncode == 0:
        return True
    print(f"!!! FALHOU: {nome} (codigo {resultado.returncode})", flush=True)
    return False


def executar(passos=None) -> list[str]:
    """Roda todos os passos e devolve a lista de nomes que falharam."""
    falhas = []
    for nome, script in (passos or PASSOS):
        if not rodar(nome, script):
            falhas.append(nome)
    return falhas


def resumir(falhas: list[str], total: int) -> str:
    if not falhas:
        return f"Pronto! Os {total} passos foram atualizados com sucesso."
    lista = "\n".join(f"  - {nome}" for nome in falhas)
    return (f"ATENCAO: {len(falhas)} de {total} passos FALHARAM:\n{lista}\n"
            f"Os demais foram atualizados.")


def _auto_teste() -> None:
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        ok = os.path.join(tmp, "passa.py")
        with open(ok, "w", encoding="utf-8") as f:
            f.write("print('ok')\n")
        ruim = os.path.join(tmp, "falha.py")
        with open(ruim, "w", encoding="utf-8") as f:
            f.write("import sys; sys.exit(1)\n")

        # Caso 1: rodar() distingue sucesso de falha pelo codigo de saida
        assert rodar("passo que passa", ok) is True
        assert rodar("passo que falha", ruim) is False
        print("[OK] Caso 1: rodar() distingue sucesso de falha pelo codigo de saida.")

        # Caso 2: um passo que falha NAO interrompe os seguintes - uma fonte
        # fora do ar nao pode impedir a coleta das outras
        falhas = executar([("primeiro", ok), ("do meio", ruim), ("ultimo", ok)])
        assert falhas == ["do meio"], falhas
        print("[OK] Caso 2: falha no meio nao interrompe os passos seguintes.")

    # Caso 3: o resumo nomeia quem falhou, e nao mente quando ha falha
    texto_ok = resumir([], 10)
    assert "sucesso" in texto_ok and "FALHARAM" not in texto_ok
    texto_ruim = resumir(["noticias", "alertas"], 10)
    assert "2 de 10" in texto_ruim
    assert "noticias" in texto_ruim and "alertas" in texto_ruim
    assert "Pronto!" not in texto_ruim   # nao pode declarar sucesso com falha na lista
    print("[OK] Caso 3: resumo nomeia os passos que falharam e nao declara sucesso.")

    print("\nTodos os casos passaram.")


if __name__ == "__main__":
    if "--teste" in sys.argv:
        _auto_teste()
    else:
        falhas = executar()
        print("\n" + resumir(falhas, len(PASSOS)))
        # Codigo de saida diferente de zero quando algo falhou: e' o que
        # permite ao agendador do Windows (ou a qualquer wrapper) perceber
        # que a coleta do dia nao esta' integra.
        sys.exit(1 if falhas else 0)
