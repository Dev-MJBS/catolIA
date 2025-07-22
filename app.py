# app.py (Catolia 2.0 Backend - Versão com Diagnóstico Aprimorado)

import os
import requests 
import json
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from dotenv import load_dotenv

print("LOG: INICIANDO O ARQUIVO app.py")

# --- CONFIGURAÇÃO INICIAL ---
load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')
print("LOG: Flask App Instanciado")

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///catolia.db'
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
    sender = db.Column(db.String(10), nullable=False) # 'user' ou 'ai'
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --- ROTAS DA APLICAÇÃO ---
@app.route('/')
def index():
    print("LOG: Rota '/' foi acessada.")
    return render_template('index.html')

# --- ROTAS DA API PARA O HISTÓRICO ---
@app.route('/api/history', methods=['GET'])
def get_history():
    print("LOG: Rota '/api/history' foi acessada.")
    conversations = Conversation.query.order_by(Conversation.created_at.desc()).all()
    history = [{"id": conv.id, "title": conv.title} for conv in conversations]
    return jsonify(history)

@app.route('/api/conversation/<int:conv_id>', methods=['GET'])
def get_conversation(conv_id):
    print(f"LOG: Rota '/api/conversation/{conv_id}' foi acessada.")
    conversation = Conversation.query.get_or_404(conv_id)
    messages = [{"sender": msg.sender, "content": msg.content} for msg in conversation.messages]
    return jsonify({"title": conversation.title, "messages": messages})

@app.route('/api/conversation', methods=['DELETE'])
def delete_all_history():
    print("LOG: Rota 'DELETE /api/conversation' foi acessada.")
    try:
        db.session.query(Message).delete()
        db.session.query(Conversation).delete()
        db.session.commit()
        return jsonify({"success": "Histórico apagado com sucesso."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# --- ROTA PRINCIPAL DO CHAT (COM STREAMING) ---
@app.route('/api/chat', methods=['POST'])
def chat():
    print("LOG: ROTA '/api/chat' FOI ACESSADA COM SUCESSO!")
    if not openrouter_api_key:
        print("LOG: ERRO - Chave da API do OpenRouter não encontrada.")
        return Response(json.dumps({"error": "API Key not configured"}), status=500, mimetype='application/json')
    # ... (o resto da função continua igual)
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')
        user_profile = data.get('profile', 'leigo')
        print(f"LOG: Recebida nova mensagem. Conv ID: {conversation_id}, Perfil: {user_profile}")

        if user_profile == 'catequista':
            age_group = data.get('age_group', 'Não especificado')
            user_message = f"Tema da Catequese: {user_message}\nFaixa Etária: {age_group}"
            print(f"LOG: Perfil Catequista detectado. Prompt ajustado.")

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
        print(f"LOG: Mensagem do usuário salva no BD. Conv ID: {conv.id}")

        def generate_response():
            full_ai_response = ""
            try:
                yield f"event: conversation_id\ndata: {conv.id}\n\n"
                print(f"LOG: Enviando conversation_id {conv.id} para o cliente.")

                system_prompt = get_system_prompt(user_profile)
                
                headers = { "Authorization": f"Bearer {openrouter_api_key}", "Content-Type": "application/json" }
                json_data = {
                    "model": "deepseek/deepseek-chat",
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
                    "stream": True
                }
                
                print("LOG: Iniciando chamada de streaming para a API do OpenRouter...")
                with requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=json_data, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    print("LOG: Conexão de streaming com a API estabelecida.")
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
                print("LOG: Streaming da API finalizado.")

                ai_msg_db = Message(conversation_id=conv.id, sender='ai', content=full_ai_response)
                if conv.title == "Novo Chat":
                    conv.title = generate_title(data.get('message', ''), full_ai_response)
                db.session.add(ai_msg_db)
                db.session.commit()
                print(f"LOG: Resposta completa da IA salva no BD.")

            except requests.exceptions.HTTPError as e:
                print(f"LOG: ERRO HTTP da API: {e.response.text}")
                yield f"event: error\ndata: Erro na API: {e.response.status_code}\n\n"
            except Exception as e:
                print(f"LOG: ERRO GERAL no streaming: {e}")
                yield f"event: error\ndata: {str(e)}\n\n"

        return Response(stream_with_context(generate_response()), mimetype='text/event-stream')

    except Exception as e:
        print(f"LOG: ERRO GERAL na rota /api/chat: {e}")
        return Response(json.dumps({"error": "Internal Server Error"}), status=500, mimetype='application/json')

def get_system_prompt(profile):
    bible_citation_rule = "Ao citar passagens bíblicas, use sempre o formato 'Livro Capítulo, Versículo' (ex: 'Mateus 1,1')."
    instructions = {
        'crianca': f"Você é uma IA católica. Responda de forma muito simples, didática e adequada para uma criança pequena. {bible_citation_rule}",
        'catequista': f"Você é uma IA católica para catequistas. Crie um plano de encontro de catequese detalhado e estruturado. Use Markdown para formatar a resposta com títulos, negrito e listas.",
        'seminarista': f"Você é uma IA católica para seminaristas. Responda com profundidade teológica, referências a documentos da Igreja e filosofia. {bible_citation_rule}",
        'sacerdote': f"Você é uma IA católica para sacerdotes. Responda com alta profundidade teológica, foco em hermêutica e homilética. {bible_citation_rule}",
        'leigo': f"Você é uma IA católica. Responda de forma clara, objetiva e completa para um leigo interessado em aprofundar sua fé. {bible_citation_rule}"
    }
    return instructions.get(profile, instructions['leigo'])

def generate_title(user_prompt, ai_response):
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

print("LOG: FIM DO ARQUIVO app.py, DEFININDO CONTEXTO DA APP")
with app.app_context():
    db.create_all()
    print("LOG: Banco de dados verificado/criado.")

if __name__ == '__main__':
    print("LOG: Iniciando app em modo de desenvolvimento (__main__)")
    app.run(debug=True, threaded=True)