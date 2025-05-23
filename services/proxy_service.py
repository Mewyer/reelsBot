from flask import Flask, request, jsonify, Response
import openai
import requests
import os
from dotenv import load_dotenv
from functools import wraps
import logging

# Загрузка переменных окружения
load_dotenv()

app = Flask(__name__)

# Конфигурация
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
AUTH_TOKEN = os.getenv("PROXY_AUTH_TOKEN")
RATE_LIMIT = int(os.getenv("RATE_LIMIT", "100"))  # Запросов в минуту

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or auth_header != f"Bearer {AUTH_TOKEN}":
            logger.warning("Unauthorized access attempt")
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/proxy/gpt', methods=['POST'])
@auth_required
def proxy_gpt():
    try:
        data = request.json
        logger.info(f"GPT request: {data.get('model')}")
        
        response = openai.ChatCompletion.create(
            model=data.get('model', 'gpt-4'),
            messages=data['messages'],
            temperature=data.get('temperature', 0.7),
            max_tokens=data.get('max_tokens', 1000),
            api_key=OPENAI_API_KEY
        )
        
        return jsonify(response)
    except Exception as e:
        logger.error(f"GPT proxy error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/proxy/tts', methods=['POST'])
@auth_required
def proxy_tts():
    try:
        data = request.json
        logger.info(f"TTS request for voice: {data.get('voice_id')}")
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{data['voice_id']}"
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "text": data['text'],
            "voice_settings": {
                "stability": data.get('stability', 0.5),
                "similarity_boost": data.get('similarity_boost', 0.5)
            }
        }
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            return Response(
                response.content,
                mimetype='audio/mpeg',
                headers={
                    'Cache-Control': 'no-store',
                    'Content-Length': str(len(response.content))
                }
            )
        else:
            logger.error(f"TTS API error: {response.text}")
            return jsonify({"error": response.text}), response.status_code
    except Exception as e:
        logger.error(f"TTS proxy error: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        threaded=True
    )