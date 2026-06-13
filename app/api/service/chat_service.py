import json
from collections.abc import Iterator

from fastapi import Depends

from app.api.repositories.chat_repository import ChatRepository
from app.schemas.chat import ChatResponse


class ChatService:
    def __init__(self, repo: ChatRepository = Depends()) -> None:
        self.repo = repo

    def answer(self, question: str) -> ChatResponse:
        try:
            result = self.repo.answer_query(question=question, top_k=3)
            return ChatResponse(
                answer=str(result.get("answer") or ""),
                source=result.get("sources") or [],
            )
        except Exception as exc:
            return ChatResponse(
                answer=f"Error processing request: {str(exc)}", source=[]
            )

    def stream_answer(self, question: str) -> Iterator[str]:
        try:
            for event in self.repo.stream_answer_query(question=question, top_k=3):
                yield format_sse(event)
        except Exception as exc:
            answer = f"Error processing request: {str(exc)}"
            yield format_sse(
                {
                    "type": "error",
                    "message": answer,
                }
            )
            yield format_sse(
                {
                    "type": "done",
                    "answer": answer,
                    "sources": [],
                    "route": "fallback",
                }
            )


def format_sse(event: dict) -> str:
    event_type = str(event.get("type") or "message")
    data = json.dumps(event, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {data}\n\n"
