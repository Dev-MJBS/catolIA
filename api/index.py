# /api/index.py (Versão com Lógica de BD Refatorada e Segura)

import os
import requests 
import json
import traceback
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Esta versão NÃO USA a biblioteca dotenv
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages = db.relationship('Message', backref='conversation', lazy=True, cascade="all, delete-orphan")

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    sender = db.Column(db.String(10), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
        return jsonify({"error": "Esta rota é inválida"}), 404
    return render_template("index.html")

# --- ROTAS DE HISTÓRICO (SEM MUDANÇAS) ---
@app.route('/api/history', methods=['GET'])
def get_history():
    conversations = Conversation.query.order_by(Conversation.created_at.desc()).all()
    history = [{"id": conv.id, "title": conv.title} for conv in conversations]
    return jsonify(history)

@app.route('/api/conversation/<int:conv_id>', methods=['GET'])
def get_conversation(conv_id):
    conversation = Conversation.query.get_or_404(conv_id)
    messages = [{"sender": msg.sender, "content": msg.content} for msg in conversation.messages]
    return jsonify({"title": conversation.title, "messages": messages})

@app.route('/api/conversation', methods=['DELETE'])
def delete_all_history():
    try:
        db.session.query(Message).delete()
        db.session.query(Conversation).delete()
        db.session.commit()
        return jsonify({"success": "Histórico apagado com sucesso."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# --- ROTA PRINCIPAL DO CHAT (COM LÓGICA REESTRUTURADA) ---
@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        if not openrouter_api_key:
            raise ValueError("A variável de ambiente OPENROUTER_API_KEY não foi encontrada.")

        data = request.get_json()
        user_message_content = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')
        user_profile = data.get('profile', 'leigo')
        
        if not user_message_content:
            return Response("Mensagem vazia.", status=400)

        # Prepara o prompt completo
        final_user_prompt = user_message_content
        if user_profile == 'catequista':
            age_group = data.get('age_group', 'Não especificado')
            final_user_prompt = f"Tema da Catequese: {user_message_content}\nFaixa Etária: {age_group}"

        # --- NOVA LÓGICA DE STREAMING ---
        def generate_response():
            full_ai_response = ""
            temp_conv_id = conversation_id
            
            # 1. OBTÉM A RESPOSTA DA IA PRIMEIRO (ISOLANDO A OPERAÇÃO DE REDE)
            try:
                # Envia um ID temporário se for um novo chat, para o frontend saber que é um novo chat
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
                print(f"ERRO DURANTE O STREAMING DA API: {error_details}")
                yield f"event: error\ndata: {json.dumps({'error': 'Erro ao comunicar com a IA.'})}\n\n"
                return # Para a execução aqui se a IA falhar

            # 2. SALVA TUDO NO BANCO DE DADOS DE UMA SÓ VEZ (APÓS O SUCESSO DA IA)
            try:
                with app.app_context():
                    if temp_conv_id:
                        conv = db.session.get(Conversation, temp_conv_id)
                    else:
                        conv = Conversation()
                        db.session.add(conv)
                        db.session.commit() # Salva para obter o ID real
                    
                    # Envia o ID real para o frontend
                    yield f"event: conversation_id\ndata: {conv.id}\n\n"

                    user_msg_db = Message(conversation_id=conv.id, sender='user', content=user_message_content)
                    ai_msg_db = Message(conversation_id=conv.id, sender='ai', content=full_ai_response)
                    db.session.add_all([user_msg_db, ai_msg_db])

                    if conv.title == "Novo Chat":
                        conv.title = generate_title(user_message_content, full_ai_response)
                    
                    db.session.commit()
            
            except Exception as e:
                error_details = traceback.format_exc()
                print(f"ERRO AO SALVAR NO BANCO DE DADOS: {error_details}")
                yield f"event: error\ndata: {json.dumps({'error': 'Erro ao salvar a conversa.'})}\n\n"

        return Response(stream_with_context(generate_response()), mimetype='text/event-stream')

    except Exception as e:
        error_details = traceback.format_exc()
        print(f"ERRO CRÍTICO NA ROTA CHAT: {error_details}")
        def error_stream():
            yield f"event: error\ndata: {json.dumps({'error': 'Erro crítico no servidor.'})}\n\n"
        return Response(stream_with_context(error_stream()), mimetype='text/event-stream')

def get_system_prompt(profile):
    bible_citation_rule = "Ao citar passagens bíblicas, use sempre o formato 'Livro Capítulo, Versículo' (ex: 'Mateus 1,1')."
    instructions = { 'crianca': f"...", 'catequista': f"...", 'seminarista': f"...", 'sacerdote': f"...", 'leigo': f"..." }
    instructions['catequista'] = f"Você é uma IA católica para catequistas. Crie um plano de encontro de catequese detalhado e estruturado. Use Markdown para formatar a resposta com títulos, negrito e listas."
    instructions['leigo'] = f"Você é uma IA católica. Responda de forma clara, objetiva e completa para um leigo interessado em aprofundar sua fé. {bible_citation_rule}"
    return instructions.get(profile, instructions['leigo'])

def generate_title(user_prompt, ai_response):
    try:
        title_prompt = f"Gere um título muito curto (3 a 5 palavras) para a seguinte conversa:\n\nPERGUNTA: {user_prompt}\nRESPOSTA: {ai_response}\n\nTÍTULO:"
        headers = { "Authorization": f"Bearer {openrouter_api_key}", "Content-Type": "application/json" }
        json_data = {"model": "mistralai/mistral-7b-instruct", "messages": [{"role": "user", "content": title_prompt}], "max_tokens": 20}
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=json_data, timeout=5)
        response.raise_for_status()
        title = response.json()['choices'][0]['message']['content'].strip().strip('"')
        return title if title else "Chat sobre " + user_prompt[:20]
    except Exception:
        return "Chat sobre " + user_prompt[:20]