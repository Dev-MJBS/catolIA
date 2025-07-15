import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv() 

gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    print("Erro: A variável de ambiente GEMINI_API_KEY não está configurada.")
    exit()

genai.configure(api_key=gemini_api_key)

print("Listando modelos disponíveis para a sua API Key:")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"Nome: {m.name}, Métodos Suportados: {m.supported_generation_methods}")
except Exception as e:
    print(f"Erro ao listar modelos: {e}")