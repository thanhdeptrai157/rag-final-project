from fastapi import APIRouter
from .chat import chat_router

router = APIRouter(tags=["chat"])

router.include_router(chat_router, prefix="/chat", tags=["chat"])
