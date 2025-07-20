import os
import time
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from datetime import datetime
import requests

# Carrega as variáveis de ambiente do ficheiro .env
load_dotenv()

# Inicializa a aplicação Flask
app = Flask(__name__)

# --- Configuração da API OpenRouter ---
# A chave da API será lida da variável de ambiente OPENROUTER_API_KEY
# É crucial que esta variável esteja definida no seu ficheiro .env ou no ambiente do servidor.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") 
OPENROUTER_API_URL = 'https://openrouter.ai/api/v1/chat/completions'
# Nome do modelo DeepSeek a ser usado através do OpenRouter
# Verifique a documentação do OpenRouter para nomes de modelos exatos, por exemplo: "deepseek/deepseek-chat", "deepseek/deepseek-coder"
OPENROUTER_MODEL_NAME = "deepseek/deepseek-chat" 

# --- Verificação da chave da API ---
# Esta verificação é essencial para garantir que a chave foi carregada corretamente.
if not OPENROUTER_API_KEY:
    raise ValueError("A variável de ambiente OPENROUTER_API_KEY não está configurada. Por favor, defina-a no seu ficheiro .env ou no ambiente do servidor.")

# --- Configuração da Cache ---
# A cache será um dicionário para guardar respostas recentes.
# A chave será a pergunta e o valor será a resposta e o carimbo de data/hora em que foi guardada.
api_cache = {}
CACHE_DURATION_SECONDS = 600  # Guarda as respostas por 10 minutos (600 segundos)

# --- Funções Auxiliares ---

