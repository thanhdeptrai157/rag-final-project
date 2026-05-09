from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Document(BaseModel):
    doc_id: str
    source_path: str
    source_type: str
    title: str
    raw_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentUploadResponse(BaseModel):
    document_id: UUID
    title: str
    file_path: str | None
    mime_type: str | None
    checksum: str | None
    status: str
    created_at: datetime
    job_id: str  # ID của processing job để track progress


class DocumentUpdateRequest(BaseModel):
    title: str | None = None
    source_path: str | None = None
    source_type: str | None = None
    file_path: str | None = None
    mime_type: str | None = None
    status: str | None = None
    checksum: str | None = None


class DocumentListItem(BaseModel):
    document_id: UUID
    title: str
    source_path: str
    source_type: str
    file_path: str | None
    mime_type: str | None
    status: str
    checksum: str | None
    created_at: datetime
    updated_at: datetime
    versions_count: int = 0
    chunks_count: int = 0


class DocumentVersionListItem(BaseModel):
    version_id: UUID
    document_id: UUID
    version_no: int
    raw_text_path: str | None
    cleaned_text_path: str | None
    checksum: str | None
    created_at: datetime
    updated_at: datetime
    chunks_count: int = 0


class DocumentVersionUpdateRequest(BaseModel):
    raw_text_path: str | None = None
    cleaned_text_path: str | None = None
    checksum: str | None = None


class DocumentVersionDetailResponse(DocumentVersionListItem):
    pass


class DocumentDetailResponse(DocumentListItem):
    versions: list[DocumentVersionListItem] = Field(default_factory=list)


class DocumentListResponse(BaseModel):
    items: list[DocumentListItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class DocumentVersionListResponse(BaseModel):
    items: list[DocumentVersionListItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class DocumentDeleteResponse(BaseModel):
    document_id: UUID
    deleted: bool = True


class DocumentVersionDeleteResponse(BaseModel):
    version_id: UUID
    document_id: UUID
    deleted: bool = True


class DocumentJobsStreamEvent(BaseModel):
    document_id: UUID
    jobs: list[dict[str, Any]] = Field(default_factory=list)
    terminal: bool = False
