from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.document import Document


class DocumentRepository:
    def __init__(self, db: Session = Depends(get_db)) -> None:
        self.db = db

    def get_by_checksum(self, checksum: str) -> Document | None:
        return self.db.query(Document).filter(Document.checksum == checksum).first()

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

