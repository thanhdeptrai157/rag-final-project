"""
Loader cho file văn bản thuần (.txt).
Đọc trực tiếp nội dung văn bản, bỏ qua bước OCR.
"""

from pathlib import Path

from app.schemas.document import Document


class TextFileLoader:
    """Load file .txt thành DocumentSchema, không qua OCR."""

    def load(self, file_path: str | Path) -> Document:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Thử UTF-8 trước, fallback sang latin-1
        try:
            raw_text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw_text = path.read_text(encoding="latin-1")

        raw_text = raw_text.strip()

        return Document(
            doc_id=path.stem.lower().replace(" ", "_"),
            source_path=str(path),
            source_type="txt",
            title=path.stem,
            raw_text=raw_text,
            metadata={
                "file_name": path.name,
                "encoding": "utf-8",
                "char_count": len(raw_text),
            },
        )
