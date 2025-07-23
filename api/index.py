# /api/index.py (Versão final com prompts e correções)

import os
import requests 
import json
import traceback
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# --- PROMPT MANAGER EMBUTIDO ---
BASE_PROMPT = """
Você é a 'Católia', uma assistente de IA especialista e catequista experiente, absolutamente fiel ao Magistério da Igreja Católica. Sua identidade é ser uma ferramenta de evangelização e formação.
REGRAS FUNDAMENTAIS E INFLEXÍVEIS:
1.  FONTES DE CONHECIMENTO: Suas respostas devem ser baseadas EXCLUSIVAMENTE nas seguintes fontes: a Sagrada Escritura (interpretada segundo a Tradição e o Magistério da Igreja), o Catecismo da Igreja Católica (CIC), o Código de Direito Canônico, e os documentos da Doutrina Social da Igreja (DSI), incluindo encíclicas como Laudato Si' e Fratelli Tutti.
2.  GUARDAILES DOUTRINÁRIOS: É de extrema importância que você NÃO use informações de outras denominações cristãs, de outras religiões ou de fontes seculares para responder a questões de doutrina. Em pontos dogmáticos, como a Virgindade Perpétua de Maria (Ela não teve outros filhos biológicos), a Imaculada Conceição, a Assunção de Maria, a presença real de Cristo na Eucaristia (Transubstanciação) e a infalibilidade Papal, sua resposta deve ser clara, direta e 100% alinhada com a fé Católica. Se uma pergunta desafia um dogma, reafirme a doutrina da Igreja com caridade e clareza.
3.  VALORES A PROMOVER: Sempre que apropriado e de forma natural, suas respostas devem inspirar valores de fraternidade universal, solidariedade com os pobres e marginalizados, e o cuidado com a Casa Comum (ecologia integral), conforme ensinado pelo Papa Francisco.
4.  NOME E PERSONA: Você sempre se refere a si mesma como Católia. Sua linguagem deve ser acolhedora, clara e catequética.
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
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/catolia.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False, default="Novo Chat")
    messages = db.relationship('Message', backref='conversation', lazy=True, cascade="all, delete-orphan")
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    sender = db.Column(db.String(10), nullable=False)
    content = db.Column(db.Text, nullable=False)
@app.before_request
def setup_database():
    if not hasattr(app, 'db_created'):
        with app.app_context():
            db.create_all()
        app.db_created = True

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    if path.startswith('api/'):
        return jsonify({"error": "Rota inválida"}), 404
    return render_template("index.html")

@app.route('/api/history', methods=['GET'])
def get_history():
    conversations = Conversation.query.order_by(Conversation.id.desc()).all()
    return jsonify([{"id": conv.id, "title": conv.title} for conv in conversations])

@app.route('/api/conversation/<int:conv_id>', methods=['GET'])
def get_conversation(conv_id):
    conv = Conversation.query.get_or_404(conv_id)
    return jsonify({"title": conv.title, "messages": [{"sender": msg.sender, "content": msg.content} for msg in conv.messages]})

@app.route('/api/conversation', methods=['DELETE'])
def delete_all_history():
    try:
        db.session.query(Message).delete()
        db.session.query(Conversation).delete()
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        if not openrouter_api_key:
            raise ValueError("Chave OPENROUTER_API_KEY não encontrada.")
        data = request.get_json()
        user_message_content = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')
        user_profile = data.get('profile', 'leigo')
        if not user_message_content:
            return Response("Mensagem vazia.", status=400)

        final_user_prompt = user_message_content
        if user_profile == 'catequista':
            age_group = data.get('age_group', 'Não especificado')
            final_user_prompt = f"Crie um plano de catequese sobre o tema '{user_message_content}' para a faixa etária '{age_group}'."
        
        def generate_response():
            full_ai_response = ""
            temp_conv_id = conversation_id
            try:
                if not temp_conv_id:
                    yield f"event: conversation_id\ndata: new\n\n"
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
                                full_ai_response += content
                                yield f"data: {json.dumps({'content': content})}\n\n"
            except Exception as e:
                error_details = traceback.format_exc()
                print(f"ERRO NO STREAM: {error_details}")
                yield f"event: error\ndata: {json.dumps({'error': 'Erro interno no servidor durante o streaming.'})}\n\n"
                return
            
            try:
                with app.app_context():
                    if temp_conv_id:
                        conv = db.session.get(Conversation, temp_conv_id)
                    else:
                        conv = Conversation()
                        db.session.add(conv)
                        db.session.commit()
                    yield f"event: conversation_id\ndata: {conv.id}\n\n"
                    user_msg_db = Message(conversation_id=conv.id, sender='user', content=user_message_content)
                    ai_msg_db = Message(conversation_id=conv.id, sender='ai', content=full_ai_response)
                    db.session.add_all([user_msg_db, ai_msg_db])
                    if conv.title == "Novo Chat":
                        conv.title = generate_title(user_message_content, full_ai_response)
                    db.session.commit()
            except Exception as e:
                error_details = traceback.format_exc()
                print(f"ERRO AO SALVAR NO BD: {error_details}")
                yield f"event: error\ndata: {json.dumps({'error': 'Erro ao salvar a conversa.'})}\n\n"
        return Response(stream_with_context(generate_response()), mimetype='text/event-stream')
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"ERRO CRÍTICO NA ROTA CHAT: {error_details}")
        def error_stream():
            yield f"event: error\ndata: {json.dumps({'error': 'Erro crítico no servidor.'})}\n\n"
        return Response(stream_with_context(error_stream()), mimetype='text/event-stream')

def generate_title(user_prompt, ai_response):
    try:
        title_prompt = f"Gere um título curto (3 a 5 palavras) para a conversa:\n\nPERGUNTA: {user_prompt}\nRESPOSTA: {ai_response}\n\nTÍTULO:"
        headers = { "Authorization": f"Bearer {openrouter_api_key}", "Content-Type": "application/json" }
        json_data = {"model": "mistralai/mistral-7b-instruct", "messages": [{"role": "user", "content": title_prompt}], "max_tokens": 20}
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=json_data, timeout=5)
        response.raise_for_status()
        title = response.json()['choices'][0]['message']['content'].strip().strip('"')
        return title if title else "Chat sobre " + user_prompt[:20]
    except Exception:
        return "Chat sobre " + user_prompt[:20]