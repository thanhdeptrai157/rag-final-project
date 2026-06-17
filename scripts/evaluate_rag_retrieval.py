from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

DEFAULT_INPUT = Path("test/rag_retrieval_test_data.csv")
DEFAULT_OUTPUT = Path("test/rag_retrieval_eval_results.csv")
DEFAULT_SUMMARY = Path("test/rag_retrieval_eval_summary.json")
DEFAULT_TOP_K = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate RAG retrieval quality on a CSV test set."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help="Final result count used for Hit@k, MRR, and Context Recall.",
    )
    parser.add_argument(
        "--candidate-top-k",
        type=int,
        default=None,
        help="Number of vector candidates retrieved before reranking.",
    )
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="Disable cross-encoder reranking for this evaluation run.",
    )
    parser.add_argument(
        "--context-top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help="Number of top contexts used to compute Context Recall.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional number of test rows to evaluate.",
    )
    return parser.parse_args()


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.replace("đ", "d")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def split_keywords(value: str) -> list[str]:
    keywords = []
    seen = set()
    for item in re.split(r"[;,]", value or ""):
        keyword = normalize_text(item)
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        keywords.append(keyword)
    return keywords


def result_chunk_id(result: dict[str, Any]) -> str:
    metadata = result.get("metadata") or {}

    return str(
        result.get("id")
        or metadata.get("point_id")
        or metadata.get("_id")
        or metadata.get("id")
        or result.get("chunk_id")
        or metadata.get("chunk_id")
        or ""
    )


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def fallback_vector_rerank(
    results: list[dict[str, Any]], top_k: int
) -> list[dict[str, Any]]:
    unique_by_chunk: dict[str, dict[str, Any]] = {}

    for item in results:
        key = result_chunk_id(item)
        current = unique_by_chunk.get(key)
        if current is None or safe_float(item.get("score")) > safe_float(
            current.get("score")
        ):
            unique_by_chunk[key] = dict(item)

    reranked = list(unique_by_chunk.values())
    reranked.sort(key=lambda item: safe_float(item.get("score")), reverse=True)

    for item in reranked[:top_k]:
        item["rerank_score"] = safe_float(item.get("score"))
        item["rerank_model"] = "vector_score_fallback"

    return reranked[:top_k]


def rerank_results(
    *,
    query: str,
    results: list[dict[str, Any]],
    top_k: int,
    use_reranker: bool,
) -> list[dict[str, Any]]:
    if not results:
        return []

    if not use_reranker:
        return fallback_vector_rerank(results, top_k)

    try:
        from app.retrieval.cross_encoder_reranker import get_cross_encoder_reranker

        reranker = get_cross_encoder_reranker()
        reranked = reranker.rerank(query=query, results=results, top_k=top_k)
        for item in reranked:
            item["rerank_model"] = reranker.model_name
        return reranked
    except Exception as exc:
        print(
            "[WARN] Cross-encoder rerank failed; using vector score fallback: "
            f"{type(exc).__name__}: {exc}"
        )
        return fallback_vector_rerank(results, top_k)


def find_expected_rank(
    results: list[dict[str, Any]],
    expected_chunk_id: str,
) -> int | None:
    expected = str(expected_chunk_id or "").strip()
    if not expected:
        return None

    for index, item in enumerate(results, start=1):
        if result_chunk_id(item) == expected:
            return index

    return None


def build_context_text(results: list[dict[str, Any]], context_top_k: int) -> str:
    parts = []
    for item in results[:context_top_k]:
        metadata = item.get("metadata") or {}
        parts.extend(
            [
                item.get("title"),
                item.get("section_path"),
                metadata.get("doc_title"),
                metadata.get("article_title"),
                item.get("text"),
            ]
        )
    return normalize_text(" ".join(str(part or "") for part in parts))


def context_recall(
    results: list[dict[str, Any]], row: dict[str, str], context_top_k: int
) -> float:
    keywords = split_keywords(row.get("expected_keywords", ""))
    if not keywords:
        rank = find_expected_rank(
            results[:context_top_k], row.get("expected_chunk_id", "")
        )
        return 1.0 if rank else 0.0

    context = build_context_text(results, context_top_k)
    if not context:
        return 0.0

    matched = sum(1 for keyword in keywords if keyword in context)
    return matched / len(keywords)


def summarize_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    if total == 0:
        return {
            "total": 0,
            "hit_at_1": 0.0,
            "hit_at_3": 0.0,
            "hit_at_5": 0.0,
            "mrr": 0.0,
            "context_recall": 0.0,
        }

    return {
        "total": total,
        "hit_at_1": sum(row["hit_at_1"] for row in rows) / total,
        "hit_at_3": sum(row["hit_at_3"] for row in rows) / total,
        "hit_at_5": sum(row["hit_at_5"] for row in rows) / total,
        "mrr": sum(row["reciprocal_rank"] for row in rows) / total,
        "context_recall": sum(row["context_recall"] for row in rows) / total,
    }


