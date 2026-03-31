from app.llm.gemini_client import GeminiClient
from app.retrieval.retriever import Retriever


class RagService:
    def __init__(self):
        self.retriever = Retriever()
        self.llm = GeminiClient()

    def answer_query(self, query: str, top_k: int = 5) -> dict:
        results = self.retriever.retrieve(query, top_k=top_k)
        contexts = []
        sources = []

        for item in results:
            text = item.get("text")
            if text:
                contexts.append(text)

            metadata = item.get("metadata") or {}
            source = (
                metadata.get("source")
                or metadata.get("file_path")
                or metadata.get("document_id")
            )
            sources.append(
                {
                    "title": item.get("title"),
                    "section_path": item.get("section_path"),
                    "source": source,
                }
            )

        context = "\n\n".join(contexts)
        answer = self.llm.generate_response(query=query, context=context)

        return {"answer": answer, "sources": sources}
