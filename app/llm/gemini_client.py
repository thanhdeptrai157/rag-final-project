from google import genai
from app.core.config import Config
from app.llm.prompt_builder import build_rag_prompt


class GeminiClient:
    def __init__(self):
        self.client = genai.Client(api_key=Config.GEMINI_API_KEY)

    def generate_response(self, query: str, context: str) -> str:
        prompt = build_rag_prompt(query=query, context=context)
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={
                "temperature": 0.5,
            },
        )
        return response.text
