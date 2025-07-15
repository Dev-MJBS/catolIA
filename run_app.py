import os
import subprocess
import sys
import time
from pathlib import Path

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent

os.environ['DOTENV_PATH'] = str(BASE_DIR / ".env")

os.environ['FLASK_TEMPLATES_PATH'] = str(BASE_DIR / "templates")

from app import app as flask_app

FLASK_PORT = "5000"
APP_URL = f"http://127.0.0.1:{FLASK_PORT}"

def open_browser(url):
    try:
        subprocess.Popen(['xdg-open', url])
        print(f"Abrindo o navegador em: {url}")
    except FileNotFoundError:
        print(f"Não foi possível abrir o navegador automaticamente. Por favor, acesse: {url}")
    except Exception as e:
        print(f"Erro ao tentar abrir o navegador: {e}")

print("Iniciando o servidor Flask...")

subprocess.Popen([sys.executable, "-c", f"import time; time.sleep(2); import webbrowser; webbrowser.open_new_tab('{APP_URL}')"])

print(f"Servidor Flask rodando em: {APP_URL}")
flask_app.run(debug=False, port=int(FLASK_PORT))