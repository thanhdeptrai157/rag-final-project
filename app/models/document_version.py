import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import BaseModel


class DocumentVersion(Base, BaseModel):
    __tablename__ = "document_versions"

    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_no", name="uq_document_versions_doc_ver"
        ),
    )

    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.document_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_no: Mapped[int] = mapped_column(nullable=False)
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.version_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_checksum: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    raw_text_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    cleaned_text_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    layout_json_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    document = relationship("Document", back_populates="versions")
    chunks = relationship(
        "Chunk", back_populates="version", cascade="all, delete-orphan"
    )