def compact_result_ids(results: list[dict[str, Any]]) -> str:
    return "|".join(result_chunk_id(item) for item in results)


def compact_result_titles(results: list[dict[str, Any]]) -> str:
    values = []
    for item in results:
        title = item.get("title") or item.get("section_path") or ""
        values.append(str(title).replace("\n", " ").strip())
    return "|".join(values)


def compact_result_scores(results: list[dict[str, Any]]) -> str:
    values = []
    for item in results:
        score = item.get("rerank_score", item.get("score"))
        values.append(f"{safe_float(score):.6f}")
    return "|".join(values)


def evaluate(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from app.core.config import Config
    from app.retrieval.retriever import Retriever

    final_top_k = max(args.top_k, 5)
    requested_candidate_top_k = args.candidate_top_k or Config.RERANKER_MAX_CANDIDATES
    candidate_top_k = max(requested_candidate_top_k, final_top_k)
    context_top_k = min(max(args.context_top_k, 1), final_top_k)
    use_reranker = Config.RERANKER_ENABLED and not args.no_rerank

    retriever = Retriever()
    output_rows = []

    with args.input.open("r", encoding="utf-8-sig", newline="") as input_file:
        reader = csv.DictReader(input_file)
        for index, row in enumerate(reader, start=1):
            if args.limit is not None and index > args.limit:
                break

            test_id = row.get("test_id") or f"row_{index}"
            question = row.get("question", "")
            print(f"[{index}] Evaluating {test_id}: {question}")

            raw_results = retriever.retrieve(question, top_k=candidate_top_k)
            results = rerank_results(
                query=question,
                results=raw_results,
                top_k=final_top_k,
                use_reranker=use_reranker,
            )

            rank = find_expected_rank(results, row.get("expected_chunk_id", ""))
            reciprocal_rank = 1.0 / rank if rank else 0.0
            recall = context_recall(results, row, context_top_k)

            output_rows.append(
                {
                    "test_id": test_id,
                    "question": question,
                    "expected_chunk_id": row.get("expected_chunk_id", ""),
                    "expected_document_id": row.get("expected_document_id", ""),
                    "expected_chunk_title": row.get("expected_chunk_title", ""),
                    "rank": rank or "",
                    "hit_at_1": 1 if rank and rank <= 1 else 0,
                    "hit_at_3": 1 if rank and rank <= 3 else 0,
                    "hit_at_5": 1 if rank and rank <= 5 else 0,
                    "reciprocal_rank": reciprocal_rank,
                    "context_recall": recall,
                    "retrieved_chunk_ids": compact_result_ids(results),
                    "retrieved_titles": compact_result_titles(results),
                    "retrieved_scores": compact_result_scores(results),
                    "rerank_model": (results[0].get("rerank_model") if results else ""),
                    "retrieved_count": len(results),
                    "candidate_count": len(raw_results),
                }
            )

    summary = summarize_results(output_rows)
    summary.update(
        {
            "input": str(args.input),
            "output": str(args.output),
            "top_k": final_top_k,
            "candidate_top_k": candidate_top_k,
            "context_top_k": context_top_k,
            "reranker_enabled": use_reranker,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return output_rows, summary


def write_outputs(
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    output_path: Path,
    summary_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "test_id",
        "question",
        "expected_chunk_id",
        "expected_document_id",
        "expected_chunk_title",
        "rank",
        "hit_at_1",
        "hit_at_3",
        "hit_at_5",
        "reciprocal_rank",
        "context_recall",
        "retrieved_chunk_ids",
        "retrieved_titles",
        "retrieved_scores",
        "rerank_model",
        "retrieved_count",
        "candidate_count",
    ]

    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with summary_path.open("w", encoding="utf-8") as summary_file:
        json.dump(summary, summary_file, ensure_ascii=False, indent=2)
        summary_file.write("\n")


def main() -> None:
    args = parse_args()
    rows, summary = evaluate(args)
    write_outputs(rows, summary, args.output, args.summary_output)

    print("\n=== Retrieval Evaluation Summary ===")
    print(f"Total: {summary['total']}")
    print(f"Hit@1: {summary['hit_at_1']:.4f}")
    print(f"Hit@3: {summary['hit_at_3']:.4f}")
    print(f"Hit@5: {summary['hit_at_5']:.4f}")
    print(f"MRR: {summary['mrr']:.4f}")
    print(f"Context Recall: {summary['context_recall']:.4f}")
    print(f"Details: {args.output}")
    print(f"Summary: {args.summary_output}")


if __name__ == "__main__":
    main()
