@echo off
setlocal EnableDelayedExpansion
title LimpiaPro v2.3 - Release Tool

echo ============================================================
echo   LimpiaPro v2.3 - Release Tool
echo   %date% %time%
echo ============================================================
echo.

cd /d "%~dp0"

echo Directorio: %CD%
echo.

REM Verificar que existe python
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set PYTHON=py -3.12
) else (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 (
        set PYTHON=python
    ) else (
        echo ERROR: No se encontro Python en el sistema.
        echo Instala Python 3.12+ desde https://python.org
        pause
        exit /b 1
    )
)

echo Python: %PYTHON%
echo.

REM Verificar que existe git
where git >nul 2>nul
if %ERRORLEVEL%==0 (
    echo Git: encontrado
) else (
    echo ADVERTENCIA: git no esta instalado. El commit/tag no se hara.
)

echo.
echo Iniciando release_tool.py...
echo.

%PYTHON% release_tool.py %*

if %ERRORLEVEL%==0 (
    echo.
    echo ============================================================
    echo   RELEASE EXITOSO
    echo ============================================================
    echo.
    echo El acceso directo de LimpiaPro esta en tu escritorio.
    echo.
) else (
    echo.
    echo ============================================================
    echo   RELEASE FALLIDO
    echo ============================================================
    echo Revisa los errores anteriores.
)

pause
