import json
from collections.abc import Iterator

from google import genai
from app.core.config import Config
from app.llm.prompt_builder import (
    build_expand_query_prompt,
    build_rag_prompt,
    build_route_query_prompt,
)


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

    def stream_generate_response(self, query: str, context: str) -> Iterator[str]:
        prompt = build_rag_prompt(query=query, context=context)

        if not hasattr(self.client.models, "generate_content_stream"):
            yield self.generate_response(query=query, context=context)
            return

        stream = self.client.models.generate_content_stream(
            model="gemma-4-31b-it",
            contents=prompt,
            config={
                "temperature": 0.5,
            },
        )

        for chunk in stream:
            text = getattr(chunk, "text", None)
            if text:
                yield text

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

    def generate_query_route(self, query: str) -> dict:
        prompt = build_route_query_prompt(query=query)

        response = self.client.models.generate_content(
            model="gemma-4-31b-it",
            contents=prompt,
            config={
                "temperature": 0.1,
                "response_mime_type": "application/json",
            },
        )

        text = response.text.strip()
        return self._parse_json_object(text)

    def _parse_json_object(self, text: str) -> dict:
        try:
            route = json.loads(text)
            return route if isinstance(route, dict) else {}
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return {}

            try:
                route = json.loads(text[start : end + 1])
                return route if isinstance(route, dict) else {}
            except Exception:
                return {}
