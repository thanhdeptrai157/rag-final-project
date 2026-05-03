import uuid

from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import BaseModel
from app.models.document_version import DocumentVersion
from app.models.processing_job import ProcessingJob
from app.models.chunk import Chunk


class Document(Base, BaseModel):
    __tablename__ = "documents"

    __table_args__ = (
        CheckConstraint(
            "status IN ('uploaded', 'processing', 'processed', 'failed')",
            name="ck_documents_status",
        ),
        CheckConstraint(
            "source_type IN ('upload', 'url', 'crawl')",
            name="ck_documents_source_type",
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="uploaded")
    checksum: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    versions = relationship(
        "DocumentVersion", back_populates="document", cascade="all, delete-orphan"
    )
    chunks = relationship(
        "Chunk", back_populates="document", cascade="all, delete-orphan"
    )
    processing_jobs = relationship(
        "ProcessingJob", back_populates="document", cascade="all, delete-orphan"
    )
