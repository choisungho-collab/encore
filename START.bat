@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "PYEXE="
where py >nul 2>&1 && set "PYEXE=py"
if not defined PYEXE (
  where python >nul 2>&1 && set "PYEXE=python"
)
if not defined PYEXE goto nopy

%PYEXE% "%~dp0sc_recorder.py"
echo.
pause
exit /b

:nopy
echo.
echo  [!] Python 3 was not found on this PC.
echo.
echo      1. Install Python 3 from https://www.python.org/downloads/
echo      2. During install, CHECK "Add python.exe to PATH"
echo      3. Run this file (START.bat) again.
echo.
pause
