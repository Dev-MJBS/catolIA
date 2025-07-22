# /api/index.py

import os
import requests 
import json
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from dotenv import load_dotenv

# --- CONFIGURAÇÃO INICIAL ---
load_dotenv()

# O Vercel precisa que a pasta de templates seja especificada a partir da raiz do projeto
# ../templates significa "volte uma pasta e entre em templates"
app = Flask(__name__, template_folder='../templates')

# O Vercel usa um sistema de arquivos temporário, então o BD será criado lá
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/catolia.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

# --- MODELOS DO BANCO DE DADOS ---
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

# Cria as tabelas antes da primeira requisição
with app.app_context():
    db.create_all()

# --- ROTAS DA APLICAÇÃO ---
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    # Esta rota serve o index.html para qualquer caminho que não seja uma API
    return render_template("index.html")

# --- ROTAS DA API PARA O HISTÓRICO ---
@app.route('/api/history', methods=['GET'])
def get_history():
    conversations = Conversation.query.order_by(Conversation.created_at.desc()).all()
    history = [{"id": conv.id, "title": conv.title} for conv in conversations]
    return jsonify(history)

# ... (O resto do seu código de rotas continua exatamente o mesmo)
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

@app.route('/api/chat', methods=['POST'])
def chat():
    # ... (Esta função continua exatamente a mesma)
    if not openrouter_api_key:
        return Response(json.dumps({"error": "API Key not configured"}), status=500, mimetype='application/json')
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')
        user_profile = data.get('profile', 'leigo')

        if user_profile == 'catequista':
            age_group = data.get('age_group', 'Não especificado')
            user_message = f"Tema da Catequese: {user_message}\nFaixa Etária: {age_group}"

        if not user_message:
            return Response("Mensagem vazia.", status=400)

        if conversation_id:
            conv = Conversation.query.get(conversation_id)
        else:
            conv = Conversation()
            db.session.add(conv)
            db.session.commit()
        
        user_msg_db = Message(conversation_id=conv.id, sender='user', content=data.get('message', ''))
        db.session.add(user_msg_db)
        db.session.commit()

        def generate_response():
            full_ai_response = ""
            try:
                yield f"event: conversation_id\ndata: {conv.id}\n\n"
                system_prompt = get_system_prompt(user_profile)
                headers = { "Authorization": f"Bearer {openrouter_api_key}", "Content-Type": "application/json" }
                json_data = {
                    "model": "deepseek/deepseek-chat",
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
                    "stream": True
                }
                
                with requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=json_data, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    for chunk in r.iter_lines():
                        if chunk.startswith(b'data: '):
                            chunk_data = chunk.decode('utf-8')[6:]
                            if chunk_data.strip() == '[DONE]':
                                break
                            try:
                                json_chunk = json.loads(chunk_data)
                                content = json_chunk['choices'][0]['delta'].get('content', '')
                                if content:
                                    full_ai_response += content
                                    yield f"data: {json.dumps({'content': content})}\n\n"
                            except (json.JSONDecodeError, KeyError):
                                continue

                ai_msg_db = Message(conversation_id=conv.id, sender='ai', content=full_ai_response)
                if conv.title == "Novo Chat":
                    conv.title = generate_title(data.get('message', ''), full_ai_response)
                db.session.add(ai_msg_db)
                db.session.commit()

            except requests.exceptions.HTTPError as e:
                yield f"event: error\ndata: Erro na API: {e.response.status_code}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {str(e)}\n\n"

        return Response(stream_with_context(generate_response()), mimetype='text/event-stream')
    except Exception as e:
        return Response(json.dumps({"error": "Internal Server Error"}), status=500, mimetype='application/json')

def get_system_prompt(profile):
    # ... (Esta função continua a mesma)
    bible_citation_rule = "Ao citar passagens bíblicas, use sempre o formato 'Livro Capítulo, Versículo' (ex: 'Mateus 1,1')."
    instructions = {
        'crianca': f"Você é uma IA católica. Responda de forma muito simples, didática e adequada para uma criança pequena. {bible_citation_rule}",
        'catequista': f"Você é uma IA católica para catequistas. Crie um plano de encontro de catequese detalhado e estruturado. Use Markdown para formatar a resposta com títulos, negrito e listas.",
        'seminarista': f"Você é uma IA católica para seminaristas. Responda com profundidade teológica, referências a documentos da Igreja e filosofia. {bible_citation_rule}",
        'sacerdote': f"Você é uma IA católica para sacerdotes. Responda com alta profundidade teológica, foco em hermenêutica e homilética. {bible_citation_rule}",
        'leigo': f"Você é uma IA católica. Responda de forma clara, objetiva e completa para um leigo interessado em aprofundar sua fé. {bible_citation_rule}"
    }
    return instructions.get(profile, instructions['leigo'])

def generate_title(user_prompt, ai_response):
    # ... (Esta função continua a mesma)
    try:
        title_prompt = f"Gere um título muito curto (3 a 5 palavras) para a seguinte conversa:\n\nPERGUNTA: {user_prompt}\nRESPOSTA: {ai_response}\n\nTÍTULO:"
        headers = { "Authorization": f"Bearer {openrouter_api_key}", "Content-Type": "application/json" }
        json_data = {"model": "deepseek/deepseek-chat", "messages": [{"role": "user", "content": title_prompt}], "max_tokens": 20}
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=json_data)
        response.raise_for_status()
        title = response.json()['choices'][0]['message']['content'].strip().strip('"')
        return title if title else "Chat sobre " + user_prompt[:20]
    except Exception:
        return "Chat sobre " + user_prompt[:20]