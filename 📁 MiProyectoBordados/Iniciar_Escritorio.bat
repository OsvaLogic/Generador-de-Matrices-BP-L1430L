@echo off
echo Iniciando la Aplicacion de Escritorio (PyQt6)...
cd /d "%~dp0"
call venv\Scripts\activate
python desktop_app\main.py
pause