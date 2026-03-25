from __future__ import annotations


from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct


class QdrantStore:
    def __init__(self, collection_name: str, host: str = "localhost", port: int = 6333):
        self.collection_name = collection_name
        self.client = QdrantClient(host=host, port=port)

    def recreate_collection(self, vector_size: int) -> None:
        self.client.recreate_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

    def upsert_chunks(
        self, ids: List[str], vectors: List[List[float]], payloads: List[Dict[str, Any]]
    ) -> None:
        points = [
            PointStruct(id=idx, vector=vector, payload=payload)
            for idx, vector, payload in zip(ids, vectors, payloads)
        ]
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
