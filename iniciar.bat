@echo off
cd /d "%~dp0"
if not exist .venv (
  echo Criando ambiente virtual...
  python -m venv .venv
  call .venv\Scripts\activate
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate
)
if not exist .env copy .env.example .env >nul
start "" http://127.0.0.1:5001
python app.py
