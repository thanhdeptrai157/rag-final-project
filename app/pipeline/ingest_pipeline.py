# app/pipelines/ingest_pipeline.py

import hashlib
import json
import tempfile
import uuid
from pathlib import Path
from typing import List

from app.api.repositories.processing_repository import (
    ChunkRepository,
    DocumentVersionRepository,
)
from app.chunking.universal_document_chunker import UniversalLegalChunker
from app.core.config import Config
from app.core.database import SessionLocal
from app.embedding.sentence_transformer_embedder import get_embedder
from app.loaders.pdf_loader_paddle_ocr import PDFLoader
from app.loaders.pdf_loader_mineru_ocr import MinerUPDFLoader
from app.loaders.text_loader import TextFileLoader
from app.loaders.docx_loader import DocxLoader
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.preprocessing.cleaners.text_cleaner import TextCleaner
from app.retrieval.indexing_service import chunk_to_payload, prepare_text_for_embedding
from app.schemas.document import Document as DocumentSchema
from app.services.storage.r2_storage import R2Storage
from app.vectordb.qdrant_store import QdrantStore

# MIME types không cần OCR — đọc text trực tiếp
_DIRECT_TEXT_MIMES = {
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class IngestPipeline:
    def __init__(self):
        self.pdf_loader = self._build_pdf_loader()
        self.text_loader = TextFileLoader()
        self.docx_loader = DocxLoader()
        self.text_cleaner = TextCleaner()
        self.chunker = UniversalLegalChunker()
        self.embedder = get_embedder()
        self.storage = R2Storage()
        self.qdrant_store = QdrantStore(
            collection_name=Config.QDRANT_COLLECTION,
            url=Config.QDRANT_HOST_URL,
            api_key=Config.QDRANT_API_KEY,
        )

    def ingest(self, version_id) -> dict:
        context = None
        try:
            context = self._load_ingest_context(version_id)
            self._update_version_and_document_status(
                version_id=context["version_id"],
                document_id=context["document_id"],
                version_status="processing",
                document_status="processing",
            )

            mime_type = context.get("source_mime_type") or ""
            use_direct = mime_type in _DIRECT_TEXT_MIMES

            print(f"[INGEST] Starting ingest for version {version_id}")
            print(f"[INGEST] MIME type: {mime_type!r} → {'direct text' if use_direct else 'OCR'}")
            print(f"[STEP 1] Downloading file from R2: {context['source_file_path']}")
            file_bytes = self.storage.download_bytes(context["source_file_path"])

            if use_direct:
                return self._ingest_direct_text(context, file_bytes, mime_type)
            else:
                return self._ingest_via_ocr(context, file_bytes)

        except Exception as e:
            print(f"[INGEST] Error: {str(e)}")
            try:
                if context:
                    self._update_version_and_document_status(
                        version_id=context["version_id"],
                        document_id=context["document_id"],
                        version_status="failed",
                        document_status="failed",
                    )
            except Exception:
                pass

            raise

    # ------------------------------------------------------------------
    # Ingest paths
    # ------------------------------------------------------------------

    def _ingest_direct_text(
        self, context: dict, file_bytes: bytes, mime_type: str
    ) -> dict:
        """Ingest cho txt/docx: đọc text trực tiếp, bỏ qua OCR."""
        is_docx = "wordprocessingml" in mime_type
        suffix = ".docx" if is_docx else ".txt"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            print(f"[STEP 2] Reading {suffix} directly (no OCR)")
            loader = self.docx_loader if is_docx else self.text_loader
            doc_schema = loader.load(tmp_path)
            raw_text = doc_schema.raw_text
            doc_schema.metadata = doc_schema.metadata or {}

            return self._run_common_steps(context, doc_schema, raw_text, layout_data=None)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def _ingest_via_ocr(self, context: dict, file_bytes: bytes) -> dict:
        """Ingest cho PDF: qua OCR loader."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            tmp_file.write(file_bytes)
            tmp_file_path = tmp_file.name

        try:
            print("[STEP 2] OCR PDF")
            doc_schema = self.pdf_loader.load(tmp_file_path)
            raw_text = doc_schema.raw_text
            doc_schema.metadata = doc_schema.metadata or {}

            layout_json_key, layout_data = self._upload_layout_json_to_r2(
                context["document_id"], doc_schema.metadata
            )
            if layout_json_key:
                doc_schema.metadata["layout_json_path"] = layout_json_key

            return self._run_common_steps(
                context, doc_schema, raw_text, layout_data=layout_data
            )
        finally:
            Path(tmp_file_path).unlink(missing_ok=True)

    def _run_common_steps(
        self,
        context: dict,
        doc_schema,
        raw_text: str,
        layout_data,
    ) -> dict:
        """Các bước chung sau khi đã có raw_text: clean → chunk → embed → lưu."""
        print("[STEP 3] Cleaning text")
        cleaned_text = self.text_cleaner.clean(raw_text)

        print("[STEP 4] Updating version artifacts")
        text_checksum = hashlib.sha256(cleaned_text.encode()).hexdigest()

        raw_text_key = self._upload_text_to_r2(
            context["document_id"], "raw_text", raw_text
        )
        cleaned_text_key = self._upload_text_to_r2(
            context["document_id"], "cleaned_text", cleaned_text
        )

        # Layout JSON chỉ có khi qua OCR (PDF); txt/docx không có
        layout_json_key: str | None = None
        if layout_data is not None:
            layout_json_key, layout_data = self._upload_layout_json_to_r2(
                context["document_id"], doc_schema.metadata
            )
            if layout_json_key:
                doc_schema.metadata["layout_json_path"] = layout_json_key

        previous_version = self._load_previous_version_context(
            context["previous_version_id"]
        )

        print("[STEP 5] Chunking text")
        doc_for_chunking = DocumentSchema(
            doc_id=str(context["document_id"]),
            source_path=context["source_file_path"],
            source_type=context["source_type"],
            title=context["title"],
            raw_text=cleaned_text,
            metadata=doc_schema.metadata,
            version_id=str(context["version_id"]),
            version_no=context["version_no"],
            previous_version_id=(
                str(previous_version["version_id"]) if previous_version else None
            ),
            previous_version_number=(
                previous_version["version_no"] if previous_version else None
            ),
        )

        chunker = self.chunker
        print(f"[STEP 5] Selected chunker: {chunker.__class__.__name__}")

        chunks_schema = chunker.chunk(doc_for_chunking, layout_data=layout_data)
        print(f"[STEP 5] Created {len(chunks_schema)} chunks")

        if not chunks_schema:
            raise ValueError("No chunks created from document")

        if previous_version:
            previous_chunks = self._load_chunks_by_version(
                previous_version["version_id"]
            )
            self._annotate_chunks_with_previous_version(
                chunks_schema=chunks_schema,
                previous_version=previous_version,
                previous_chunks=previous_chunks,
            )

        print("[STEP 6] Inserting chunks to Postgres")
        chunk_data = [
            {
                "chunk_index": chunk.chunk_index,
                "chunk_text": chunk.text,
                "token_count": None,
                "page_number": chunk.page_start,
                "section_path": chunk.section_path,
                "metadata_json": chunk.metadata,
            }
            for chunk in chunks_schema
        ]
        chunk_ids = self._create_chunks(
            document_id=context["document_id"],
            version_id=context["version_id"],
            chunk_data=chunk_data,
        )
        point_ids = [str(chunk_id) for chunk_id in chunk_ids]

        print("[STEP 7] Embedding chunks")
        texts_to_embed = [
            prepare_text_for_embedding(chunk) for chunk in chunks_schema
        ]
        vectors = self.embedder.embed_texts(texts_to_embed)

        print("[STEP 8a] Checking Qdrant collection")
        vector_size = len(vectors[0]) if vectors else 1024
        self.qdrant_store.ensure_collection_exists(vector_size=vector_size)

        print("[STEP 8b] Upserting to Qdrant")
        payloads = [chunk_to_payload(chunk) for chunk in chunks_schema]
        self.qdrant_store.upsert_chunks(
            ids=point_ids,
            vectors=vectors,
            payloads=payloads,
            batch_size=100,
        )

        print("[STEP 9] Updating chunk embedding IDs")
        self._update_embedding_ids(chunk_ids, point_ids)

        print("[STEP 10] Updating version/document status to processed")
        self._update_version_and_document_status(
            version_id=context["version_id"],
            document_id=context["document_id"],
            version_status="processed",
            document_status="processed",
            raw_text_path=raw_text_key,
            cleaned_text_path=cleaned_text_key,
            layout_json_path=layout_json_key,
            checksum=text_checksum,
        )

        return {
            "success": True,
            "message": f"Ingest completed: {len(chunk_ids)} chunks processed",
            "version_id": context["version_id"],
            "chunk_count": len(chunk_ids),
            "layout_json_path": layout_json_key,
        }

    def _build_pdf_loader(self):
        provider = Config.PDF_OCR_PROVIDER
        if provider in {"mineru", "mineru_ocr"}:
            return MinerUPDFLoader(enable_ocr=True, force_ocr=True)
        return PDFLoader(enable_ocr=True, force_ocr=True)

    def _upload_text_to_r2(
        self, document_id: uuid.UUID, text_type: str, content: str
    ) -> str:
        from datetime import datetime, timezone
        import uuid as uuid_module

        now = datetime.now(timezone.utc)
        key = (
            f"documents/text/{now.year}/{now.month:02d}/"
            f"{document_id}/{text_type}/{uuid_module.uuid4()}.txt"
        )

        self.storage.upload_bytes(
            data=content.encode("utf-8"),
            object_key=key,
            content_type="text/plain; charset=utf-8",
        )
        return key

    def _upload_layout_json_to_r2(
        self, document_id: uuid.UUID, metadata: dict
    ) -> tuple[str | None, dict | list | None]:
        layout_bytes: bytes | None = None
        layout_data: dict | list | None = None

        layout_path = metadata.get("mineru_layout_path") or metadata.get("layout_path")

        if layout_path:
            path = Path(str(layout_path))
            if path.exists():
                layout_bytes = path.read_bytes()
                try:
                    layout_data = json.loads(layout_bytes.decode("utf-8"))
                    print("[INGEST] Loaded layout data from local file")
                except Exception as e:
                    print(f"[INGEST] Warning: Failed to parse local layout json: {e}")
                    layout_data = None

        if layout_bytes is None and metadata.get("layout") is not None:
            layout_data = metadata["layout"]
            layout_bytes = json.dumps(layout_data, ensure_ascii=False, indent=2).encode(
                "utf-8"
            )

        if layout_bytes is None:
            return None, None

        from datetime import datetime, timezone
        import uuid as uuid_module

        now = datetime.now(timezone.utc)
        key = (
            f"documents/text/{now.year}/{now.month:02d}/"
            f"{document_id}/layout_json/{uuid_module.uuid4()}.json"
        )

        self.storage.upload_bytes(
            data=layout_bytes,
            object_key=key,
            content_type="application/json; charset=utf-8",
        )

        return key, layout_data

    def _choose_chunker(self, text: str):
        return self.chunker

    def _load_ingest_context(self, version_id) -> dict:
        with SessionLocal() as db:
            version = DocumentVersionRepository(db).get_by_id(version_id)
            if not version:
                raise ValueError(f"Version {version_id} not found")

            document = (
                db.query(Document)
                .filter(Document.document_id == version.document_id)
                .first()
            )
            if not document:
                raise ValueError(f"Document {version.document_id} not found")

            if not version.source_file_path:
                raise ValueError(f"Version {version_id} does not have source_file_path")

            return {
                "version_id": version.version_id,
                "document_id": version.document_id,
                "version_no": version.version_no,
                "previous_version_id": version.previous_version_id,
                "source_file_path": version.source_file_path,
                "source_mime_type": version.source_mime_type,
                "title": document.title,
                "source_type": document.source_type or "upload",
                "layout_json_path": version.layout_json_path,
            }

    def _load_previous_version_context(self, previous_version_id) -> dict | None:
        if not previous_version_id:
            return None

        with SessionLocal() as db:
            version = DocumentVersionRepository(db).get_by_id(previous_version_id)
            if not version:
                return None

            return {
                "version_id": version.version_id,
                "version_no": version.version_no,
            }

    def _load_chunks_by_version(self, version_id) -> list:
        with SessionLocal() as db:
            return ChunkRepository(db).get_chunks_by_version(version_id)

    def _create_chunks(
        self,
        *,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
        chunk_data: List[dict],
    ) -> List[uuid.UUID]:
        with SessionLocal() as db:
            chunks = ChunkRepository(db).create_chunks(
                document_id=document_id,
                version_id=version_id,
                chunk_data=chunk_data,
            )
            return [chunk.chunk_id for chunk in chunks]

    def _update_embedding_ids(
        self, chunk_ids: List[uuid.UUID], embedding_ids: List[str]
    ) -> None:
        with SessionLocal() as db:
            ChunkRepository(db).update_embedding_ids(chunk_ids, embedding_ids)

    def _update_version_and_document_status(
        self,
        *,
        version_id: uuid.UUID,
        document_id: uuid.UUID,
        version_status: str | None = None,
        document_status: str | None = None,
        raw_text_path: str | None = None,
        cleaned_text_path: str | None = None,
        layout_json_path: str | None = None,
        checksum: str | None = None,
    ) -> None:
        with SessionLocal() as db:
            version = (
                db.query(DocumentVersion)
                .filter(DocumentVersion.version_id == version_id)
                .first()
            )
            if not version:
                raise ValueError(f"Version {version_id} not found")

            if version_status is not None:
                version.status = version_status
            if raw_text_path is not None:
                version.raw_text_path = raw_text_path
            if cleaned_text_path is not None:
                version.cleaned_text_path = cleaned_text_path
            if layout_json_path is not None:
                version.layout_json_path = layout_json_path
            if checksum is not None:
                version.checksum = checksum

            document = (
                db.query(Document).filter(Document.document_id == document_id).first()
            )
            if document and document_status is not None:
                document.status = document_status

            db.commit()

    def _annotate_chunks_with_previous_version(
        self,
        *,
        chunks_schema: List,
        previous_version,
        previous_chunks,
    ) -> None:
        previous_by_article = {}

        for chunk in previous_chunks:
            metadata = chunk.metadata_json or {}
            article_number = metadata.get("article_number") or metadata.get(
                "target_article_number"
            )
            if article_number is not None:
                previous_by_article[str(article_number)] = chunk

        for chunk in chunks_schema:
            metadata = chunk.metadata or {}
            current_article = metadata.get("article_number") or metadata.get(
                "target_article_number"
            )
            if current_article is None:
                continue

            previous_chunk = previous_by_article.get(str(current_article))

            metadata["previous_version_id"] = str(previous_version["version_id"])
            metadata["previous_version_number"] = previous_version["version_no"]

            if not previous_chunk:
                metadata["relation_to_previous_version"] = "new_article"
                chunk.metadata = metadata
                continue

            previous_metadata = previous_chunk.metadata_json or {}
            metadata["previous_chunk_id"] = str(previous_chunk.chunk_id)
            metadata["previous_chunk_title"] = previous_chunk.chunk_text[:120]

            if (
                metadata.get("is_amendment")
                or metadata.get("chunk_kind") == "amendment"
            ):
                metadata["relation_to_previous_version"] = "amends_article"
            else:
                metadata["relation_to_previous_version"] = "matched_article"

            metadata["previous_article_number"] = previous_metadata.get(
                "article_number"
            ) or previous_metadata.get("target_article_number")

            chunk.metadata = metadata
