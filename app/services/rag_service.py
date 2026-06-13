import re
import unicodedata
from uuid import UUID

from rapidfuzz import fuzz

from app.core.database import SessionLocal
from app.llm.gemini_client import GeminiClient
from app.llm.ollama_client import OllamaClient
from app.models.document import Document
from app.models.chunk import Chunk as ChunkModel
from app.models.document_version import DocumentVersion
from app.pipeline.query_pipeline import QueryPipeline
from app.retrieval.retriever import Retriever
from app.services.storage.r2_storage import R2Storage


class RagService:
    def __init__(self):
        self.retriever = Retriever()
        # self.llm = GeminiClient()
        self.llm = OllamaClient()
        self.storage = R2Storage()
        self.query_pipeline = QueryPipeline(
            retriever=self.retriever,
            llm=self.llm,
            storage=self.storage,
            rag_helpers=self,
        )

    def answer_query(self, query: str, top_k: int = 1) -> dict:
        return self.query_pipeline.run(query=query, top_k=top_k)

    def stream_answer_query(self, query: str, top_k: int = 1):
        yield from self.query_pipeline.stream(query=query, top_k=top_k)

    def _normalize_expanded_queries(
        self, query: str, expanded_queries: list[str] | None
    ) -> list[str]:
        queries = [query]
        queries.extend(expanded_queries or [])

        normalized_queries = []
        seen = set()
        for item in queries:
            value = str(item or "").strip()
            if not value:
                continue

            key = self._fold_text(value)
            if key in seen:
                continue

            seen.add(key)
            normalized_queries.append(value)

        return normalized_queries or [query]

    def _rerank_results(
        self,
        query: str,
        expanded_queries: list[str],
        results: list[dict],
        top_k: int,
    ) -> list[dict]:
        grouped = {}

        for item in results:
            key = self._result_key(item)
            score = self._safe_float(item.get("score"))

            if key not in grouped:
                grouped[key] = {
                    "item": dict(item),
                    "max_score": score,
                    "matched_queries": set(),
                    "matched_original_query": False,
                    "best_query_index": item.get("retrieval_query_index", 999),
                }

            group = grouped[key]
            if score > group["max_score"]:
                group["item"] = dict(item)
                group["max_score"] = score

            query_index = item.get("retrieval_query_index")
            retrieval_query = item.get("retrieval_query")
            if retrieval_query:
                group["matched_queries"].add(self._fold_text(str(retrieval_query)))

            if query_index == 0:
                group["matched_original_query"] = True

            if isinstance(query_index, int):
                group["best_query_index"] = min(group["best_query_index"], query_index)

        reranked = []
        query_count = max(len(expanded_queries), 1)
        for group in grouped.values():
            item = group["item"]
            vector_score = group["max_score"]
            lexical_score = self._lexical_score(query=query, item=item)
            metadata_bonus = self._metadata_bonus(query=query, item=item)
            multi_query_bonus = min(
                len(group["matched_queries"]) / query_count,
                1.0,
            )
            original_query_bonus = 1.0 if group["matched_original_query"] else 0.0

            rerank_score = (
                0.75 * vector_score
                + 0.12 * lexical_score
                + 0.06 * multi_query_bonus
                + 0.04 * original_query_bonus
                + metadata_bonus
            )

            item["score"] = vector_score
            item["rerank_score"] = rerank_score
            item["lexical_score"] = lexical_score
            item["matched_query_count"] = len(group["matched_queries"])
            reranked.append(item)

        reranked.sort(
            key=lambda item: (
                item.get("rerank_score", 0.0),
                item.get("score", 0.0),
            ),
            reverse=True,
        )
        return reranked[:top_k]

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

    def _result_key(self, item: dict) -> str:
        chunk_id = item.get("chunk_id") or item.get("id")

        if not chunk_id:
            metadata = item.get("metadata") or {}
            chunk_id = (
                metadata.get("chunk_id")
                or metadata.get("point_id")
                or f"{item.get('document_id')}::{item.get('section_path')}::{item.get('title')}"
            )

        return str(chunk_id)

    def _lexical_score(self, query: str, item: dict) -> float:
        title = item.get("title") or ""
        section_path = item.get("section_path") or ""
        text = item.get("text") or ""
        metadata = item.get("metadata") or {}

        haystack = "\n".join(
            [
                str(title),
                str(section_path),
                str(metadata.get("doc_title") or ""),
                str(metadata.get("article_title") or ""),
                str(metadata.get("article_number") or ""),
                str(text[:4000]),
            ]
        )

        query_folded = self._fold_text(query)
        haystack_folded = self._fold_text(haystack)
        if not query_folded or not haystack_folded:
            return 0.0

        fuzzy_score = fuzz.token_set_ratio(query_folded, haystack_folded) / 100
        phrase_bonus = self._legal_phrase_bonus(query_folded, haystack_folded)
        return min(fuzzy_score + phrase_bonus, 1.0)

    def _legal_phrase_bonus(self, query: str, haystack: str) -> float:
        patterns = [
            r"\bdieu\s+[a-z0-9ivxlcdm]+\b",
            r"\bkhoan\s+[a-z0-9ivxlcdm]+\b",
            r"\bdiem\s+[a-z0-9ivxlcdm]+\b",
            r"\bchuong\s+[a-z0-9ivxlcdm]+\b",
            r"\bmuc\s+[a-z0-9ivxlcdm]+\b",
            r"\bphu luc\s+[a-z0-9ivxlcdm]+\b",
        ]

        bonus = 0.0
        for pattern in patterns:
            for phrase in set(re.findall(pattern, query)):
                if phrase in haystack:
                    bonus += 0.04

        numeric_terms = set(re.findall(r"\b\d{2,4}\b", query))
        for term in numeric_terms:
            if term in haystack:
                bonus += 0.02

        return min(bonus, 0.15)

    def _metadata_bonus(self, query: str, item: dict) -> float:
        metadata = item.get("metadata") or {}
        query_folded = self._fold_text(query)
        bonus = 0.0

        if metadata.get("is_current") is True:
            bonus += 0.03

        status = self._fold_text(str(metadata.get("status") or ""))
        if status in {"active", "processed"}:
            bonus += 0.02
        elif status in {"inactive", "deleted", "removed", "archived"}:
            bonus -= 0.04

        is_amendment = metadata.get("is_amendment") is True
        amendment_intent = any(
            phrase in query_folded
            for phrase in (
                "sua doi",
                "bo sung",
                "bai bo",
                "thay doi",
                "van ban moi",
                "hien hanh",
            )
        )
        if is_amendment and amendment_intent:
            bonus += 0.03

        article_number = metadata.get("article_number") or metadata.get(
            "target_article_number"
        )
        if article_number and self._fold_text(str(article_number)) in query_folded:
            bonus += 0.02

        return bonus

    def _fold_text(self, text: str) -> str:
        normalized = unicodedata.normalize("NFD", str(text).lower())
        without_marks = "".join(
            char for char in normalized if unicodedata.category(char) != "Mn"
        )
        without_marks = without_marks.replace("đ", "d")
        return re.sub(r"\s+", " ", without_marks).strip()

    def _safe_float(self, value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

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

        with SessionLocal() as db:
            for item in results:
                metadata = item.get("metadata") or {}

                # Case 1 + 2: mở rộng chunk theo quan hệ version/amendment
                version_logs = self._load_version_relation_chunks(
                    db=db,
                    item=item,
                    expanded=expanded,
                    seen_chunk_ids=seen_chunk_ids,
                )
                added_chunks_log.extend(version_logs)

                # Case 3: nếu chunk top có nhắc "theo Phụ lục ..."
                # => kéo thêm chunk phụ lục tương ứng vào context
                appendix_logs = self._load_appendix_reference_chunks(
                    db=db,
                    item=item,
                    expanded=expanded,
                    seen_chunk_ids=seen_chunk_ids,
                )
                added_chunks_log.extend(appendix_logs)

        print(f"Expanded results with related chunks: {added_chunks_log}")
        return expanded

    def _load_version_relation_chunks(
        self,
        db,
        item: dict,
        expanded: list[dict],
        seen_chunk_ids: set[str],
    ) -> list[dict]:
        metadata = item.get("metadata") or {}
        chunk_id = item.get("chunk_id")
        added_logs = []

        # Case 1: retrieve trúng chunk sửa đổi
        # => lấy chunk gốc từ previous_chunk_id
        if metadata.get("is_amendment") is True:
            previous_chunk_id = metadata.get("previous_chunk_id")
            previous_chunk_id_str = (
                str(previous_chunk_id) if previous_chunk_id else None
            )

            if previous_chunk_id_str and previous_chunk_id_str not in seen_chunk_ids:
                previous_chunk = (
                    db.query(ChunkModel)
                    .filter(ChunkModel.chunk_id == previous_chunk_id)
                    .first()
                )

                if previous_chunk:
                    log_item = self._append_related_chunk(
                        expanded=expanded,
                        seen_chunk_ids=seen_chunk_ids,
                        chunk=previous_chunk,
                        relation="amendment_to_original",
                        source_chunk_id=chunk_id,
                    )
                    if log_item:
                        added_logs.append(log_item)

            return added_logs

        # Case 2: retrieve trúng chunk thường
        # => tìm chunk sửa đổi có previous_chunk_id = Qdrant point id
        # Lưu ý: hệ của bạn đang dùng item["id"] làm point_id, giữ nguyên.
        point_id: str = str(item.get("id"))
        if not point_id or point_id == "None":
            return added_logs

        amendment_chunks = (
            db.query(ChunkModel)
            .filter(ChunkModel.metadata_json["previous_chunk_id"].astext == point_id)
            .all()
        )

        filtered = [
            chunk
            for chunk in amendment_chunks
            if (chunk.metadata_json or {}).get("is_amendment") is True
        ]

        for amendment_chunk in filtered:
            log_item = self._append_related_chunk(
                expanded=expanded,
                seen_chunk_ids=seen_chunk_ids,
                chunk=amendment_chunk,
                relation="original_to_amendment",
                source_chunk_id=point_id,
            )
            if log_item:
                added_logs.append(log_item)

        return added_logs

    def _load_appendix_reference_chunks(
        self,
        db,
        item: dict,
        expanded: list[dict],
        seen_chunk_ids: set[str],
    ) -> list[dict]:
        metadata = item.get("metadata") or {}
        document_id = item.get("document_id") or metadata.get("document_id")
        source_chunk_id = item.get("chunk_id")

        if not document_id:
            return []

        text_for_ref = self._get_item_text_for_reference_detection(item)
        appendix_refs = self._extract_appendix_refs(text_for_ref)

        if not appendix_refs:
            return []

        added_logs = []

        for appendix_ref in appendix_refs:
            appendix_chunks = self._query_appendix_chunks(
                db=db,
                document_id=document_id,
                appendix_ref=appendix_ref,
                limit=5,
            )

            for appendix_chunk in appendix_chunks:
                log_item = self._append_related_chunk(
                    expanded=expanded,
                    seen_chunk_ids=seen_chunk_ids,
                    chunk=appendix_chunk,
                    relation="referenced_appendix",
                    source_chunk_id=source_chunk_id,
                    extra_log={"appendix": f"Phụ lục {appendix_ref}"},
                )
                if log_item:
                    added_logs.append(log_item)

        return added_logs

    def _query_appendix_chunks(
        self,
        db,
        document_id,
        appendix_ref: str,
        limit: int = 5,
    ) -> list[ChunkModel]:
        # Nếu sau này ingest có metadata appendix_number thì nên ưu tiên field này.
        by_appendix_number = (
            db.query(ChunkModel)
            .filter(ChunkModel.document_id == document_id)
            .filter(ChunkModel.metadata_json["chunk_kind"].astext == "appendix")
            .filter(ChunkModel.metadata_json["appendix_number"].astext == appendix_ref)
            .limit(limit)
            .all()
        )
        if by_appendix_number:
            return by_appendix_number

        section_patterns = self._build_appendix_section_patterns(appendix_ref)
        chunks_by_id: dict[str, ChunkModel] = {}

        base_query = (
            db.query(ChunkModel)
            .filter(ChunkModel.document_id == document_id)
            .filter(ChunkModel.metadata_json["chunk_kind"].astext == "appendix")
        )

        for pattern in section_patterns:
            chunks = (
                base_query.filter(
                    ChunkModel.metadata_json["section_path"].astext.ilike(pattern)
                )
                .limit(limit)
                .all()
            )

            for chunk in chunks:
                chunks_by_id[str(chunk.chunk_id)] = chunk

        return list(chunks_by_id.values())[:limit]

    def _build_appendix_section_patterns(self, appendix_ref: str) -> list[str]:
        digit_ref = self._roman_to_digit(appendix_ref)
        raw_refs = [appendix_ref]
        if digit_ref:
            raw_refs.append(digit_ref)

        patterns = []
        for ref in raw_refs:
            patterns.extend(
                [
                    f"%Phụ lục {ref}%",
                    f"%PHỤ LỤC {ref}%",
                    f"%phụ lục {ref}%",
                    f"%Phu luc {ref}%",
                    f"%PHU LUC {ref}%",
                    f"%phu luc {ref}%",
                ]
            )

        return list(dict.fromkeys(patterns))

    def _get_item_text_for_reference_detection(self, item: dict) -> str:
        metadata = item.get("metadata") or {}

        return self._normalize_ref_text(
            " ".join(
                [
                    str(metadata.get("section_path") or ""),
                    str(metadata.get("title") or ""),
                    str(metadata.get("doc_title") or ""),
                    str(metadata.get("article_title") or ""),
                    str(item.get("title") or ""),
                    str(item.get("section_path") or ""),
                    str(item.get("text") or ""),
                    str(item.get("content") or ""),
                ]
            )
        )

    def _extract_appendix_refs(self, text: str) -> list[str]:
        pattern = re.compile(
            r"(?:phụ\s*lục|phu\s*luc)\s+([ivxlcdm]+|\d+)",
            flags=re.IGNORECASE,
        )

        refs = []
        for match in pattern.finditer(text or ""):
            raw_ref = match.group(1).upper().strip()
            refs.append(self._digit_to_roman(raw_ref) or raw_ref)

        return list(dict.fromkeys(refs))

    def _digit_to_roman(self, value: str) -> str | None:
        mapping = {
            "1": "I",
            "2": "II",
            "3": "III",
            "4": "IV",
            "5": "V",
            "6": "VI",
            "7": "VII",
            "8": "VIII",
            "9": "IX",
            "10": "X",
        }
        return mapping.get(str(value).strip())

    def _roman_to_digit(self, value: str) -> str | None:
        mapping = {
            "I": "1",
            "II": "2",
            "III": "3",
            "IV": "4",
            "V": "5",
            "VI": "6",
            "VII": "7",
            "VIII": "8",
            "IX": "9",
            "X": "10",
        }
        return mapping.get(str(value).upper().strip())

    def _normalize_ref_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip()

    def _append_related_chunk(
        self,
        expanded: list[dict],
        seen_chunk_ids: set[str],
        chunk: ChunkModel,
        relation: str,
        source_chunk_id: str | None = None,
        extra_log: dict | None = None,
    ) -> dict | None:
        chunk_id = str(chunk.chunk_id)

        if chunk_id in seen_chunk_ids:
            return None

        result = self._chunk_model_to_result(chunk)
        result["relation"] = relation
        result["source_role"] = "supporting"

        expanded.append(result)
        seen_chunk_ids.add(chunk_id)

        log_item = {
            "source_chunk_id": source_chunk_id,
            "added_chunk_id": chunk_id,
            "relation": relation,
        }

        if extra_log:
            log_item.update(extra_log)

        return log_item

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
