from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from fastapi import Depends, HTTPException, UploadFile, status

from app.api.repositories.document_repository import DocumentRepository
from app.api.repositories.processing_repository import (
    DocumentVersionRepository,
    ProcessingJobRepository,
)
from app.core.database import SessionLocal
from app.models.document import Document
from app.schemas.document import (
    DocumentDeleteResponse,
    DocumentDetailResponse,
    DocumentJobsStreamEvent,
    DocumentListItem,
    DocumentListResponse,
    DocumentUpdateRequest,
    DocumentUploadResponse,
    DocumentVersionDeleteResponse,
    DocumentVersionDetailResponse,
    DocumentVersionListItem,
    DocumentVersionListResponse,
    DocumentVersionUpdateRequest,
)
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
        version_repo: DocumentVersionRepository = Depends(),
    ) -> None:
        self.repo = repo
        self.storage = storage
        self.job_repo = job_repo
        self.version_repo = version_repo

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

    def list_documents(self, page: int, page_size: int) -> DocumentListResponse:
        items, total = self.repo.list_paginated(page=page, page_size=page_size)
        return DocumentListResponse(
            items=[self._to_document_list_item(document) for document in items],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=max((total + page_size - 1) // page_size, 1) if total else 0,
        )

    def get_document(self, document_id: UUID) -> DocumentDetailResponse:
        document = self._require_document(document_id)
        versions, _ = self.version_repo.list_versions(
            document_id=document_id, page=1, page_size=1000
        )
        return DocumentDetailResponse(
            **self._to_document_list_item(document).model_dump(),
            versions=[self._to_version_list_item(version) for version in versions],
        )

    def update_document(
        self, document_id: UUID, payload: DocumentUpdateRequest
    ) -> DocumentDetailResponse:
        document = self._require_document(document_id)
        data = payload.model_dump(exclude_unset=True)
        if "source_type" in data and data["source_type"] not in {
            "upload",
            "url",
            "crawl",
        }:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid source_type",
            )
        if "status" in data and data["status"] not in {
            "uploaded",
            "processing",
            "processed",
            "failed",
        }:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status",
            )
        updated = self.repo.update(document, **data)
        versions, _ = self.version_repo.list_versions(
            document_id=document_id, page=1, page_size=1000
        )
        return DocumentDetailResponse(
            **self._to_document_list_item(updated).model_dump(),
            versions=[self._to_version_list_item(version) for version in versions],
        )

    def delete_document(self, document_id: UUID) -> DocumentDeleteResponse:
        document = self._require_document(document_id)
        self._delete_document_storage(document)
        self.repo.delete(document)
        return DocumentDeleteResponse(document_id=document_id)

    def list_versions(
        self, document_id: UUID, page: int, page_size: int
    ) -> DocumentVersionListResponse:
        self._require_document(document_id)
        items, total = self.version_repo.list_versions(
            document_id=document_id, page=page, page_size=page_size
        )
        return DocumentVersionListResponse(
            items=[self._to_version_list_item(version) for version in items],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=max((total + page_size - 1) // page_size, 1) if total else 0,
        )

    def get_version(
        self, document_id: UUID, version_id: UUID
    ) -> DocumentVersionDetailResponse:
        version = self._require_version(document_id, version_id)
        return DocumentVersionDetailResponse(
            **self._to_version_list_item(version).model_dump()
        )

    def update_version(
        self,
        document_id: UUID,
        version_id: UUID,
        payload: DocumentVersionUpdateRequest,
    ) -> DocumentVersionDetailResponse:
        version = self._require_version(document_id, version_id)
        updated = self.version_repo.update(
            version, **payload.model_dump(exclude_unset=True)
        )
        return DocumentVersionDetailResponse(
            **self._to_version_list_item(updated).model_dump()
        )

    def delete_version(
        self, document_id: UUID, version_id: UUID
    ) -> DocumentVersionDeleteResponse:
        version = self._require_version(document_id, version_id)
        self._delete_version_storage(version)
        self.version_repo.delete(version)
        return DocumentVersionDeleteResponse(
            version_id=version_id,
            document_id=document_id,
        )

    async def stream_document_jobs(self, document_id: UUID):
        self._require_document(document_id)
        last_snapshot: str | None = None

        while True:
            db_session = SessionLocal()
            try:
                job_repo = ProcessingJobRepository(db_session)
                jobs = job_repo.get_jobs_by_document(document_id)
                payload = DocumentJobsStreamEvent(
                    document_id=document_id,
                    jobs=[self._job_to_payload(job) for job in jobs],
                    terminal=bool(jobs)
                    and all(job.status in {"completed", "failed"} for job in jobs),
                )
                snapshot = payload.model_dump_json()

                if snapshot != last_snapshot:
                    last_snapshot = snapshot
                    yield f"data: {snapshot}\n\n"

                if payload.terminal:
                    break

            finally:
                db_session.close()

            await asyncio.sleep(1)

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

    def _require_document(self, document_id: UUID) -> Document:
        document = self.repo.get_by_id(document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )
        return document

    def _require_version(self, document_id: UUID, version_id: UUID):
        version = self.version_repo.get_by_document_and_id(document_id, version_id)
        if not version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document version not found",
            )
        return version

    def _to_document_list_item(self, document: Document) -> DocumentListItem:
        return DocumentListItem(
            document_id=document.document_id,
            title=document.title,
            source_path=document.source_path,
            source_type=document.source_type,
            file_path=document.file_path,
            mime_type=document.mime_type,
            status=document.status,
            checksum=document.checksum,
            created_at=document.created_at,
            updated_at=document.updated_at,
            versions_count=len(document.versions or []),
            chunks_count=len(document.chunks or []),
        )

    def _to_version_list_item(self, version) -> DocumentVersionListItem:
        return DocumentVersionListItem(
            version_id=version.version_id,
            document_id=version.document_id,
            version_no=version.version_no,
            raw_text_path=version.raw_text_path,
            cleaned_text_path=version.cleaned_text_path,
            checksum=version.checksum,
            created_at=version.created_at,
            updated_at=version.updated_at,
            chunks_count=len(version.chunks or []),
        )

    def _job_to_payload(self, job) -> dict:
        return {
            "job_id": str(job.job_id),
            "document_id": str(job.document_id),
            "job_type": job.job_type,
            "status": job.status,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "error_message": job.error_message,
            "retry_count": job.retry_count,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        }

    def _delete_document_storage(self, document: Document) -> None:
        keys = [document.file_path]
        versions = self.version_repo.list_versions(
            document.document_id, page=1, page_size=1000
        )[0]
        for version in versions:
            keys.extend([version.raw_text_path, version.cleaned_text_path])

        for key in keys:
            if not key:
                continue
            try:
                self.storage.delete_object(key)
            except Exception:
                continue

    def _delete_version_storage(self, version) -> None:
        for key in [version.raw_text_path, version.cleaned_text_path]:
            if not key:
                continue
            try:
                self.storage.delete_object(key)
            except Exception:
                continue
