@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set "PYEXE="
where py >nul 2>&1 && set "PYEXE=py"
if not defined PYEXE (
  where python >nul 2>&1 && set "PYEXE=python"
)
if not defined PYEXE (
  echo Python 3 not found. Install from https://www.python.org/downloads/
  pause & exit /b
)
%PYEXE% "%~dp0diagnose.py"
