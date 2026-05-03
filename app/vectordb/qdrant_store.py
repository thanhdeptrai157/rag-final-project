from __future__ import annotations

from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct


class QdrantStore:
    def __init__(
        self,
        collection_name: str,
        url: str,
        api_key: str,
    ):
        self.collection_name = collection_name
        self.client = QdrantClient(
            url=url,
            api_key=api_key,
        )

    def collection_exists(self) -> bool:
        """Kiểm tra collection có tồn tại không."""
        try:
            self.client.get_collection(self.collection_name)
            return True
        except Exception:
            return False

    def ensure_collection_exists(self, vector_size: int = 1024) -> None:
        """Tạo collection nếu chưa tồn tại."""
        if not self.collection_exists():
            print(
                f"[QDRANT] Creating collection: {self.collection_name} (vector_size={vector_size})"
            )
            self.recreate_collection(vector_size=vector_size)
        else:
            print(f"[QDRANT] Collection already exists: {self.collection_name}")

    def recreate_collection(self, vector_size: int) -> None:
        self.client.recreate_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

    def upsert_chunks(
        self,
        ids: List[str],
        vectors: List[List[float]],
        payloads: List[Dict[str, Any]],
        batch_size: int = 100,
    ) -> None:
        """Upsert chunks với batch để tránh timeout.

        Args:
            ids: List ID
            vectors: List embedding vectors
            payloads: List payload metadata
            batch_size: Số lượng point mỗi batch (default 100)
        """
        total = len(ids)
        for i in range(0, total, batch_size):
            batch_end = min(i + batch_size, total)
            batch_ids = ids[i:batch_end]
            batch_vectors = vectors[i:batch_end]
            batch_payloads = payloads[i:batch_end]

            points = [
                PointStruct(id=idx, vector=vector, payload=payload)
                for idx, vector, payload in zip(
                    batch_ids, batch_vectors, batch_payloads
                )
            ]

            print(
                f"[QDRANT] Upserting batch {i//batch_size + 1}: {len(points)} points ({batch_end}/{total})"
            )
            self.client.upsert(collection_name=self.collection_name, points=points)

    def search(self, query_vector: List[float], top_k: int = 5):
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        return response.points
