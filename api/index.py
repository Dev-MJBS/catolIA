# /api/index.py (CÓDIGO DE DIAGNÓSTICO TEMPORÁRIO - Versão 2)

import os
from flask import Flask, Response

app = Flask(__name__)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def inspect_environment(path):
    html_output = "<html><body style='font-family: monospace; background-color: #121212; color: #EAEAEA; padding: 20px;'>"
    html_output += "<h1>Inspetor de Ambiente Vercel</h1><pre>"

    variables = sorted(os.environ.items())

    # PROCURANDO PELA NOVA CHAVE DE TESTE
    found_key = False
    for key, value in variables:
        value_to_show = f"{value[:4]}..." if len(value) > 4 else value
        html_output += f"{key} = {value_to_show}\n"
        if key == "TEST_KEY":
            found_key = True
            html_output += f"--> CHAVE DE TESTE ENCONTRADA! (comprimento: {len(value)})\n"

    if not found_key:
        html_output += "\n\n<h2 style='color: red;'>ERRO: A variável TEST_KEY NÃO FOI ENCONTRADA!</h2>"

    html_output += "</pre></body></html>"

    return Response(html_output, mimetype='text/html')