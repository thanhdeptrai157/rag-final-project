from dataclasses import dataclass, field
from enum import Enum


class QueryStrategy(str, Enum):
    EXACT_LEGAL_LOOKUP = "exact_legal_lookup"
    APPENDIX_LOOKUP = "appendix_lookup"
    AMENDMENT_LOOKUP = "amendment_lookup"
    BROAD_SEMANTIC_RAG = "broad_semantic_rag"
    LOW_CONTEXT_OR_INVALID = "low_context_or_invalid"


@dataclass
class QueryRoute:
    strategy: QueryStrategy
    normalized_query: str
    filters: dict = field(default_factory=dict)
    boosts: dict = field(default_factory=dict)
    top_k: int = 3
    candidate_top_k: int = 12
    use_query_expansion: bool = True
    use_related_chunk_expansion: bool = True
