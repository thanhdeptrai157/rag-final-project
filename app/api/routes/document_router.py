from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_current_admin_user
from app.schemas.common import PageResponse
from app.schemas.document import (
    DocumentDeleteResponse,
    DocumentDetailResponse,
    DocumentListItem,
    DocumentUpdateRequest,
    DocumentUploadResponse,
    DocumentVersionUploadResponse,
    DocumentVersionDeleteResponse,
    DocumentVersionDetailResponse,
    DocumentVersionListItem,
    DocumentVersionUpdateRequest,
)
from app.api.service.document_service import DocumentService

document_router = APIRouter(dependencies=[Depends(get_current_admin_user)])


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


@document_router.post(
    "/{document_id}/versions/upload",
    response_model=DocumentVersionUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document_version(
    document_id: UUID,
    file: UploadFile = File(...),
    service: DocumentService = Depends(),
) -> DocumentVersionUploadResponse:
    return await service.upload_document_version(document_id, file)


@document_router.get("", response_model=PageResponse[DocumentListItem])
def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    service: DocumentService = Depends(),
) -> PageResponse[DocumentListItem]:
    return service.list_documents(page=page, page_size=page_size)


@document_router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(
    document_id: UUID,
    service: DocumentService = Depends(),
) -> DocumentDetailResponse:
    return service.get_document(document_id)


@document_router.patch("/{document_id}", response_model=DocumentDetailResponse)
def update_document(
    document_id: UUID,
    payload: DocumentUpdateRequest,
    service: DocumentService = Depends(),
) -> DocumentDetailResponse:
    return service.update_document(document_id, payload)


@document_router.delete("/{document_id}", response_model=DocumentDeleteResponse)
def delete_document(
    document_id: UUID,
    service: DocumentService = Depends(),
) -> DocumentDeleteResponse:
    return service.delete_document(document_id)


@document_router.get(
    "/{document_id}/versions", response_model=PageResponse[DocumentVersionListItem]
)
def list_document_versions(
    document_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    service: DocumentService = Depends(),
) -> PageResponse[DocumentVersionListItem]:
    return service.list_versions(
        document_id=document_id, page=page, page_size=page_size
    )


@document_router.get(
    "/{document_id}/versions/{version_id}",
    response_model=DocumentVersionDetailResponse,
)
def get_document_version(
    document_id: UUID,
    version_id: UUID,
    service: DocumentService = Depends(),
) -> DocumentVersionDetailResponse:
    return service.get_version(document_id, version_id)


@document_router.patch(
    "/{document_id}/versions/{version_id}",
    response_model=DocumentVersionDetailResponse,
)
def update_document_version(
    document_id: UUID,
    version_id: UUID,
    payload: DocumentVersionUpdateRequest,
    service: DocumentService = Depends(),
) -> DocumentVersionDetailResponse:
    return service.update_version(document_id, version_id, payload)


@document_router.delete(
    "/{document_id}/versions/{version_id}",
    response_model=DocumentVersionDeleteResponse,
)
def delete_document_version(
    document_id: UUID,
    version_id: UUID,
    service: DocumentService = Depends(),
) -> DocumentVersionDeleteResponse:
    return service.delete_version(document_id, version_id)


@document_router.get("/{document_id}/jobs/stream")
async def stream_document_jobs(
    document_id: UUID,
    service: DocumentService = Depends(),
):
    return StreamingResponse(
        service.stream_document_jobs(document_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
