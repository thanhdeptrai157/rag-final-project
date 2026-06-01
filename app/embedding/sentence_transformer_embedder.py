from __future__ import annotations

import os
from functools import lru_cache
from typing import List

from sentence_transformers import SentenceTransformer


class Embedder:
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self.model = SentenceTransformer(
            model_name,
            device="cpu",
            cache_folder=os.getenv("HF_HOME", "/app/.cache/huggingface"),
        )

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=4,
        )
        return embeddings.tolist()

    def embed_query(self, query: str) -> List[float]:
        embedding = self.model.encode(
            [query],
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=1,
        )
        return embedding[0].tolist()


@lru_cache(maxsize=1)
def get_embedder(model_name: str = "BAAI/bge-m3") -> Embedder:
    return Embedder(model_name=model_name)