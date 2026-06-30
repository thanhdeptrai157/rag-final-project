from fastapi import Depends

from app.services.rag_service import RagService


class ChatRepository:
    def __init__(self, rag_service: RagService = Depends()) -> None:
        self.rag_service = rag_service

    def answer_query(
        self,
        question: str,
        top_k: int = 1,
        chat_history: list[dict] | None = None,
    ) -> dict:
        return self.rag_service.answer_query(
            query=question,
            top_k=top_k,
            chat_history=chat_history,
        )

    def stream_answer_query(
        self,
        question: str,
        top_k: int = 1,
        chat_history: list[dict] | None = None,
    ):
        yield from self.rag_service.stream_answer_query(
            query=question,
            top_k=top_k,
            chat_history=chat_history,
        )
