import json

from google import genai
from app.core.config import Config
from app.llm.prompt_builder import build_expand_query_prompt, build_rag_prompt


class GeminiClient:
    def __init__(self):
        self.client = genai.Client(api_key=Config.GEMINI_API_KEY)

    def generate_response(self, query: str, context: str) -> str:
        prompt = build_rag_prompt(query=query, context=context)
        response = self.client.models.generate_content(
            model="gemma-4-31b-it",
            contents=prompt,
            config={
                "temperature": 0.5,
            },
        )
        return response.text

    def generate_expand_query(self, query: str) -> list[str]:
        prompt = build_expand_query_prompt(query=query)

        response = self.client.models.generate_content(
            model="gemma-4-31b-it",
            contents=prompt,
            config={
                "temperature": 0.5,
                "response_mime_type": "application/json",
            },
        )

        text = response.text.strip()
        print("Expanded query response:", text)
        try:
            queries = json.loads(text)

            if not isinstance(queries, list):
                return [query]

            return [str(q) for q in queries]

        except Exception:
            return [query]
