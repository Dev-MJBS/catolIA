#!/bin/bash

PROJECT_DIR="/home/job/Gemini_Education"

VENV_DIR="venv"

APP_FILE="app.py"

FLASK_PORT="5000"

APP_URL="http://127.0.0.1:${FLASK_PORT}"

echo "--- Iniciando o Chat Gemini ---"
echo "Verificando dependências e iniciando o servidor Flask..."

cd "$PROJECT_DIR" || { echo "Erro: Não foi possível encontrar o diretório do projeto: $PROJECT_DIR"; exit 1; }

if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate" || { echo "Erro: Não foi possível ativar o ambiente virtual."; exit 1; }
    echo "Ambiente virtual '$VENV_DIR' ativado."
else
    echo "Aviso: Ambiente virtual '$VENV_DIR' não encontrado. Tentando rodar sem ele (pode causar problemas)."
fi

if [ ! -f "$APP_FILE" ]; then
    echo "Erro: Arquivo do aplicativo '$APP_FILE' não encontrado em $PROJECT_DIR."
    exit 1
fi

echo "Abrindo o chat no navegador: $APP_URL"
(sleep 2 && xdg-open "$APP_URL") &

echo "Servidor Flask iniciando..."
exec python "$APP_FILE"

echo "--- Chat Gemini Encerrado ---"