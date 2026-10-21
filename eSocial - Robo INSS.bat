@echo off
rem Robo eSocial INSS: entra (gov.br > certificado), roda os scripts de 10 em 10, sai, abre aba nova e repete ate o fim.
rem Voce so escolhe o certificado na primeira vez. Para recomecar de uma parte: arraste este arquivo para o Prompt e acrescente  --desde N
chcp 65001 >nul
title Robo eSocial INSS
set "AQUI=%~dp0"
where py >nul 2>nul || (echo Python nao encontrado neste computador. & pause & exit /b 1)
py -3 "%AQUI%robo_esocial.py" inss %*
echo.
pause
