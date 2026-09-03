@echo off
cd /d C:\Users\aliss\projetos\plataforma-mercado

REM .venv (com ponto) e nao venv: existem os dois ambientes nesta maquina, e
REM so' o .venv tem scipy - de que os modulos de opcoes dependem. Apontar para
REM o venv antigo faria a coleta de opcoes quebrar na importacao.
.venv\Scripts\python.exe atualizar.py

REM ERRORLEVEL diferente de zero significa que algum passo falhou; o
REM atualizar.py ja imprimiu quais. Mantem a janela aberta nesse caso para a
REM falha nao passar despercebida numa execucao manual.
if errorlevel 1 (
    echo.
    echo *** A coleta terminou COM FALHAS - veja a lista acima. ***
    pause
)
