@echo off
rem Abre o eSocial numa janela InPrivate do Edge e já clica em "Entrar com gov.br" e "Seu certificado digital".
rem Depois é só escolher o certificado da Drillgeo e digitar o PIN.
chcp 65001 >nul
set "AQUI=%~dp0"
where py >nul 2>nul && (py -3 "%AQUI%abrir_esocial_certificado.py" %* & goto fim)
where python >nul 2>nul && (python "%AQUI%abrir_esocial_certificado.py" %* & goto fim)
echo Python nao encontrado neste computador. Abrindo o eSocial sem o clique automatico...
start "" msedge --inprivate https://login.esocial.gov.br/login.aspx
:fim
timeout /t 4 >nul
