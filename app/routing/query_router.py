import re
import unicodedata
from typing import Any

from app.routing.query_route import QueryRoute, QueryStrategy


class QueryRouter:
    def __init__(self, llm: Any | None = None, min_llm_confidence: float = 0.55):
        self.llm = llm
        self.min_llm_confidence = min_llm_confidence

    def route(self, query: str, top_k: int = 3) -> QueryRoute:
        normalized = self._fold_text(query)

        if len(normalized.split()) <= 1:
            return QueryRoute(
                strategy=QueryStrategy.LOW_CONTEXT_OR_INVALID,
                normalized_query=normalized,
                top_k=top_k,
                use_query_expansion=False,
            )

        rule_route = self._route_by_rules(normalized=normalized, top_k=top_k)
        llm_route = self._route_by_llm(query=query, normalized=normalized, top_k=top_k)

        if rule_route and (
            not llm_route
            or llm_route.strategy
            in {
                QueryStrategy.BROAD_SEMANTIC_RAG,
                QueryStrategy.LOW_CONTEXT_OR_INVALID,
            }
        ):
            return rule_route

        if llm_route:
            return llm_route

        if rule_route:
            return rule_route

        return self._broad_route(normalized=normalized, top_k=top_k)

    def _route_by_rules(self, normalized: str, top_k: int) -> QueryRoute | None:
        article_number = self._extract_article_number(normalized)
        if article_number:
            return QueryRoute(
                strategy=QueryStrategy.EXACT_LEGAL_LOOKUP,
                normalized_query=normalized,
                filters={"article_number": article_number},
                top_k=top_k,
                candidate_top_k=max(top_k * 3, 8),
                use_query_expansion=False,
            )

        appendix_number = self._extract_appendix_number(normalized)
        if appendix_number:
            return QueryRoute(
                strategy=QueryStrategy.APPENDIX_LOOKUP,
                normalized_query=normalized,
                filters={
                    "chunk_kind": "appendix",
                    "appendix_number": appendix_number,
                },
                top_k=top_k,
                candidate_top_k=max(top_k * 4, 12),
                use_query_expansion=False,
            )

        if any(x in normalized for x in ["sua doi", "bo sung", "bai bo", "thay the", "hien hanh"]):
            return QueryRoute(
                strategy=QueryStrategy.AMENDMENT_LOOKUP,
                normalized_query=normalized,
                filters={"is_amendment": True},
                top_k=top_k,
                candidate_top_k=max(top_k * 5, 15),
                use_query_expansion=True,
            )

        return None

    def _route_by_llm(
        self, query: str, normalized: str, top_k: int
    ) -> QueryRoute | None:
        if not self.llm or not hasattr(self.llm, "generate_query_route"):
            return None

        try:
            decision = self.llm.generate_query_route(query=query)
        except Exception:
            return None

        if not isinstance(decision, dict):
            return None

        confidence = self._coerce_confidence(decision.get("confidence"))
        if confidence < self.min_llm_confidence:
            return None

        try:
            strategy = QueryStrategy(str(decision.get("strategy", "")).strip())
        except ValueError:
            return None

        if strategy == QueryStrategy.LOW_CONTEXT_OR_INVALID and confidence < 0.75:
            return None

        article_number = self._extract_article_number(normalized) or self._clean_token(
            decision.get("article_number")
        )
        appendix_number = self._extract_appendix_number(
            normalized
        ) or self._clean_token(decision.get("appendix_number"), uppercase=True)

        if strategy == QueryStrategy.EXACT_LEGAL_LOOKUP:
            if not article_number:
                return None
            return QueryRoute(
                strategy=strategy,
                normalized_query=normalized,
                filters={"article_number": article_number},
                boosts={"llm_confidence": confidence},
                top_k=top_k,
                candidate_top_k=max(top_k * 3, 8),
                use_query_expansion=False,
            )

        if strategy == QueryStrategy.APPENDIX_LOOKUP:
            filters = {"chunk_kind": "appendix"}
            if appendix_number:
                filters["appendix_number"] = appendix_number

            return QueryRoute(
                strategy=strategy,
                normalized_query=normalized,
                filters=filters,
                boosts={"llm_confidence": confidence},
                top_k=top_k,
                candidate_top_k=max(top_k * 4, 12),
                use_query_expansion=False,
            )

        if strategy == QueryStrategy.AMENDMENT_LOOKUP:
            filters = {"is_amendment": True}
            if article_number:
                filters["article_number"] = article_number

            return QueryRoute(
                strategy=strategy,
                normalized_query=normalized,
                filters=filters,
                boosts={"llm_confidence": confidence},
                top_k=top_k,
                candidate_top_k=max(top_k * 5, 15),
                use_query_expansion=True,
            )

        if strategy == QueryStrategy.LOW_CONTEXT_OR_INVALID:
            return QueryRoute(
                strategy=strategy,
                normalized_query=normalized,
                boosts={"llm_confidence": confidence},
                top_k=top_k,
                use_query_expansion=False,
            )

        if strategy == QueryStrategy.BROAD_SEMANTIC_RAG:
            return self._broad_route(
                normalized=normalized,
                top_k=top_k,
                boosts={"llm_confidence": confidence},
            )

        return None

    def _broad_route(
        self, normalized: str, top_k: int, boosts: dict | None = None
    ) -> QueryRoute:
        return QueryRoute(
            strategy=QueryStrategy.BROAD_SEMANTIC_RAG,
            normalized_query=normalized,
            boosts=boosts or {},
            top_k=top_k,
            candidate_top_k=max(top_k * 4, 12),
            use_query_expansion=True,
        )

    def _coerce_confidence(self, value) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(confidence, 1.0))

    def _clean_token(self, value, uppercase: bool = False) -> str | None:
        if value is None:
            return None

        token = str(value).strip()
        if not token or token.lower() == "null":
            return None

        return token.upper() if uppercase else token.lower()

    def _extract_article_number(self, text: str) -> str | None:
        match = re.search(r"\bdieu\s+(\d+[a-z]?)\b", text)
        return match.group(1) if match else None

    def _extract_appendix_number(self, text: str) -> str | None:
        match = re.search(r"\bphu\s*luc\s+([ivxlcdm]+|\d+)\b", text)
        if not match:
            return None
        return match.group(1).upper()

    def _fold_text(self, text: str) -> str:
        normalized = unicodedata.normalize("NFD", str(text).lower())
        without_marks = "".join(
            char for char in normalized if unicodedata.category(char) != "Mn"
        )
        without_marks = without_marks.replace("đ", "d")
        return re.sub(r"\s+", " ", without_marks).strip()
