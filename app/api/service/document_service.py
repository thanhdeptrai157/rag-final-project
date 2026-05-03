from __future__ import annotations

from pathlib import Path

from fastapi import Depends, HTTPException, UploadFile, status

from app.api.repositories.document_repository import DocumentRepository
from app.api.repositories.processing_repository import ProcessingJobRepository
from app.schemas.document import DocumentUploadResponse
from app.services.storage.r2_storage import R2Storage
from app.utils.file_utils import build_r2_object_key, sha256_bytes
from app.workers.background_worker import get_worker

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


class DocumentService:
    def __init__(
        self,
        repo: DocumentRepository = Depends(),
        storage: R2Storage = Depends(),
        job_repo: ProcessingJobRepository = Depends(),
    ) -> None:
        self.repo = repo
        self.storage = storage
        self.job_repo = job_repo

    async def create_document(self, file: UploadFile) -> DocumentUploadResponse:
        contents = await file.read()
        self._validate_upload(file=file, contents=contents)

        checksum = sha256_bytes(contents)
        existing = self.repo.get_by_checksum(checksum)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "File already exists.",
                    "document_id": str(existing.document_id),
                },
            )

        object_key = build_r2_object_key(file.filename)
        self.storage.upload_bytes(
            data=contents,
            object_key=object_key,
            content_type=file.content_type,
        )

        document = self.repo.create(
            title=Path(file.filename).name,
            source_path=Path(file.filename).name,
            source_type="upload",
            file_path=object_key,
            mime_type=file.content_type,
            status="uploaded",
            checksum=checksum,
        )

        # ===== Tạo processing job + enqueue worker =====
        job = self.job_repo.create_ingest_job(document.document_id)
        worker = get_worker()
        worker.enqueue_document(document.document_id)

        return DocumentUploadResponse(
            document_id=document.document_id,
            title=document.title,
            file_path=document.file_path,
            mime_type=document.mime_type,
            checksum=document.checksum,
            status=document.status,
            created_at=document.created_at,
            job_id=str(job.job_id),
        )

    def _validate_upload(self, *, file: UploadFile, contents: bytes) -> None:
        if file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type",
            )

        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename is required",
            )

        if not contents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is empty",
            )

        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File size exceeds limit",
            )
