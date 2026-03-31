from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import Config
from app.services.rag_service import RagService


def main():
    if not Config.GEMINI_API_KEY:
        print("Thiếu GEMINI_API_KEY. Hãy thêm key vào file .env trước khi chạy.")
        return

    rag_service = RagService()

    while True:
        query = input("\nNhập câu hỏi (hoặc 'exit'): ").strip()
        if query.lower() == "exit":
            break

        result = rag_service.answer_query(query, top_k=5)

        print("\n=== CÂU TRẢ LỜI ===")
        print(result["answer"])

        print("\n=== NGUỒN THAM CHIẾU ===")
        for i, source in enumerate(result["sources"], start=1):
            print("-" * 80)
            print(f"Top {i}")
            print(f"title: {source['title']}")
            print(f"section_path: {source['section_path']}")
            print(f"source: {source['source']}")


if __name__ == "__main__":
    main()
