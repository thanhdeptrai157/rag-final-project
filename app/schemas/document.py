from typing import Any
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime


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
