from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.document import Document


class DocumentRepository:
    def __init__(self, db: Session = Depends(get_db)) -> None:
        self.db = db

    def get_by_checksum(self, checksum: str) -> Document | None:
        return self.db.query(Document).filter(Document.checksum == checksum).first()

    def list_paginated(
        self, *, page: int, page_size: int
    ) -> tuple[list[Document], int]:
        query = self.db.query(Document).order_by(Document.created_at.desc())
        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    def get_by_id(self, document_id) -> Document | None:
        return (
            self.db.query(Document).filter(Document.document_id == document_id).first()
        )

    def create(
        self,
        *,
        title: str,
        source_path: str,
        source_type: str,
        file_path: str,
        mime_type: str | None,
        status: str,
        checksum: str,
    ) -> Document:
        document = Document(
            title=title,
            source_path=source_path,
            source_type=source_type,
            file_path=file_path,
            mime_type=mime_type,
            status=status,
            checksum=checksum,
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def update(self, document: Document, **fields) -> Document:
        for key, value in fields.items():
            setattr(document, key, value)
        self.db.commit()
        self.db.refresh(document)
        return document

    def delete(self, document: Document) -> None:
        self.db.delete(document)
        self.db.commit()
