from fastapi import Depends

from app.api.repositories.chat_repository import ChatRepository
from app.schemas.chat import ChatResponse


class ChatService:
    def __init__(self, repo: ChatRepository = Depends()) -> None:
        self.repo = repo

    def answer(self, question: str) -> ChatResponse:
        try:
            result = self.repo.answer_query(question=question, top_k=3)
            return ChatResponse(answer=result["answer"], source=result["sources"])
        except Exception as exc:
            return ChatResponse(
                answer=f"Error processing request: {str(exc)}", source=[]
            )
