@echo off
cd /d "%~dp0"
git --no-optional-locks status
echo ---
git log -1
echo ---
git remote -v
