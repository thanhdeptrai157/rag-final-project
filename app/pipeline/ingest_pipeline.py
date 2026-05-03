"""
Ingest Pipeline: Orchestrator chính để xử lý OCR, clean, chunk, embed, upsert Qdrant.

Flow:
1. Download file từ R2
2. OCR + clean text
3. Tạo document version
4. Chunk text
5. Insert chunks vào Postgres
6. Embed chunks
7. Upsert Qdrant
8. Update chunk embedding_id
9. Update document status = processed
"""

import uuid
import tempfile
from pathlib import Path
from typing import List
import hashlib

from sqlalchemy.orm import Session

from app.loaders.pdf_loader import PDFLoader
from app.preprocessing.cleaners.text_cleaner import TextCleaner
from app.preprocessing.structure.regulation_parser import RegulationParser
from app.chunking.regulation_chunker import RegulationChunker
from app.embedding.sentence_transformer_embedder import Embbedder
from app.retrieval.indexing_service import chunk_to_payload, prepare_text_for_embedding
from app.vectordb.qdrant_store import QdrantStore
from app.services.storage.r2_storage import R2Storage
from app.models.document import Document
from app.schemas.document import Document as DocumentSchema
from app.api.repositories.processing_repository import (
    DocumentVersionRepository,
    ChunkRepository,
)
from app.core.database import SessionLocal
from app.core.config import Config


