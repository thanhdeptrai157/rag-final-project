"""
Repository để quản lý processing jobs, document versions, chunks.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session
from fastapi import Depends

from app.core.database import get_db
from app.models.processing_job import ProcessingJob
from app.models.document_version import DocumentVersion
from app.models.chunk import Chunk
from app.models.document import Document


class ProcessingJobRepository:
    def __init__(self, db: Session = Depends(get_db)) -> None:
        self.db = db

    def create_ingest_job(self, document_id: uuid.UUID) -> ProcessingJob:
        """Tạo 1 job ingest duy nhất cho document."""
        job = ProcessingJob(
            document_id=document_id,
            job_type="ingest",
            status="pending",
            retry_count=0,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_pending_jobs(
        self, document_id: uuid.UUID = None, limit: int = 10
    ) -> List[ProcessingJob]:
        """Lấy danh sách job pending để worker xử lý.

        Args:
            document_id: Nếu có, lọc job cho document cụ thể
            limit: Số lượng job tối đa
        """
        query = (
            self.db.query(ProcessingJob)
            .filter(ProcessingJob.status == "pending")
            .filter(ProcessingJob.job_type == "ingest")
        )
        if document_id:
            query = query.filter(ProcessingJob.document_id == document_id)
        return query.limit(limit).all()

    def update_job_status(
        self,
        job_id: uuid.UUID,
        status: str,
        error_message: Optional[str] = None,
    ) -> ProcessingJob:
        """Cập nhật trạng thái job và thời gian."""
        job = (
            self.db.query(ProcessingJob).filter(ProcessingJob.job_id == job_id).first()
        )
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.status = status
        if status == "running" and not job.started_at:
            job.started_at = datetime.now(timezone.utc)
        if status in ("completed", "failed"):
            job.finished_at = datetime.now(timezone.utc)
        if error_message:
            job.error_message = error_message

        self.db.commit()
        self.db.refresh(job)
        return job

    def increment_retry_count(self, job_id: uuid.UUID) -> ProcessingJob:
        """Tăng retry_count khi failed."""
        job = (
            self.db.query(ProcessingJob).filter(ProcessingJob.job_id == job_id).first()
        )
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.retry_count += 1
        self.db.commit()
        self.db.refresh(job)
        return job

    def reset_job_to_pending(self, job_id: uuid.UUID) -> ProcessingJob:
        """Reset job từ failed sang pending để retry."""
        job = (
            self.db.query(ProcessingJob).filter(ProcessingJob.job_id == job_id).first()
        )
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.status = "pending"
        job.error_message = None
        job.started_at = None
        job.finished_at = None
        self.db.commit()
        self.db.refresh(job)
        return job


class DocumentVersionRepository:
    def __init__(self, db: Session = Depends(get_db)) -> None:
        self.db = db

    def create_version(
        self,
        document_id: uuid.UUID,
        version_no: int,
        raw_text_path: Optional[str] = None,
        cleaned_text_path: Optional[str] = None,
        checksum: Optional[str] = None,
    ) -> DocumentVersion:
        """Tạo document version mới."""
        version = DocumentVersion(
            document_id=document_id,
            version_no=version_no,
            raw_text_path=raw_text_path,
            cleaned_text_path=cleaned_text_path,
            checksum=checksum,
        )
        self.db.add(version)
        self.db.commit()
        self.db.refresh(version)
        return version

    def get_latest_version(self, document_id: uuid.UUID) -> Optional[DocumentVersion]:
        """Lấy phiên bản mới nhất của document."""
        return (
            self.db.query(DocumentVersion)
            .filter(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_no.desc())
            .first()
        )


class ChunkRepository:
    def __init__(self, db: Session = Depends(get_db)) -> None:
        self.db = db

    def create_chunks(
        self,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
        chunk_data: List[dict],
    ) -> List[Chunk]:
        """
        Insert nhiều chunks cùng lúc.
        chunk_data: list of {
            'chunk_index': int,
            'chunk_text': str,
            'token_count': int | None,
            'page_number': int | None,
            'section_path': str | None,
            'metadata_json': dict | None,
        }
        """
        chunks = []
        for data in chunk_data:
            chunk = Chunk(
                document_id=document_id,
                version_id=version_id,
                chunk_index=data.get("chunk_index"),
                chunk_text=data.get("chunk_text"),
                token_count=data.get("token_count"),
                page_number=data.get("page_number"),
                section_path=data.get("section_path"),
                metadata_json=data.get("metadata_json"),
                embedding_id=None,  # Sẽ update sau khi embed + upsert Qdrant
            )
            chunks.append(chunk)

        self.db.add_all(chunks)
        self.db.commit()

        # Refresh để lấy IDs
        for chunk in chunks:
            self.db.refresh(chunk)

        return chunks

    def update_embedding_ids(
        self, chunk_ids: List[uuid.UUID], embedding_ids: List[str]
    ) -> None:
        """Update embedding_id cho chunks sau khi upsert Qdrant."""
        for chunk_id, embedding_id in zip(chunk_ids, embedding_ids):
            chunk = self.db.query(Chunk).filter(Chunk.chunk_id == chunk_id).first()
            if chunk:
                chunk.embedding_id = embedding_id
        self.db.commit()

    def get_chunks_by_version(self, version_id: uuid.UUID) -> List[Chunk]:
        """Lấy tất cả chunks của 1 version."""
        return (
            self.db.query(Chunk)
            .filter(Chunk.version_id == version_id)
            .order_by(Chunk.chunk_index)
            .all()
        )
