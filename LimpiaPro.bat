@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    start "" py -3.12 limpiador.py
) else (
    start "" python limpiador.py
)
