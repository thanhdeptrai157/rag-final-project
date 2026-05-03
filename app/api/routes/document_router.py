from fastapi import APIRouter, Depends, File, UploadFile, status

from app.schemas.document import DocumentUploadResponse
from app.api.service.document_service import DocumentService

document_router = APIRouter()


@document_router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile = File(...),
    service: DocumentService = Depends(),
) -> DocumentUploadResponse:
    return await service.create_document(file)

