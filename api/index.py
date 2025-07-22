# /api/index.py (CÓDIGO DE DIAGNÓSTICO TEMPORÁRIO)

import os
from flask import Flask, Response

app = Flask(__name__)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def inspect_environment(path):
    html_output = """
    <html>
        <head><title>Inspetor de Ambiente Vercel</title></head>
        <body style="font-family: monospace; background-color: #121212; color: #EAEAEA; padding: 20px;">
            <h1>Variáveis de Ambiente Visíveis para a Aplicação:</h1>
            <pre>
    """

    variables = sorted(os.environ.items())

    found_key = False
    for key, value in variables:
        if key == "OPENROUTER_API_KEY":
            value_to_show = f"***ENCONTRADA*** (comprimento: {len(value)})"
            found_key = True
        else:
            # Esconde valores de outras chaves potencialmente sensíveis
            value_to_show = f"{value[:4]}..." if len(value) > 4 else value

        html_output += f"{key} = {value_to_show}\n"

    if not found_key:
        html_output += "\n\n<h2 style='color: red;'>ERRO: A variável OPENROUTER_API_KEY NÃO FOI ENCONTRADA!</h2>"

    html_output += """
            </pre>
        </body>
    </html>
    """

    return Response(html_output, mimetype='text/html')