def get_liturgia_cnbb_redirecionamento():
    """Gera uma resposta padrão para perguntas sobre a liturgia, direcionando para a CNBB."""
    today = datetime.now()
    meses_pt = {1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"}
    today_formatted_extenso = f"{today.day} de {meses_pt[today.month]} de {today.year}"
    
    reply_message = (
        f"Olá! Compreendo que deseja a Liturgia Diária para hoje, {today_formatted_extenso}.\n\n"
        "Como uma inteligência artificial, não tenho acesso direto e em tempo real a conteúdos que mudam diariamente em sites externos.\n\n"
        "Para ter acesso à Liturgia Diária completa e atualizada, sugiro que aceda diretamente ao site da **CNBB (Conferência Nacional dos Bispos do Brasil)**, que é a fonte oficial:\n"
        "**[Aceder Liturgia Diária da CNBB](https://www.cnbb.org.br/liturgia-diaria/)**\n\n"
        "Que Deus o abençoe!"
    )
    return reply_message

# --- Rotas da Aplicação ---

@app.route('/')
def index():
    """Serve a página principal da aplicação."""
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    """Evita erros 404 no registo para o ícone do separador."""
    return '', 204

@app.route('/chat', methods=['POST'])
def chat():
    """Processa as mensagens do utilizador e retorna a resposta da IA."""
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        if not user_message:
            return jsonify({'error': 'Nenhuma mensagem fornecida'}), 400

        user_profile = data.get('profile', 'leigo')
        response_type = data.get('response_type', 'media')

        # Lógica de verificação da Cache
        # Cria uma chave única para a pergunta baseada no conteúdo, perfil e tipo de resposta.
        cache_key = f"{user_message}|{user_profile}|{response_type}"
        
        # Verifica se a resposta está na cache e se ainda é válida (não expirou).
        if cache_key in api_cache:
            cached_response, timestamp = api_cache[cache_key]
            if time.time() - timestamp < CACHE_DURATION_SECONDS:
                print(f"INFO: A devolver resposta da cache para a chave: {cache_key}")
                # Adiciona a assinatura e devolve a resposta da cache.
                cached_response_with_signature = cached_response + '<br><br><span style="font-size: 0.75em; color: #888;">CatólIA - Seu Guia de Fé (Cache)</span>'
                return jsonify({'reply': cached_response_with_signature})

        liturgia_keywords = ["liturgia", "leituras do dia", "evangelho de hoje", "liturgia diaria"]
        if any(keyword in user_message.lower() for keyword in liturgia_keywords):
            gemini_reply = get_liturgia_cnbb_redirecionamento()
        else:
            # Se não estiver na cache, continua para fazer a chamada à API
            print(f"INFO: Cache miss. A chamar a API do OpenRouter para a chave: {cache_key}")
            bible_citation_rule = "Ao citar passagens bíblicas, use sempre o formato 'Livro Capítulo, Versículo' (por exemplo, 'Mateus 1,1')."
            length_instructions = {
                'curta': "Forneça uma resposta concisa, com até 3 frases.",
                'media': "Forneça uma resposta de comprimento médio, entre 4 e 8 frases.",
                'longa': "Forneça uma resposta detalhada e completa, com 9 ou mais frases."
            }
            profile_instructions = {
                'crianca': f"É uma IA católica. Responda de forma muito simples, didática e adequada para uma criança pequena. Use linguagem acessível e exemplos claros. {bible_citation_rule}",
                'catequista': f"É uma IA católica para catequistas. Responda com foco em material para aulas, exemplos práticos e referências para ensinar. {bible_citation_rule}",
                'seminarista': f"É uma IA católica para seminaristas. Responda com profundidade teológica, referências a documentos da Igreja e filosofia, adequada para estudos seminarísticos. {bible_citation_rule}",
                'sacerdote': f"É uma IA católica para sacerdotes. Responda com alta profundidade teológica, foco em hermenêutica e homilética. {bible_citation_rule}",
                'leigo': f"É uma IA católica. Responda de forma clara, objetiva e completa para um leigo interessado em aprofundar a sua fé. {bible_citation_rule}"
            }
            
            system_instructions = profile_instructions.get(user_profile, profile_instructions['leigo'])
            length_instruction = length_instructions.get(response_type, length_instructions['media'])

            # Construção do payload de mensagens para o modelo de linguagem
            # O OpenRouter espera uma lista de mensagens com roles
            messages_payload = [
                {"role": "system", "content": f"É uma IA de guia de fé católica. {system_instructions} {length_instruction}"},
                {"role": "user", "content": user_message}
            ]
            
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": OPENROUTER_MODEL_NAME,
                "messages": messages_payload,
                "temperature": 0.7, # Pode ajustar a temperatura para criatividade (0.0 a 1.0)
                "max_tokens": 1000 # Limite de tokens na resposta
            }
            
            try:
                # Aumenta o timeout para 180 segundos (3 minutos)
                response_llm = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=180)
                response_llm.raise_for_status() # Lança exceção para status de erro HTTP (4xx ou 5xx)

                llm_data = response_llm.json()
                
                # Acede o conteúdo da resposta do modelo
                if llm_data and llm_data.get('choices') and llm_data['choices'][0].get('message'):
                    gemini_reply = llm_data['choices'][0]['message']['content']
                else:
                    print(f"ERRO: A resposta da IA (OpenRouter) não contém o conteúdo esperado. Dados brutos: {llm_data}")
                    gemini_reply = "Desculpe, a IA (OpenRouter) não conseguiu gerar uma resposta. A estrutura da resposta foi inesperada."
                
                # Salva a nova resposta na cache
                api_cache[cache_key] = (gemini_reply, time.time())
            
            except requests.exceptions.Timeout:
                print("ERRO: A requisição para a IA (OpenRouter) excedeu o tempo limite. (Timeout)")
                gemini_reply = "Desculpe, a IA demorou muito para responder. Por favor, tente novamente ou reformule a sua pergunta para ser mais concisa."
            except requests.exceptions.HTTPError as e:
                print(f"ERRO: Erro HTTP ao chamar a IA (OpenRouter): {e.response.status_code} - {e.response.text}")
                if e.response.status_code == 429:
                    gemini_reply = "Desculpe, o limite de requisições para a IA foi atingido. Por favor, aguarde um momento antes de tentar novamente."
                elif e.response.status_code == 401:
                    gemini_reply = "Erro de autenticação com a IA. Por favor, verifique a chave da API no servidor."
                elif e.response.status_code >= 400 and e.response.status_code < 500:
                    gemini_reply = f"Desculpe, a sua pergunta não pôde ser processada pela IA (erro do cliente: {e.response.status_code}). Por favor, reformule."
                else:
                    gemini_reply = f"Desculpe, a IA encontrou um problema no servidor (erro {e.response.status_code}). Por favor, tente novamente mais tarde."
            except requests.exceptions.RequestException as e:
                print(f"ERRO: Erro de rede ao chamar a IA (OpenRouter): {e}")
                gemini_reply = f"Desculpe, a CatólIA não conseguiu comunicar com a IA. Erro de rede: {e}. Por favor, verifique a sua ligação ou tente novamente mais tarde."
            except Exception as e:
                print(f"ERRO GERAL ao processar resposta da IA (OpenRouter): {e}")
                gemini_reply = f"Ocorreu um erro interno inesperado ao gerar a resposta da IA. Detalhes: {e}. Por favor, tente novamente mais tarde ou reformule a pergunta."

        # A lógica de créditos permanece a mesma
        if "cnbb.org.br" not in gemini_reply.lower():
            gemini_reply += '<br><br><span style="font-size: 0.75em; color: #888;">CatólIA - Seu Guia de Fé</span>'
        else:
             gemini_reply += '<br><br><span style="font-size: 0.75em; color: #888;">Liturgia Diária via CNBB (Conferência Nacional dos Bispos do Brasil)</span>'

        return jsonify({'reply': gemini_reply})

    except Exception as e:
        print(f"ERRO GERAL no endpoint /chat (fora da chamada principal): {e}")
        return jsonify({'error': 'Ocorreu um erro interno inesperado no servidor.'}), 500

if __name__ == '__main__':
    app.run(debug=False)
