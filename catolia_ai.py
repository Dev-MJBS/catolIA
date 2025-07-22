# catolia_ai.py

import os
import requests
from dotenv import load_dotenv

# Carrega as variáveis de ambiente (garante que a chave da API seja lida)
load_dotenv()
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

def get_ai_response(user_message: str, user_profile: str, response_type: str) -> str:
    """
    Função central para se comunicar com a API da IA.
    Recebe a mensagem, perfil e tipo de resposta, e retorna a resposta da IA.
    """
    if not openrouter_api_key:
        return "ERRO: A chave da API do OpenRouter não foi configurada no servidor."

    # --- Lógica de Construção do Prompt ---
    bible_citation_rule = "Ao citar passagens bíblicas, use sempre o formato 'Livro Capítulo, Versículo' (ex: 'Mateus 1,1')."
    
    length_instructions = {
        'curta': "Forneça uma resposta concisa, com até 3 frases.",
        'media': "Forneça uma resposta de comprimento médio, entre 4 e 8 frases.",
        'longa': "Forneça uma resposta detalhada e completa, com 9 ou mais frases."
    }
    
    profile_instructions = {
        'crianca': f"Você é uma IA católica. Responda de forma muito simples, didática e adequada para uma criança pequena. {bible_citation_rule}",
        'catequista': f"Você é uma IA católica para catequistas. Responda com foco em material para aulas, exemplos práticos e referências para ensinar. {bible_citation_rule}",
        'seminarista': f"Você é uma IA católica para seminaristas. Responda com profundidade teológica, referências a documentos da Igreja e filosofia. {bible_citation_rule}",
        'sacerdote': f"Você é uma IA católica para sacerdotes. Responda com alta profundidade teológica, foco em hermenêutica e homilética. {bible_citation_rule}",
        'leigo': f"Você é uma IA católica. Responda de forma clara, objetiva e completa para um leigo interessado em aprofundar sua fé. {bible_citation_rule}"
    }
    
    system_instructions = profile_instructions.get(user_profile, profile_instructions['leigo'])
    length_instruction = length_instructions.get(response_type, length_instructions['media'])
    system_prompt = f"{system_instructions} {length_instruction}"

    # --- Chamada para a API ---
    try:
        headers = {
            "Authorization": f"Bearer {openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://catolia.onrender.com",
            "X-Title": "CatolIA"
        }
        
        json_data = {
            "model": "deepseek/deepseek-chat", 
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        }

        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=json_data,
            timeout=45  # Adiciona um timeout de 45 segundos para evitar que a aplicação trave
        )
        response.raise_for_status() 
        
        response_data = response.json()
        reply = response_data['choices'][0]['message']['content']
        return reply
    
    except requests.exceptions.HTTPError as e:
        error_details_text = e.response.text
        print(f"ERRO HTTP ao chamar a API do OpenRouter: {error_details_text}")
        try:
            error_json = e.response.json()
            error_message = error_json.get('error', {}).get('message', error_details_text)
        except ValueError:
            error_message = error_details_text

        return f"Desculpe, a IA retornou um erro ({e.response.status_code}): \"{error_message}\". Verifique sua chave de API e os créditos no OpenRouter."
    
    except requests.exceptions.RequestException as e:
        print(f"ERRO de conexão ao chamar a API do OpenRouter: {e}")
        return "Desculpe, não foi possível conectar ao serviço de IA. Verifique sua conexão com a internet."

    except Exception as e:
        print(f"ERRO inesperado na função get_ai_response: {e}")
        return "Desculpe, a IA encontrou um problema inesperado ao processar sua solicitação. Por favor, tente novamente mais tarde."