from __future__ import annotations

from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Filter, FieldCondition, MatchValue


class QdrantStore:
    def __init__(
        self,
        collection_name: str,
        url: str,
        api_key: str | None = None,
        timeout: int = 30,
    ):
        self.collection_name = collection_name
        self.client = QdrantClient(
            url=url,
            api_key=api_key or None,
            timeout=timeout,
        )

    def collection_exists(self) -> bool:
        try:
            self.client.get_collection(self.collection_name)
            return True
        except Exception:
            return False

    def ensure_collection_exists(self, vector_size: int = 1024) -> None:
        if not self.collection_exists():
            print(
                f"[QDRANT] Creating collection: {self.collection_name} "
                f"(vector_size={vector_size})"
            )
            self.recreate_collection(vector_size=vector_size)
        else:
            print(f"[QDRANT] Collection already exists: {self.collection_name}")

        self.ensure_payload_indexes()

    def recreate_collection(self, vector_size: int) -> None:
        self.client.recreate_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            ),
        )

        self.ensure_payload_indexes()

    def ensure_payload_indexes(self) -> None:
        indexes = {
            "document_id": models.PayloadSchemaType.KEYWORD,
            "version_id": models.PayloadSchemaType.KEYWORD,
            "chunk_id": models.PayloadSchemaType.KEYWORD,
            "chunk_type": models.PayloadSchemaType.KEYWORD,
            "metadata.document_id": models.PayloadSchemaType.KEYWORD,
            "metadata.document_version_id": models.PayloadSchemaType.KEYWORD,
            "metadata.status": models.PayloadSchemaType.KEYWORD,
            "metadata.is_current": models.PayloadSchemaType.BOOL,
        }

        for field_name, field_schema in indexes.items():
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=field_schema,
                    wait=True,
                )
                print(f"[QDRANT] Created payload index: {field_name}")
            except Exception as e:
                msg = str(e).lower()
                if (
                    "already exists" in msg
                    or "already has" in msg
                    or "index already exists" in msg
                ):
                    print(f"[QDRANT] Payload index already exists: {field_name}")
                    continue

                print(
                    f"[QDRANT] Failed to create payload index "
                    f"{field_name}: {type(e).__name__}: {e}"
                )
                raise

    def upsert_chunks(
        self,
        ids: list[str],
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
        batch_size: int = 100,
    ) -> None:
        if not (len(ids) == len(vectors) == len(payloads)):
            raise ValueError(
                "ids, vectors, payloads must have the same length: "
                f"{len(ids)}, {len(vectors)}, {len(payloads)}"
            )

        total = len(ids)

        for i in range(0, total, batch_size):
            batch_end = min(i + batch_size, total)

            points = [
                models.PointStruct(
                    id=str(point_id),
                    vector=vector,
                    payload=payload,
                )
                for point_id, vector, payload in zip(
                    ids[i:batch_end],
                    vectors[i:batch_end],
                    payloads[i:batch_end],
                )
            ]

            print(
                f"[QDRANT] Upserting batch {i // batch_size + 1}: "
                f"{len(points)} points ({batch_end}/{total})"
            )

            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )

    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        filters: dict | None = None,
    ):
        query_filter = None

        if filters:
            conditions = []

            for key, value in filters.items():
                conditions.append(
                    FieldCondition(
                        key=f"metadata.{key}",
                        match=MatchValue(value=value),
                    )
                )

            query_filter = Filter(must=conditions)

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
            query_filter=query_filter,
        )

        return response.points

    def _document_filter(self, document_id: str) -> models.Filter:
        return models.Filter(
            must=[
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=str(document_id)),
                )
            ]
        )

    def _version_filter(self, version_id: str) -> models.Filter:
        return models.Filter(
            should=[
                models.FieldCondition(
                    key="version_id",
                    match=models.MatchValue(value=str(version_id)),
                ),
                models.FieldCondition(
                    key="metadata.document_version_id",
                    match=models.MatchValue(value=str(version_id)),
                ),
            ]
        )

    def count_by_document_id(self, document_id: str) -> int:
        result = self.client.count(
            collection_name=self.collection_name,
            count_filter=self._document_filter(document_id),
            exact=True,
        )
        return result.count

    def count_by_version_id(self, version_id: str) -> int:
        result = self.client.count(
            collection_name=self.collection_name,
            count_filter=self._version_filter(version_id),
            exact=True,
        )
        return result.count

    def delete_by_document_id(self, document_id: str, wait: bool = True) -> None:
        doc_id = str(document_id)
        qfilter = self._document_filter(doc_id)

        try:
            self.ensure_payload_indexes()

            before_count = self.count_by_document_id(doc_id)
            print(f"[QDRANT] Found {before_count} points for document_id={doc_id}")

            if before_count == 0:
                print(f"[QDRANT] Nothing to delete for document_id={doc_id}")
                return

            result = self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(filter=qfilter),
                wait=wait,
            )

            print(f"[QDRANT] Delete result for document_id={doc_id}: {result}")

            after_count = self.count_by_document_id(doc_id)
            print(f"[QDRANT] Remaining points for document_id={doc_id}: {after_count}")

        except Exception as e:
            print(
                f"[QDRANT] Delete failed document_id={doc_id}: "
                f"{type(e).__name__}: {e}"
            )
            raise

    def delete_by_version_id(self, version_id: str, wait: bool = True) -> None:
        ver_id = str(version_id)
        qfilter = self._version_filter(ver_id)

        try:
            self.ensure_payload_indexes()

            before_count = self.count_by_version_id(ver_id)
            print(f"[QDRANT] Found {before_count} points for version_id={ver_id}")

            if before_count == 0:
                print(f"[QDRANT] Nothing to delete for version_id={ver_id}")
                return

            result = self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(filter=qfilter),
                wait=wait,
            )

            print(f"[QDRANT] Delete result for version_id={ver_id}: {result}")

            after_count = self.count_by_version_id(ver_id)
            print(f"[QDRANT] Remaining points for version_id={ver_id}: {after_count}")

        except Exception as e:
            print(
                f"[QDRANT] Delete failed version_id={ver_id}: "
                f"{type(e).__name__}: {e}"
            )
            raise
