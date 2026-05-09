from uuid import UUID

from app.core.database import SessionLocal
from app.llm.gemini_client import GeminiClient
from app.models.document import Document
from app.retrieval.retriever import Retriever
from app.services.storage.r2_storage import R2Storage


class RagService:
    def __init__(self):
        self.retriever = Retriever()
        self.llm = GeminiClient()
        self.storage = R2Storage()

    def answer_query(self, query: str, top_k: int = 1) -> dict:
        results = self.retriever.retrieve(query, top_k=top_k)
        documents_map = self._load_documents_map(results)
        contexts = []
        sources = []
        print("Retrieved contexts:", results)
        for item in results:
            text = item.get("text")
            if text:
                contexts.append(text)

            metadata = item.get("metadata") or {}
            document_id = item.get("document_id") or metadata.get("document_id")

            document_model = (
                documents_map.get(str(document_id)) if document_id else None
            )
            file_path = metadata.get("file_path") or (
                document_model.file_path if document_model else None
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
