import os
import google.generativeai as genai
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from datetime import datetime
# REMOVIDO: import locale

# REMOVIDO: Bloco try-except para locale.setlocale
# try:
#     locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
# except locale.Error:
#     locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')

load_dotenv()

app = Flask(__name__)

gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    raise ValueError("A variável de ambiente GEMINI_API_KEY não está configurada.")
genai.configure(api_key=gemini_api_key)

model = genai.GenerativeModel('models/gemini-1.5-flash-latest')

def get_liturgia_cnbb_redirecionamento():
    today = datetime.now()
    
    # Formatação manual da data para português (agora mais crucial)
    meses_pt = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto", 
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    dia = today.day
    mes = meses_pt[today.month]
    ano = today.year
    today_formatted_extenso = f"{dia} de {mes} de {ano}"
    
    reply_message = (
        f"Olá! Entendo que você deseja a Liturgia Diária para hoje, {today_formatted_extenso}.\n\n"
        f"Infelizmente, como uma inteligência artificial, não tenho acesso direto e em tempo real a conteúdos que mudam diariamente em sites externos, como as leituras completas da Liturgia.\n\n"
        f"Para ter acesso à Liturgia Diária completa e atualizada, sugiro que você acesse diretamente o site da **CNBB (Conferência Nacional dos Bispos do Brasil)**, que é a fonte oficial para o Brasil:\n"
        f"**[Acessar Liturgia Diária da CNBB](https://www.cnbb.org.br/liturgia-diaria/)**\n\n"
        f"Você também pode considerar usar um missal impresso, um aplicativo de liturgia católica (como o 'Missal Católico' ou 'Eu Quero Rezar'), ou consultar sua paróquia local.\n\n"
        f"Lembre-se que a nossa fé se baseia em Jesus Cristo, nosso Salvador. Mesmo sem as leituras específicas do dia, podemos sempre encontrar inspiração em passagens como João 3,16: \"Porque Deus amou tanto o mundo que deu o seu Filho unigénito, para que todo aquele nele crer não pereça, mas tenha a vida eterna.\"\n\n"
        f"Que Deus te abençoe em sua jornada de fé!"
    )
    return reply_message

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        user_message = data.get('message')
        user_profile = data.get('profile', 'leigo')
        response_type = data.get('response_type', 'media')

        if not user_message:
            return jsonify({'error': 'Nenhuma mensagem fornecida'}), 400

        system_instructions = ""
        bible_citation_rule = "Ao citar passagens bíblicas, use sempre o formato 'Livro Capítulo, Versículo' (por exemplo, 'Mateus 1,1' e não 'Mateus 1:1')."

        length_instruction = ""
        if response_type == 'curta':
            length_instruction = "Forneça uma resposta concisa, com até 3 frases."
        elif response_type == 'media':
            length_instruction = "Forneça uma resposta de comprimento médio, entre 4 e 8 frases."
        elif response_type == 'longa':
            length_instruction = "Forneça uma resposta detalhada e completa, com 9 ou mais frases, explorando o tema em profundidade."
        
        if "liturgia" in user_message.lower() or "leituras do dia" in user_message.lower() or "evangelho de hoje" in user_message.lower() or "liturgia diaria" in user_message.lower():
            gemini_reply = get_liturgia_cnbb_redirecionamento()
            
        else:
            if user_profile == 'crianca':
                system_instructions = f"Você é uma IA de guia de fé católica. Responda a perguntas sobre o catolicismo, catecismo, santos e liturgia, de forma muito simples, didática e adequada para uma criança pequena. Use linguagem acessível e exemplos claros. {bible_citation_rule}"
            elif user_profile == 'catequista':
                system_instructions = f"Você é uma IA de guia de fé católica para catequistas. Responda a perguntas sobre o catolicismo, catecismo, santos e liturgia, com foco em material para aulas, exemplos práticos e referências que um catequista precisaria para ensinar. {bible_citation_rule}"
            elif user_profile == 'seminarista':
                system_instructions = f"Você é uma IA de guia de fé católica para seminaristas. Responda a perguntas sobre o catolicismo, catecismo, santos e liturgia, com profundidade teológica, referências a documentos da Igreja, Padres da Igreja e filosofia, adequada para estudos seminarísticos. {bible_citation_rule}"
            elif user_profile == 'sacerdote':
                system_instructions = f"Você é uma IA de guia de fé católica para sacerdotes. Responda a perguntas sobre o catolicismo, catecismo, santos e liturgia, com alta profundidade teológica, foco em hermenêutica, homilética e discussões complexas, útil para um sacerdote ou teólogo. {bible_citation_rule}"
            else:
                system_instructions = f"Você é uma IA de guia de fé católica. Responda a perguntas sobre o catolicismo, catecismo, santos e liturgia, de forma clara, objetiva e completa para um leigo interessado em aprofundar sua fé. {bible_citation_rule}"

            full_prompt = (
                f"{system_instructions} {length_instruction}\n\n**Contexto:** Você é uma IA de guia de fé católica, "
                f"especializada em catecismo, história e vida dos santos, liturgia diária, "
                f"reflexões sobre a ICAR, e respostas religiosas/teológicas. Seu objetivo é "
                f"ajudar católicos a estudar e aprofundar sua fé.\n\n**Pergunta:** {user_message}"
            )
            
            try:
                response = model.generate_content(full_prompt, timeout=120)
                if hasattr(response, 'text'):
                    gemini_reply = response.text
                else:
                    print(f"Gemini response did not contain text. Raw response: {response}")
                    gemini_reply = "Desculpe, a IA não conseguiu gerar uma resposta de texto para sua pergunta. Pode ser um filtro de conteúdo ou um problema interno."
            except genai.types.BlockedPromptException as e:
                print(f"Prompt bloqueado pelo filtro de segurança do Gemini: {e}")
                gemini_reply = "Desculpe, sua pergunta foi bloqueada pelo filtro de segurança da IA. Por favor, reformule."
            except Exception as e:
                print(f"Erro ao chamar a API do Gemini: {e}")
                gemini_reply = "Desculpe, a IA encontrou um problema ao processar sua solicitação. Por favor, tente novamente mais tarde ou reformule a pergunta."

        if "cnbb.org.br" not in gemini_reply.lower():
            gemini_reply += '<br><br><span style="font-size: 0.75em; color: #888;">IA Católica - Seu Guia de Fé</span>'
        else:
             gemini_reply += '<br><br><span style="font-size: 0.75em; color: #888;">Liturgia Diária via CNBB (Conferência Nacional dos Bispos do Brasil)</span>'

        return jsonify({'reply': gemini_reply})

    except Exception as e:
        print(f"Erro no backend (fora da chamada Gemini): {e}")
        return jsonify({'error': 'Ocorreu um erro interno inesperado. Por favor, tente novamente mais tarde.'}), 500

if __name__ == '__main__':
    app.run(debug=False)