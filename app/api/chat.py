from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag_service import RagService

chat_router = APIRouter(tags=["chat"])
rag_service = RagService()


@chat_router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = rag_service.answer_query(query=request.question)
        return ChatResponse(answer=result["answer"], source=result["sources"])
    except Exception as e:
        return ChatResponse(answer=f"Error processing request: {str(e)}", source=[])
