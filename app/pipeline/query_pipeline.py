from collections.abc import Iterator

from app.routing.query_router import QueryRouter
from app.routing.query_route import QueryStrategy


class QueryPipeline:
    def __init__(self, retriever, llm, storage, rag_helpers):
        self.router = QueryRouter(llm=llm)
        self.retriever = retriever
        self.llm = llm
        self.storage = storage
        self.rag = rag_helpers

    def run(self, query: str, top_k: int = 3) -> dict:
        final_result = None
        for event in self.stream(query=query, top_k=top_k):
            if event.get("type") == "done":
                final_result = event

        return {
            "answer": (final_result or {}).get("answer") or "",
            "sources": (final_result or {}).get("sources") or [],
            "route": (final_result or {}).get("route"),
        }

    def stream(self, query: str, top_k: int = 3) -> Iterator[dict]:
        yield self._status(
            stage="routing",
            status="started",
            message="Đang định tuyến truy vấn",
        )
        route = self.router.route(query=query, top_k=top_k)
        yield self._status(
            stage="routing",
            status="completed",
            message="Đã định tuyến truy vấn",
            route=route.strategy.value,
            filters=route.filters,
            use_query_expansion=route.use_query_expansion,
            candidate_top_k=route.candidate_top_k,
        )

        if route.strategy == QueryStrategy.LOW_CONTEXT_OR_INVALID:
            yield self._status(
                stage="expand_query",
                status="skipped",
                message="Bỏ qua mở rộng truy vấn",
                queries=[query],
            )
            yield self._status(
                stage="retrieve",
                status="skipped",
                message="Bỏ qua truy xuất tài liệu",
                retrieved_count=0,
            )
            yield self._status(
                stage="llm",
                status="started",
                message="Đang trả lời",
            )
            answer_parts = []
            for chunk in self._stream_low_context_response(query=query):
                for char in chunk:
                    answer_parts.append(char)
                    yield {
                        "type": "answer_delta",
                        "stage": "llm",
                        "delta": char,
                    }
            answer = "".join(answer_parts)
            yield self._status(
                stage="llm",
                status="completed",
                message="Đã hoàn tất trả lời",
            )
            yield {
                "type": "done",
                "answer": answer,
                "sources": [],
                "route": route.strategy.value,
            }
            return

        yield self._status(
            stage="expand_query",
            status="started",
            message="Đang mở rộng truy vấn",
        )
        expanded_queries = self._build_queries(query, route)
        yield self._status(
            stage="expand_query",
            status="completed",
            message="Đã mở rộng truy vấn",
            queries=expanded_queries,
            query_count=len(expanded_queries),
        )

        yield self._status(
            stage="retrieve",
            status="started",
            message="Đang truy xuất tài liệu",
            query_count=len(expanded_queries),
            candidate_top_k=route.candidate_top_k,
        )
        all_results = self._retrieve_all(expanded_queries, route)
        yield self._status(
            stage="retrieve",
            status="retrieved",
            message="Đã truy xuất ứng viên",
            retrieved_count=len(all_results),
        )

        results = self.rag._rerank_results(
            query=query,
            expanded_queries=expanded_queries,
            results=all_results,
            top_k=route.top_k,
        )
        yield self._status(
            stage="retrieve",
            status="reranked",
            message="Đã xếp hạng lại nguồn",
            selected_count=len(results),
        )

        if route.use_related_chunk_expansion:
            results = self.rag._load_related_version_chunks(results)
            yield self._status(
                stage="retrieve",
                status="expanded",
                message="Đã bổ sung chunk liên quan",
                selected_count=len(results),
            )

        sources, context = self._build_sources_and_context(results)
        yield self._status(
            stage="retrieve",
            status="completed",
            message="Đã chuẩn bị context",
            source_count=len(sources),
        )

        answer_parts = []
        yield self._status(
            stage="llm",
            status="started",
            message="LLM đang trả lời",
        )
        for chunk in self._stream_llm_response(query=query, context=context):
            for char in chunk:
                answer_parts.append(char)
                yield {
                    "type": "answer_delta",
                    "stage": "llm",
                    "delta": char,
                }

        answer = "".join(answer_parts)
        yield self._status(
            stage="llm",
            status="completed",
            message="Đã hoàn tất trả lời",
        )
        yield {
            "type": "done",
            "answer": answer,
            "sources": sources,
            "route": route.strategy.value,
        }

    def _stream_llm_response(self, query: str, context: str) -> Iterator[str]:
        if hasattr(self.llm, "stream_generate_response"):
            yield from self.llm.stream_generate_response(query=query, context=context)
            return

        yield self.llm.generate_response(query=query, context=context)

    def _stream_low_context_response(self, query: str) -> Iterator[str]:
        fallback = "Bạn vui lòng hỏi rõ hơn hoặc cung cấp thêm ngữ cảnh."

        try:
            if hasattr(self.llm, "stream_low_context_response"):
                yielded = False
                for chunk in self.llm.stream_low_context_response(query=query):
                    yielded = True
                    yield chunk
                if yielded:
                    return

            if hasattr(self.llm, "generate_low_context_response"):
                answer = self.llm.generate_low_context_response(query=query)
                if answer:
                    yield answer
                    return

        except Exception as exc:
            print(
                "[LOW_CONTEXT] Failed to generate low-context response, "
                f"falling back: {type(exc).__name__}: {exc}"
            )

        yield fallback

    def _status(self, stage: str, status: str, message: str, **data) -> dict:
        return {
            "type": "status",
            "stage": stage,
            "status": status,
            "message": message,
            **data,
        }

    def _build_queries(self, query: str, route) -> list[str]:
        if not route.use_query_expansion:
            return [query]

        expanded = self.llm.generate_expand_query(query=query)
        return self.rag._normalize_expanded_queries(
            query=query,
            expanded_queries=expanded,
        )

    def _retrieve_all(self, queries: list[str], route) -> list[dict]:
        all_results = []

        for query_index, q in enumerate(queries):
            retrieved = self.retriever.retrieve(
                q,
                top_k=route.candidate_top_k,
                filters=route.filters or None,
            )

            for item in retrieved:
                item["retrieval_query"] = q
                item["retrieval_query_index"] = query_index

            all_results.extend(retrieved)

        return all_results

    def _build_sources_and_context(self, results: list[dict]) -> tuple[list[dict], str]:
        documents_map = self.rag._load_documents_map(results)
        latest_version_map = self.rag._load_latest_version_map(results)

        contexts = []
        sources = []

        for i, item in enumerate(results, start=1):
            text = item.get("text")
            if text:
                title = item.get("title") or ""
                section_path = item.get("section_path") or ""

                contexts.append(f"""
                [SOURCE {i}]
                Title: {title}
                Section: {section_path}

                {text}
                [/SOURCE {i}]
                """.strip())

            metadata = item.get("metadata") or {}
            print("chunk title:", item.get("title"))
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

            preview_url = None
            if file_path:
                try:
                    preview_url = self.storage.generate_presigned_url(file_path)
                except Exception:
                    preview_url = None

            sources.append(
                {
                    "citation_id": i,
                    "title": item.get("title"),
                    "section_path": item.get("section_path"),
                    "source": metadata.get("source") or file_path or document_id,
                    "context": text,
                    "file_path": file_path,
                    "preview_url": preview_url,
                    "document_id": str(document_id) if document_id else None,
                    "mime_type": mime_type,
                    "score": item.get("score"),
                    "rerank_score": item.get("rerank_score"),
                    "metadata": metadata,
                    "bboxes": metadata.get("bboxes"),
                    "page_start": metadata.get("page_start"),
                    "page_end": metadata.get("page_end"),
                    "page_indices": metadata.get("page_indices"),
                    "page_sizes": metadata.get("page_sizes"),
                }
            )

        return sources, "\n\n".join(contexts)
