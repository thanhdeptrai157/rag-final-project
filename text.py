from google import genai
from app.core.config import Config

client = genai.Client(api_key=Config.GEMINI_API_KEY)

for m in client.models.list():
    print(m.name)
    print(m.supported_actions)
