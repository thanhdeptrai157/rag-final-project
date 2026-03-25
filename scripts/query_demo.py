from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.retrieval.retriever import Retriever


def main():
    retriever = Retriever()

    while True:
        query = input("\nNhập câu hỏi (hoặc 'exit'): ").strip()
        if query.lower() == "exit":
            break

        results = retriever.retrieve(query, top_k=5)

        print("\n=== TOP RESULTS ===")
        for i, item in enumerate(results, start=1):
            print("=" * 80)
            print(f"Top {i} | score={item['score']:.4f}")
            print(f"title: {item['title']}")
            print(f"section_path: {item['section_path']}")
            print(f"text:\n{item['text']}")
            print()


if __name__ == "__main__":
    main()
