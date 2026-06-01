from uuid import UUID

from app.core.database import SessionLocal
from app.llm.gemini_client import GeminiClient
from app.models.document import Document
from app.models.chunk import Chunk as ChunkModel
from app.models.document_version import DocumentVersion
from app.retrieval.retriever import Retriever
from app.services.storage.r2_storage import R2Storage


class RagService:
    def __init__(self):
        self.retriever = Retriever()
        self.llm = GeminiClient()
        self.storage = R2Storage()

    def answer_query(self, query: str, top_k: int = 1) -> dict:
        expanded_queries = self.llm.generate_expand_query(query=query)
        all_results = []

        for q in expanded_queries:
            retrieved = self.retriever.retrieve(q, top_k=top_k)
            all_results.extend(retrieved)

        results = self._deduplicate_results(all_results)
        documents_map = self._load_documents_map(results)
        latest_version_map = self._load_latest_version_map(results)
        contexts = []
        sources = []
        results = self._load_related_version_chunks(results)
        for item in results:
            text = item.get("text")
            if text:
                contexts.append(text)

            metadata = item.get("metadata") or {}
            document_id = item.get("document_id")

            document_model = (
                documents_map.get(str(document_id)) if document_id else None
            )
            latest_version = (
                latest_version_map.get(str(document_id)) if document_id else None
            )
            file_path = metadata.get("file_path") or (
                latest_version.source_file_path if latest_version else None
            )
            mime_type = metadata.get("mime_type") or (
                document_model.mime_type if document_model else None
            )

            source = metadata.get("source") or file_path or document_id

            preview_url = None
            if file_path:
                try:
                    preview_url = self.storage.generate_presigned_url(file_path)
                except Exception:
                    preview_url = None

            sources.append(
                {
                    "title": item.get("title"),
                    "section_path": item.get("section_path"),
                    "source": source,
                    "file_path": file_path,
                    "preview_url": preview_url,
                    "document_id": str(document_id) if document_id else None,
                    "mime_type": mime_type,
                }
            )

        context = "\n\n".join(contexts)
        answer = self.llm.generate_response(query=query, context=context)

        return {"answer": answer, "sources": sources}

    def _deduplicate_results(self, results: list[dict]) -> list[dict]:
        seen = set()
        unique_results = []

        for item in results:
            chunk_id = item.get("chunk_id") or item.get("id")

            if not chunk_id:
                metadata = item.get("metadata") or {}
                chunk_id = (
                    metadata.get("chunk_id")
                    or metadata.get("point_id")
                    or f"{item.get('document_id')}::{item.get('section_path')}::{item.get('title')}"
                )

            if chunk_id in seen:
                continue

            seen.add(chunk_id)
            unique_results.append(item)

        return unique_results

    def _load_documents_map(self, results: list[dict]) -> dict[str, Document]:
        document_ids: list[UUID] = []
        for item in results:
            value = item.get("document_id")
            if not value:
                continue
            try:
                document_ids.append(UUID(str(value)))
            except (ValueError, TypeError):
                continue

        if not document_ids:
            return {}

        with SessionLocal() as db:
            docs = (
                db.query(Document).filter(Document.document_id.in_(document_ids)).all()
            )

        return {str(doc.document_id): doc for doc in docs}

    def _load_latest_version_map(
        self, results: list[dict]
    ) -> dict[str, DocumentVersion]:
        document_ids: list[UUID] = []
        for item in results:
            value = item.get("document_id")
            if not value:
                continue
            try:
                document_ids.append(UUID(str(value)))
            except (ValueError, TypeError):
                continue

        if not document_ids:
            return {}

        with SessionLocal() as db:
            versions = (
                db.query(DocumentVersion)
                .filter(DocumentVersion.document_id.in_(document_ids))
                .order_by(
                    DocumentVersion.document_id.asc(), DocumentVersion.version_no.desc()
                )
                .all()
            )

        latest_map: dict[str, DocumentVersion] = {}
        for version in versions:
            key = str(version.document_id)
            if key not in latest_map:
                latest_map[key] = version

        return latest_map

    def _load_related_version_chunks(self, results: list[dict]) -> list[dict]:
        expanded = list(results)
        seen_chunk_ids = {
            str(item.get("chunk_id")) for item in results if item.get("chunk_id")
        }

        added_chunks_log = []
        # print(f"Initial seen_chunk_ids: {results[0].get('metadata')}")
        with SessionLocal() as db:
            for item in results:
                metadata = item.get("metadata") or {}
                chunk_id = item.get("chunk_id")

                # Case 1: retrieve trúng chunk sửa đổi
                # => lấy chunk gốc từ previous_chunk_id
                if metadata.get("is_amendment") is True:
                    previous_chunk_id = metadata.get("previous_chunk_id")
                    if previous_chunk_id and previous_chunk_id not in seen_chunk_ids:
                        previous_chunk = (
                            db.query(ChunkModel)
                            .filter(ChunkModel.chunk_id == previous_chunk_id)
                            .first()
                        )

                        if previous_chunk:
                            expanded.append(self._chunk_model_to_result(previous_chunk))
                            seen_chunk_ids.add(str(previous_chunk.chunk_id))
                            added_chunks_log.append(
                                {
                                    "source_chunk_id": chunk_id,
                                    "added_chunk_id": previous_chunk.chunk_id,
                                    "relation": "amendment_to_original",
                                }
                            )
                # Case 2: retrieve trúng chunk thường
                # => tìm chunk sửa đổi có previous_chunk_id = chunk_id
                else:
                    point_id: str = str(item.get("id"))
                    if not point_id:
                        continue

                    amendment_chunks = (
                        db.query(ChunkModel)
                        .filter(
                            ChunkModel.metadata_json["previous_chunk_id"].astext
                            == point_id,
                        )
                        .all()
                    )
                    # Post-filter in Python to avoid type/coercion issues in SQL
                    filtered = [
                        c
                        for c in amendment_chunks
                        if (c.metadata_json or {}).get("is_amendment") is True
                    ]
                    print(
                        f"Found amendment chunks: {filtered} for chunk_id: {chunk_id}"
                    )
                    for amendment_chunk in filtered:
                        amendment_chunk_id = str(amendment_chunk.chunk_id)

                        if amendment_chunk_id not in seen_chunk_ids:
                            expanded.append(
                                self._chunk_model_to_result(amendment_chunk)
                            )
                            seen_chunk_ids.add(amendment_chunk_id)
                            added_chunks_log.append(
                                {
                                    "source_chunk_id": point_id,
                                    "added_chunk_id": amendment_chunk_id,
                                    "relation": "original_to_amendment",
                                }
                            )
        print(f"Expanded results with related version chunks: {added_chunks_log}")
        return expanded

    def _chunk_model_to_result(self, chunk: ChunkModel) -> dict:
        metadata = chunk.metadata_json or {}

        title = (
            metadata.get("previous_chunk_title")
            or metadata.get("amendment_title")
            or metadata.get("doc_title")
            or None
        )

        return {
            "chunk_id": str(chunk.chunk_id),
            "document_id": str(chunk.document_id),
            "title": title,
            "section_path": chunk.section_path,
            "text": chunk.chunk_text,
            "metadata": metadata,
        }
