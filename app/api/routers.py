from fastapi import APIRouter

from app.api.routes.chat_router import chat_router
from app.api.routes.document_router import document_router
from app.api.routes.job_router import job_router

router = APIRouter()

router.include_router(chat_router, prefix="/chat", tags=["chat"])
router.include_router(document_router, prefix="/documents", tags=["document"])
router.include_router(job_router, prefix="/jobs", tags=["job"])
