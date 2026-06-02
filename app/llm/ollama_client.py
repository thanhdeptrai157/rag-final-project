import json

from ollama import Client

from app.core.config import Config
from app.llm.prompt_builder import build_expand_query_prompt, build_rag_prompt


class OllamaClient:
    def __init__(self):
        self.client = Client(host=Config.OLLAMA_HOST)
        self.model = Config.OLLAMA_MODEL

    def _chat(self, prompt: str, temperature: float = 0.3) -> str:
        response = self.client.chat(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            options={
                "temperature": temperature,
            },
            stream=False,
        )

        return response["message"]["content"]

    def generate_response(self, query: str, context: str) -> str:
        prompt = build_rag_prompt(query=query, context=context)
        return self._chat(prompt, temperature=0.3)

    def generate_expand_query(self, query: str) -> list[str]:
        prompt = build_expand_query_prompt(query=query)

        text = self._chat(prompt, temperature=0.1).strip()
        print("Expanded query response:", text)

        try:
            queries = json.loads(text)

            if not isinstance(queries, list):
                return [query]

            return [str(q) for q in queries if str(q).strip()]

        except Exception:
            return [query]
