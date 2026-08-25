@echo off
where gh 2>nul
if %errorlevel%==0 (
    echo GH_FOUND
) else (
    echo GH_NOT_FOUND
)