class IngestPipeline:
    """Orchestrator chính cho ingest end-to-end."""

    def __init__(self):
        self.pdf_loader = PDFLoader(enable_ocr=True, force_ocr=True)
        self.text_cleaner = TextCleaner()
        self.chunker = RegulationChunker()
        self.embedder = Embbedder(model_name="BAAI/bge-m3")
        self.storage = R2Storage()
        self.qdrant_store = QdrantStore(
            collection_name=Config.QDRANT_COLLECTION,
            url=Config.QDRANT_HOST_URL,
            api_key=Config.QDRANT_API_KEY,
        )

    def ingest(self, document_id: uuid.UUID, db: Session) -> dict:
        """
        Xử lý ingest toàn bộ cho 1 document.

        Returns:
            {
                'success': bool,
                'message': str,
                'version_id': uuid.UUID | None,
                'chunk_count': int,
            }
        """
        try:
            # Lấy document từ DB
            doc_model = (
                db.query(Document).filter(Document.document_id == document_id).first()
            )
            if not doc_model:
                raise ValueError(f"Document {document_id} not found")

            print(f"[INGEST] Starting ingest for document {document_id}")

            # ===== STEP 1: Download file từ R2 =====
            print(f"[STEP 1] Downloading file from R2: {doc_model.file_path}")
            file_bytes = self.storage.download_bytes(doc_model.file_path)

            # ===== STEP 2: Tạo temp file để OCR =====
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
                tmp_file.write(file_bytes)
                tmp_file_path = tmp_file.name

            try:
                # ===== STEP 3: OCR + clean text =====
                print(f"[STEP 2] OCR PDF")
                doc_schema = self.pdf_loader.load(tmp_file_path)
                raw_text = doc_schema.raw_text
                print(f"[STEP 3] raw text: {(raw_text)}")
                print(f"[STEP 3] Cleaning text")
                cleaned_text = self.text_cleaner.clean(raw_text)

                # ===== STEP 4: Tạo document version =====
                print(f"[STEP 4] Creating document version")
                version_repo = DocumentVersionRepository(db)

                # Tính checksum của cleaned text
                text_checksum = hashlib.sha256(cleaned_text.encode()).hexdigest()

                # Upload raw/cleaned text lên R2
                raw_text_key = self._upload_text_to_r2(
                    document_id, "raw_text", raw_text
                )
                cleaned_text_key = self._upload_text_to_r2(
                    document_id, "cleaned_text", cleaned_text
                )

                version = version_repo.create_version(
                    document_id=document_id,
                    version_no=1,  # Có thể update nếu có version cũ
                    raw_text_path=raw_text_key,
                    cleaned_text_path=cleaned_text_key,
                    checksum=text_checksum,
                )
                print(f"[STEP 4] Version created: {version.version_id}")

                # ===== STEP 5: Chunk text =====
                print(f"[STEP 5] Chunking text")
                # Tạo schema Document từ dữ liệu để dùng cho chunker
                doc_for_chunking = DocumentSchema(
                    doc_id=str(document_id),
                    source_path=doc_model.source_path,
                    source_type=doc_model.source_type or "upload",
                    title=doc_model.title,
                    raw_text=cleaned_text,
                    metadata=doc_schema.metadata or {},
                )
                chunks_schema = self.chunker.chunk(doc_for_chunking)
                print(f"[STEP 5] Created {len(chunks_schema)} chunks")

                if not chunks_schema:
                    raise ValueError("No chunks created from document")

                # ===== STEP 6: Insert chunks vào Postgres =====
                print(f"[STEP 6] Inserting chunks to Postgres")
                chunk_repo = ChunkRepository(db)
                chunk_data = [
                    {
                        "chunk_index": chunk.chunk_index,
                        "chunk_text": chunk.text,
                        "token_count": None,  # Có thể tính sau
                        "page_number": None,
                        "section_path": chunk.section_path,
                        "metadata_json": chunk.metadata,
                    }
                    for chunk in chunks_schema
                ]
                chunks_db = chunk_repo.create_chunks(
                    document_id=document_id,
                    version_id=version.version_id,
                    chunk_data=chunk_data,
                )
                print(f"[STEP 6] Inserted {len(chunks_db)} chunks to DB")

                # ===== STEP 7: Embed chunks =====
                print(f"[STEP 7] Embedding chunks")
                texts_to_embed = [
                    prepare_text_for_embedding(chunk) for chunk in chunks_schema
                ]
                vectors = self.embedder.embed_texts(texts_to_embed)
                print(f"[STEP 7] Generated {len(vectors)} embeddings")

                # ===== STEP 8: Ensure Qdrant collection exists =====
                print(f"[STEP 8a] Checking Qdrant collection")
                vector_size = len(vectors[0]) if vectors else 1024
                self.qdrant_store.ensure_collection_exists(vector_size=vector_size)

                # ===== STEP 8: Upsert Qdrant =====
                print(f"[STEP 8b] Upserting to Qdrant")
                payloads = [chunk_to_payload(chunk) for chunk in chunks_schema]
                point_ids = [str(chunk.chunk_id) for chunk in chunks_db]

                self.qdrant_store.upsert_chunks(
                    ids=point_ids,
                    vectors=vectors,
                    payloads=payloads,
                    batch_size=100,
                )
                print(f"[STEP 8] Upserted {len(vectors)} points to Qdrant")

                # ===== STEP 9: Update chunk embedding_id =====
                print(f"[STEP 9] Updating chunk embedding IDs")
                chunk_ids = [chunk.chunk_id for chunk in chunks_db]
                chunk_repo.update_embedding_ids(chunk_ids, point_ids)

                # ===== STEP 10: Update document status =====
                print(f"[STEP 10] Updating document status to processed")
                doc_model.status = "processed"
                db.commit()

                print(f"[INGEST] ✓ Completed for document {document_id}")
                return {
                    "success": True,
                    "message": f"Ingest completed: {len(chunks_db)} chunks processed",
                    "version_id": version.version_id,
                    "chunk_count": len(chunks_db),
                }

            finally:
                # Xóa temp file
                Path(tmp_file_path).unlink(missing_ok=True)

        except Exception as e:
            print(f"[INGEST] ✗ Error: {str(e)}")
            doc_model.status = "failed"
            db.commit()
            raise

    def _upload_text_to_r2(
        self, document_id: uuid.UUID, text_type: str, content: str
    ) -> str:
        """Upload text (raw/cleaned) lên R2."""
        from datetime import datetime, timezone
        import uuid as uuid_module

        now = datetime.now(timezone.utc)
        key = f"documents/text/{now.year}/{now.month:02d}/{document_id}/{text_type}/{uuid_module.uuid4()}.txt"

        self.storage.upload_bytes(
            data=content.encode("utf-8"),
            object_key=key,
            content_type="text/plain; charset=utf-8",
        )
        return key
