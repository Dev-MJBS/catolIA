import os
from flask import Flask, request, jsonify, render_template, Response, stream_with_context, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from dotenv import load_dotenv
import requests
import json

load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "catolia-secret")
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+pymysql://{os.getenv('MYSQL_USER')}:{os.getenv('MYSQL_PASSWORD')}"
    f"@{os.getenv('MYSQL_HOST','localhost')}/{os.getenv('MYSQL_DB')}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(100))
    conversations = db.relationship('Conversation', backref='user', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False, default="Novo Chat")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    messages = db.relationship('Message', backref='conversation', lazy=True, cascade="all, delete-orphan")

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    sender = db.Column(db.String(10), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        name = request.form['name'].strip()
        if User.query.filter_by(email=email).first():
            return render_template('register.html', error='Email já cadastrado!')
        user = User(email=email, name=name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        return render_template('login.html', error='Email ou senha inválidos!')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/')
def index():
    return render_template('index.html', user=current_user if getattr(current_user, "is_authenticated", False) else None)

@app.route('/api/history', methods=['GET'])
@login_required
def get_history():
    conversations = Conversation.query.filter_by(user_id=current_user.id).order_by(Conversation.created_at.desc()).all()
    history = [{"id": conv.id, "title": conv.title} for conv in conversations]
    return jsonify(history)

@app.route('/api/conversation/<int:conv_id>', methods=['GET'])
@login_required
def get_conversation(conv_id):
    conversation = Conversation.query.filter_by(id=conv_id, user_id=current_user.id).first_or_404()
    messages = [{"sender": msg.sender, "content": msg.content} for msg in conversation.messages]
    return jsonify({"title": conversation.title, "messages": messages})

@app.route('/api/conversation', methods=['DELETE'])
@login_required
def delete_all_history():
    try:
        conversations = Conversation.query.filter_by(user_id=current_user.id).all()
        for conv in conversations:
            Message.query.filter_by(conversation_id=conv.id).delete()
        Conversation.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        return jsonify({"success": "Histórico apagado com sucesso."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    if not openrouter_api_key:
        return Response(json.dumps({"error": "API Key não configurada"}), status=500, mimetype='application/json')
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')
        user_profile = data.get('profile', 'leigo')
        age_group = data.get('age_group', '')
        if not user_message:
            return Response(json.dumps({"error": "Mensagem vazia."}), status=400, mimetype='application/json')
        uid = current_user.id if getattr(current_user, "is_authenticated", False) else None
        conv = None
        if conversation_id:
            conv = Conversation.query.filter_by(id=conversation_id).first()
        if not conv:
            conv = Conversation(user_id=uid)
            db.session.add(conv)
            db.session.commit()
        user_msg_db = Message(conversation_id=conv.id, sender='user', content=user_message)
        db.session.add(user_msg_db)
        db.session.commit()
        def generate_response():
            full_ai_response = ""
            try:
                yield f"event: conversation_id\ndata: {conv.id}\n\n"
                system_prompt = get_system_prompt(user_profile)
                if user_profile == 'catequista':
                    user_message_final = f"Tema da Catequese: {user_message}\nFaixa Etária: {age_group}"
                else:
                    user_message_final = user_message
                headers = {"Authorization": f"Bearer {openrouter_api_key}", "Content-Type": "application/json"}
                json_data = {
                    "model": "deepseek/deepseek-chat",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message_final}
                    ],
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
                db.session.add(ai_msg_db)
                if conv.title == "Novo Chat":
                    conv.title = generate_title(user_message, full_ai_response)
                db.session.commit()
            except requests.exceptions.HTTPError as e:
                yield f"event: error\ndata: Erro na API: {e.response.status_code}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {str(e)}\n\n"
        return Response(stream_with_context(generate_response()), mimetype='text/event-stream')
    except Exception as e:
        print("Erro interno em /api/chat:", e)
        return Response(json.dumps({"error": "Erro interno do servidor"}), status=500, mimetype='application/json')

def get_system_prompt(profile):
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
    try:
        title_prompt = f"Gere um título muito curto (3 a 5 palavras) para a seguinte conversa:\n\nPERGUNTA: {user_prompt}\nRESPOSTA: {ai_response}\n\nTÍTULO:"
        headers = {"Authorization": f"Bearer {openrouter_api_key}", "Content-Type": "application/json"}
        json_data = {
            "model": "deepseek/deepseek-chat",
            "messages": [{"role": "user", "content": title_prompt}],
            "max_tokens": 20
        }
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=json_data)
        response.raise_for_status()
        title = response.json()['choices'][0]['message']['content'].strip().strip('"')
        return title if title else "Chat sobre " + user_prompt[:20]
    except Exception:
        return "Chat sobre " + user_prompt[:20]

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, threaded=True, port=5002)