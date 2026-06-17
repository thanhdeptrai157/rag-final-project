from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from sentence_transformers import CrossEncoder

from app.core.config import Config


_load_error: Exception | None = None


class CrossEncoderReranker:
    def __init__(
        self,
        model_name: str = Config.RERANKER_MODEL,
        max_length: int = Config.RERANKER_MAX_LENGTH,
    ) -> None:
        self.model_name = model_name
        self.cache_dir = Config.RERANKER_CACHE_DIR
        self.model = self._load_model(model_name=model_name, max_length=max_length)

    def _load_model(self, *, model_name: str, max_length: int) -> CrossEncoder:
        os.makedirs(self.cache_dir, exist_ok=True)
        os.environ.setdefault("HF_HOME", self.cache_dir)
        os.environ.setdefault("TRANSFORMERS_CACHE", self.cache_dir)

        device = os.getenv("RERANKER_DEVICE", "cpu")
        shared_kwargs = {
            "max_length": max_length,
            "device": device,
        }

        try:
            return CrossEncoder(
                model_name,
                **shared_kwargs,
                tokenizer_args={
                    "cache_dir": self.cache_dir,
                    "local_files_only": Config.RERANKER_LOCAL_FILES_ONLY,
                },
                automodel_args={
                    "cache_dir": self.cache_dir,
                    "local_files_only": Config.RERANKER_LOCAL_FILES_ONLY,
                },
                config_args={
                    "cache_dir": self.cache_dir,
                    "local_files_only": Config.RERANKER_LOCAL_FILES_ONLY,
                },
            )
        except TypeError:
            return CrossEncoder(model_name, **shared_kwargs)

    def rerank(
        self,
        *,
        query: str,
        results: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        unique_results = self._deduplicate(results)
        if not unique_results:
            return []

        unique_results = self._limit_candidates(unique_results)

        pairs = [
            (query, self._build_candidate_text(item))
            for item in unique_results
        ]
        scores = self.model.predict(
            pairs,
            batch_size=Config.RERANKER_BATCH_SIZE,
            show_progress_bar=False,
        )

        reranked = []
        for item, score in zip(unique_results, scores):
            reranked_item = dict(item)
            cross_encoder_score = float(score)
            reranked_item["cross_encoder_score"] = cross_encoder_score
            reranked_item["rerank_score"] = cross_encoder_score
            reranked.append(reranked_item)

        reranked.sort(
            key=lambda item: (
                item.get("rerank_score", float("-inf")),
                item.get("score", float("-inf")),
            ),
            reverse=True,
        )
        return reranked[:top_k]

    def _build_candidate_text(self, item: dict[str, Any]) -> str:
        metadata = item.get("metadata") or {}
        parts = [
            item.get("title"),
            item.get("section_path"),
            metadata.get("doc_title"),
            metadata.get("article_title"),
            metadata.get("article_number"),
            item.get("text"),
        ]
        text = "\n".join(str(part).strip() for part in parts if part)
        return text[:8000]

    def _deduplicate(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}

        for item in results:
            key = self._result_key(item)
            score = self._safe_float(item.get("score"))

            if key not in grouped:
                grouped[key] = {
                    "item": dict(item),
                    "max_score": score,
                    "matched_query_count": 0,
                }

            group = grouped[key]
            group["matched_query_count"] += 1
            if score > group["max_score"]:
                group["item"] = dict(item)
                group["max_score"] = score

        unique_results = []
        for group in grouped.values():
            item = group["item"]
            item["score"] = group["max_score"]
            item["matched_query_count"] = group["matched_query_count"]
            unique_results.append(item)

        return unique_results

    def _limit_candidates(
        self,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        limit = max(Config.RERANKER_MAX_CANDIDATES, 1)
        results.sort(
            key=lambda item: self._safe_float(item.get("score")),
            reverse=True,
        )
        return results[:limit]

    def _result_key(self, item: dict[str, Any]) -> str:
        chunk_id = item.get("chunk_id") or item.get("id")

        if not chunk_id:
            metadata = item.get("metadata") or {}
            chunk_id = (
                metadata.get("chunk_id")
                or metadata.get("point_id")
                or f"{item.get('document_id')}::{item.get('section_path')}::{item.get('title')}"
            )

        return str(chunk_id)

    def _safe_float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0


@lru_cache(maxsize=1)
def get_cross_encoder_reranker(
    model_name: str = Config.RERANKER_MODEL,
) -> CrossEncoderReranker:
    global _load_error

    if _load_error is not None:
        raise RuntimeError(
            "Cross-encoder reranker is unavailable because model loading "
            f"failed earlier: {_load_error}"
        ) from _load_error

    try:
        return CrossEncoderReranker(model_name=model_name)
    except Exception as exc:
        _load_error = exc
        raise
