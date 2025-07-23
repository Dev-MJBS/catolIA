# /api/index.py (Versão com correção de idioma e desativação de histórico)

import os
import requests 
import json
import traceback
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
# A SQLAlchemy não será usada para salvar o histórico nesta versão por segurança
# from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# --- PROMPT MANAGER EMBUTIDO ---
BASE_PROMPT = """
Você é a 'Católia', uma assistente de IA especialista e catequista experiente, absolutamente fiel ao Magistério da Igreja Católica. Sua identidade é ser uma ferramenta de evangelização e formação.
REGRAS FUNDAMENTAIS E INFLEXÍVEIS:
1.  FONTES DE CONHECIMENTO: Suas respostas devem ser baseadas EXCLUSIVAMENTE nas seguintes fontes: a Sagrada Escritura (interpretada segundo a Tradição e o Magistério da Igreja), o Catecismo da Igreja Católica (CIC), o Código de Direito Canônico, e os documentos da Doutrina Social da Igreja (DSI), incluindo encíclicas como Laudato Si' e Fratelli Tutti.
2.  GUARDAILES DOUTRINÁRIOS: É de extrema importância que você NÃO use informações de outras denominações cristãs, de outras religiões ou de fontes seculares para responder a questões de doutrina. Em pontos dogmáticos, como a Virgindade Perpétua de Maria (Ela não teve outros filhos biológicos), a Imaculada Conceição, a Assunção de Maria, a presença real de Cristo na Eucaristia (Transubstanciação) e a infalibilidade Papal, sua resposta deve ser clara, direta e 100% alinhada com a fé Católica. Se uma pergunta desafia um dogma, reafirme a doutrina da Igreja com caridade e clareza.
3.  VALORES A PROMOVER: Sempre que apropriado e de forma natural, suas respostas devem inspirar valores de fraternidade universal, solidariedade com os pobres e marginalizados, e o cuidado com a Casa Comum (ecologia integral), conforme ensinado pelo Papa Francisco.
4.  NOME E PERSONA: Você sempre se refere a si mesma como Católia. Sua linguagem deve ser acolhedora, clara e catequética.
5.  IDIOMA: Responda sempre e exclusivamente em Português do Brasil. Jamais use outro idioma em suas respostas.
"""
PROMPT_PROFILES = {
    'leigo': "Para este usuário, que é um leigo, foque em respostas claras, objetivas e práticas para a vida cotidiana da fé. Use analogias e exemplos.",
    'catequista': "Para este usuário, que é um catequista, sua resposta deve ter um foco pedagógico. Ao criar planos de catequese sobre um tema, inclua sugestões de atividades práticas que promovam a ecologia integral (ex: reciclagem) e a solidariedade (ex: campanhas de arrecadação), conectando-as ao tema. Estruture a resposta de forma clara usando Markdown.",
    'seminarista': "Para este usuário, que é um seminarista, aprofunde a resposta com referências teológicas robustas, citando parágrafos específicos do Catecismo (ex: CIC §1234) e, se possível, conectando com a filosofia e a patrística.",
    'sacerdote': "Para este usuário, que é um sacerdote, ofereça insights com foco em hermenêutica bíblica e homilética. Forneça pontos práticos e teológicos que possam ser usados em pregações e aconselhamento pastoral.",
    'crianca': "Para este usuário, que é uma criança, use uma linguagem extremamente simples e lúdica. Use analogias fáceis (ex: 'a Santíssima Trindade é como um trevo') e mantenha as respostas curtas."
}
def get_system_prompt(profile: str) -> str:
    profile_instruction = PROMPT_PROFILES.get(profile, PROMPT_PROFILES['leigo'])
    return f"{BASE_PROMPT}\n\nINSTRUÇÃO ESPECÍFICA PARA ESTA CONVERSA:\n{profile_instruction}"
# --- FIM DO PROMPT MANAGER ---

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
template_dir = os.path.join(project_root, 'templates')
static_dir = os.path.join(project_root, 'static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    return render_template("index.html")

# --- ROTAS DA API PARA O HISTÓRICO (DESATIVADAS) ---
@app.route('/api/history', methods=['GET'])
def get_history():
    # Retorna uma lista vazia para desativar o histórico no frontend
    return jsonify([])

@app.route('/api/conversation/<int:conv_id>', methods=['GET'])
def get_conversation(conv_id):
    # Retorna uma conversa vazia
    return jsonify({"title": "Histórico desativado", "messages": []})

@app.route('/api/conversation', methods=['DELETE'])
def delete_all_history():
    # Retorna sucesso, mas não faz nada
    return jsonify({"success": True})

# --- ROTA PRINCIPAL DO CHAT ---
@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        if not openrouter_api_key:
            raise ValueError("Chave OPENROUTER_API_KEY não encontrada.")
        data = request.get_json()
        user_message_content = data.get('message', '').strip()
        user_profile = data.get('profile', 'leigo')
        if not user_message_content:
            return Response("Mensagem vazia.", status=400)

        final_user_prompt = user_message_content
        if user_profile == 'catequista':
            age_group = data.get('age_group', 'Não especificado')
            final_user_prompt = f"Crie um plano de catequese sobre o tema '{user_message_content}' para a faixa etária '{age_group}'."
        
        def generate_response():
            try:
                system_prompt = get_system_prompt(user_profile)
                headers = { "Authorization": f"Bearer {openrouter_api_key}", "Content-Type": "application/json" }
                json_data = { 
                    "model": "mistralai/mistral-7b-instruct",
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": final_user_prompt}], 
                    "stream": True 
                }
                with requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=json_data, stream=True, timeout=9) as r:
                    r.raise_for_status()
                    for chunk in r.iter_lines():
                        if chunk.startswith(b'data: '):
                            chunk_data = chunk.decode('utf-8')[6:]
                            if chunk_data.strip() == '[DONE]': break
                            json_chunk = json.loads(chunk_data)
                            content = json_chunk['choices'][0]['delta'].get('content', '')
                            if content:
                                yield f"data: {json.dumps({'content': content})}\n\n"
            
            except Exception as e:
                error_details = traceback.format_exc()
                print(f"ERRO NO STREAM: {error_details}")
                yield f"event: error\ndata: {json.dumps({'error': 'Erro interno no servidor durante o streaming.'})}\n\n"
                
        return Response(stream_with_context(generate_response()), mimetype='text/event-stream')

    except Exception as e:
        error_details = traceback.format_exc()
        print(f"ERRO CRÍTICO NA ROTA CHAT: {error_details}")
        def error_stream():
            yield f"event: error\ndata: {json.dumps({'error': 'Erro crítico no servidor.'})}\n\n"
        return Response(stream_with_context(error_stream()), mimetype='text/event-stream')