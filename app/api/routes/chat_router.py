from fastapi import APIRouter, Depends

from app.schemas.chat import ChatRequest, ChatResponse
from app.api.service.chat_service import ChatService

chat_router = APIRouter(tags=["chat"])


@chat_router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: ChatService = Depends(),
) -> ChatResponse:
    return service.answer(request.question)

