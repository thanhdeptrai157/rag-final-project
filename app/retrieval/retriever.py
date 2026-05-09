from __future__ import annotations

from typing import List, Dict, Any

from app.embedding.sentence_transformer_embedder import Embbedder
from app.vectordb.qdrant_store import QdrantStore
from app.core.config import Config


class Retriever:
    def __init__(self):
        self.embedder = Embbedder(model_name="BAAI/bge-m3")
        self.store = QdrantStore(
            collection_name=Config.QDRANT_COLLECTION,
            url=Config.QDRANT_HOST_URL,
            api_key=Config.QDRANT_API_KEY,
        )

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        query_vector = self.embedder.embed_query(query)
        results = self.store.search(query_vector=query_vector, top_k=top_k)

        output = []
        for r in results:
            payload = r.payload or {}
            output.append(
                {
                    "score": r.score,
                    "id": r.id,
                    "chunk_id": payload.get("chunk_id"),
                    "document_id": payload.get("document_id"),
                    "title": payload.get("title"),
                    "section_path": payload.get("section_path"),
                    "text": payload.get("text"),
                    "metadata": payload.get("metadata", {}),
                }
            )
        return output
