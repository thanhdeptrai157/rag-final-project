"""Local-only ingest pipeline.

This version only accepts an input file, extracts text, cleans it, chunks it,
prints the chunks, and writes plain-text artifacts to disk.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

from app.chunking.universal_document_chunker import UniversalLegalChunker
from app.loaders.pdf_loader_paddle_ocr import PDFLoader
from app.preprocessing.cleaners.text_cleaner import TextCleaner
from app.schemas.document import Document as DocumentSchema


class IngestLocalPipeline:
    def __init__(self):
        self.pdf_loader = PDFLoader(enable_ocr=True, force_ocr=True)
        self.text_cleaner = TextCleaner()
        self.chunker = UniversalLegalChunker()

    def ingest(
        self,
        source_file: str | Path | None = None,
        db: object | None = None,
        *,
        file_bytes: bytes | None = None,
        file_name: str | None = None,
        output_dir: str | Path = "data/processed/chunks",
    ) -> dict[str, Any]:
        if db is not None:
            raise RuntimeError(
                "Legacy DB-backed ingest has been removed. Pass a file path or file bytes instead."
            )

        if source_file is None and file_bytes is None:
            raise ValueError("Provide source_file or file_bytes")

        if source_file is not None and file_bytes is not None:
            raise ValueError("Provide only one of source_file or file_bytes")

        temp_file_path: Path | None = None
        created_temp_file = file_bytes is not None
        source_path = self._resolve_source_path(
            source_file=source_file,
            file_bytes=file_bytes,
            file_name=file_name,
        )
        if created_temp_file:
            temp_file_path = source_path

        try:
            print(f"[INGEST] Starting local ingest for {source_path}")

            raw_text, metadata = self._extract_raw_text(source_path)
            print(f"[STEP 1] Extracted {len(raw_text)} characters")

            print("[STEP 2] Cleaning text")
            cleaned_text = self.text_cleaner.clean(raw_text)

            print("[STEP 3] Chunking text")
            document_label = Path(file_name or source_path.name).stem
            document = DocumentSchema(
                doc_id=document_label,
                source_path=str(source_path),
                source_type="upload",
                title=document_label,
                raw_text=cleaned_text,
                metadata=metadata or {},
            )

            chunker = self._choose_chunker(cleaned_text)
            print(f"[STEP 3] Selected chunker: {chunker.__class__.__name__}")
            chunks_schema = chunker.chunk(document)
            if not chunks_schema:
                raise ValueError("No chunks created from document")

            print(f"[STEP 3] Created {len(chunks_schema)} chunks")
            self._print_chunks(chunks_schema)

            run_dir = self._build_output_dir(output_dir, document_label)
            raw_text_path = run_dir / "raw_text.txt"
            cleaned_text_path = run_dir / "cleaned_text.txt"
            chunks_text_path = run_dir / "chunks.txt"
            chunks_json_path = run_dir / "chunks.json"

            raw_text_path.write_text(raw_text, encoding="utf-8")
            cleaned_text_path.write_text(cleaned_text, encoding="utf-8")
            chunks_text_path.write_text(
                self._format_chunks_as_text(chunks_schema), encoding="utf-8"
            )
            chunks_json_path.write_text(
                json.dumps(
                    [chunk.model_dump() for chunk in chunks_schema],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            print(f"[STEP 4] Saved raw text to {raw_text_path}")
            print(f"[STEP 4] Saved cleaned text to {cleaned_text_path}")
            print(f"[STEP 4] Saved chunk text to {chunks_text_path}")
            print(f"[STEP 4] Saved chunk JSON to {chunks_json_path}")

            return {
                "success": True,
                "message": f"Ingest completed: {len(chunks_schema)} chunks saved",
                "source_file": str(source_path),
                "output_dir": str(run_dir),
                "raw_text_path": str(raw_text_path),
                "cleaned_text_path": str(cleaned_text_path),
                "chunks_text_path": str(chunks_text_path),
                "chunks_json_path": str(chunks_json_path),
                "chunk_count": len(chunks_schema),
            }

        finally:
            if temp_file_path is not None:
                temp_file_path.unlink(missing_ok=True)

    def _resolve_source_path(
        self,
        *,
        source_file: str | Path | None,
        file_bytes: bytes | None,
        file_name: str | None,
    ) -> Path:
        if source_file is not None:
            path = Path(source_file)
            if not path.exists():
                raise FileNotFoundError(f"Input file not found: {path}")
            return path

        suffix = Path(file_name or "uploaded.pdf").suffix or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            assert file_bytes is not None
            tmp_file.write(file_bytes)
            return Path(tmp_file.name)

    def _extract_raw_text(self, source_path: Path) -> tuple[str, dict[str, Any]]:
        if source_path.suffix.lower() in {".txt", ".md", ".rst"}:
            return source_path.read_text(encoding="utf-8", errors="ignore"), {}

        doc_schema = self.pdf_loader.load(str(source_path))
        return doc_schema.raw_text or "", doc_schema.metadata or {}

    def _build_output_dir(self, output_dir: str | Path, document_label: str) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        run_dir = Path(output_dir) / f"{document_label}_{timestamp}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _format_chunks_as_text(self, chunks_schema: List) -> str:
        blocks: list[str] = []
        for chunk in chunks_schema:
            blocks.append(self._format_single_chunk(chunk))
        return "\n\n".join(blocks).rstrip() + "\n"

    def _format_single_chunk(self, chunk) -> str:
        metadata = chunk.metadata or {}
        lines = [
            f"=== Chunk {chunk.chunk_index + 1}/{chunk.total_chunks} ===",
            f"chunk_id: {chunk.chunk_id}",
            f"document_id: {chunk.document_id}",
            f"chunk_type: {chunk.chunk_type}",
            f"title: {chunk.title or ''}",
            f"section_path: {chunk.section_path or ''}",
            f"metadata: {json.dumps(metadata, ensure_ascii=False)}",
            "content:",
            chunk.text,
        ]
        return "\n".join(lines)

    def _print_chunks(self, chunks_schema: List) -> None:
        for chunk in chunks_schema:
            print("[CHUNK] --------------------------------------------------")
            print(self._format_single_chunk(chunk))

    def _choose_chunker(self, text: str):
        # Local-only mode always uses the universal legal chunker.
        return self.chunker
