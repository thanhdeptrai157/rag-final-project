import uuid
from typing import Any, Dict, List, Optional

from app.preprocessing.structure.universal_legal_parser import (
    ParsedChunk,
    UniversalLegalParser,
)
from app.schemas.chunk import Chunk
from app.schemas.document import Document


class UniversalLegalChunker:
    def __init__(self) -> None:
        self.parser = UniversalLegalParser()

    def chunk(
        self, document: Document, layout_data: Dict[str, Any] | None = None
    ) -> List[Chunk]:
        if layout_data:
            parsed_chunks = self.parser.parse_with_layout(
                document.raw_text, layout_data
            )
        else:
            parsed_chunks = self.parser.parse(document.raw_text)

        chunks: List[Chunk] = []
        total_chunks = len(parsed_chunks)

        for idx, item in enumerate(parsed_chunks):
            chunk_id = str(uuid.uuid4())
            title = self._build_title(item)
            section_path = self._build_section_path(item)

            page_start = None
            page_end = None
            if item.page_indices:
                page_start = min(item.page_indices) + 1
                page_end = max(item.page_indices) + 1

            chunk = Chunk(
                chunk_id=chunk_id,
                document_id=document.doc_id,
                text=self._build_chunk_text(document, item),
                cleaned_text=item.content,
                chunk_type=self._build_chunk_type(item),
                title=title,
                section_path=section_path,
                page_start=page_start,
                page_end=page_end,
                chunk_index=idx,
                total_chunks=total_chunks,
                metadata=self._build_metadata(
                    document=document,
                    item=item,
                    title=title,
                    section_path=section_path,
                    chunk_index=idx,
                    total_chunks=total_chunks,
                ),
            )

            chunks.append(chunk)

        return chunks

    def _build_chunk_type(self, item: ParsedChunk) -> str:
        if item.chunk_kind == "amendment":
            return "regulation_amendment"

        if item.chunk_kind == "article":
            return "regulation"

        if item.chunk_kind == "section":
            return "document_section"

        if item.chunk_kind == "table":
            return "table"

        return "document_chunk"

    def _build_title(self, item: ParsedChunk) -> str:
        if item.chunk_kind == "amendment" and item.target_article_number:
            if item.target_clause_text:
                return (
                    f"{self._action_label(item.action)} khoản "
                    f"{item.target_clause_text}, Điều {item.target_article_number}"
                )

            return (
                f"{self._action_label(item.action)} "
                f"Điều {item.target_article_number}"
            )

        return item.title

    def _build_section_path(self, item: ParsedChunk) -> str:
        if item.chunk_kind == "amendment":
            parts: List[str] = ["Văn bản sửa đổi/bổ sung"]

            if item.article_number:
                parts.append(f"Điều chứa nội dung sửa đổi {item.article_number}")

            if item.target_article_number:
                parts.append(f"Điều được tác động {item.target_article_number}")

            if item.target_clause_text:
                parts.append(f"Khoản {item.target_clause_text}")

            parts.append(self._action_label(item.action))
            return " > ".join(parts)

        parts: List[str] = []

        if item.part_title:
            parts.append(item.part_title)

        if item.chapter_title:
            parts.append(item.chapter_title)

        if item.section_title:
            parts.append(item.section_title)

        body_path = item.section_path or item.title
        if body_path:
            parts.append(body_path)

        return " > ".join(self._dedupe_path_parts(parts))

    def _build_chunk_text(self, document: Document, item: ParsedChunk) -> str:
        parts: List[str] = []

        parts.append(f"Tài liệu: {document.title}")

        if item.chunk_kind == "amendment":
            parts.append("Loại chunk: Nội dung sửa đổi/bổ sung/bãi bỏ")
            parts.append(f"Loại thay đổi: {self._action_label(item.action)}")

            if item.article_title:
                parts.append(f"Điều chứa nội dung sửa đổi: {item.article_title}")

            if item.target_article_number:
                parts.append(
                    f"Điều được tác động: Điều {item.target_article_number}"
                )

            if item.target_clause_text:
                parts.append(f"Khoản được tác động: {item.target_clause_text}")

            parts.append(f"Tiêu đề nội dung sửa đổi: {item.title}")

            if item.action == "repeal":
                parts.append("Nội dung bị bãi bỏ:")
            elif item.action == "supplement":
                parts.append("Nội dung được bổ sung:")
            elif item.action == "replace":
                parts.append("Nội dung thay thế:")
            elif item.action == "modify":
                parts.append("Nội dung sau sửa đổi:")
            else:
                parts.append("Nội dung:")

            parts.append(item.content)
            return "\n".join(parts)

        if item.chunk_kind == "article":
            parts.append("Loại chunk: Điều trong văn bản")

            if item.chapter_title:
                parts.append(f"Chương: {item.chapter_title}")

            if item.section_title:
                parts.append(f"Mục: {item.section_title}")

            if item.article_title:
                parts.append(f"Điều: {item.article_title}")

            parts.append("Nội dung:")
            parts.append(item.content)
            return "\n".join(parts)

        if item.chunk_kind == "section":
            parts.append("Loại chunk: Mục nội dung")

            if item.heading_number:
                parts.append(f"Số mục: {item.heading_number}")

            if item.heading_level:
                parts.append(f"Cấp mục: {item.heading_level}")

            if item.section_title:
                parts.append(f"Mục cha: {item.section_title}")

            parts.append(f"Tiêu đề mục: {item.title}")
            parts.append("Nội dung:")
            parts.append(item.content)
            return "\n".join(parts)

        parts.append(f"Loại chunk: {item.chunk_kind}")
        parts.append(f"Tiêu đề: {item.title}")
        parts.append("Nội dung:")
        parts.append(item.content)

        return "\n".join(parts)

    def _build_metadata(
        self,
        *,
        document: Document,
        item: ParsedChunk,
        title: str,
        section_path: str,
        chunk_index: int,
        total_chunks: int,
    ) -> dict:
        document_metadata = document.metadata or {}

        metadata = {
            "source": document.source_path,
            "source_type": document.source_type,
            "doc_title": document.title,
            "chunk_title": title,
            "section_path": section_path,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "document_id": document.doc_id,
            "document_version_id": getattr(document, "version_id", None),
            "version_number": self._resolve_version_number(document),
            "previous_version_id": getattr(document, "previous_version_id", None),
            "previous_version_number": getattr(
                document,
                "previous_version_number",
                None,
            ),
            "file_name": document_metadata.get("file_name"),
            "page_count": document_metadata.get("page_count"),
            "ocr_enabled": document_metadata.get("ocr_enabled"),
            "force_ocr": document_metadata.get("force_ocr"),
            "ocr_lang": document_metadata.get("ocr_lang"),
            "ocr_dpi": document_metadata.get("ocr_dpi"),
            "ocr_pages": document_metadata.get("ocr_pages"),
            "paddle_job_id": document_metadata.get("paddle_job_id"),
            "chunk_kind": item.chunk_kind,
            "status": "active",
            "is_current": True,
            "part": item.part_title,
            "chapter": item.chapter_title,
            "section": item.section_title,
            "appendix_title": item.appendix_title,
            "appendix_number": item.appendix_number,
            "article_title": item.article_title,
            "article_number": item.article_number,
            "heading_level": item.heading_level,
            "heading_number": item.heading_number,
            "bboxes": item.bboxes,
            "page_indices": item.page_indices,
            "page_start": min(item.page_indices) + 1 if item.page_indices else None,
            "page_end": max(item.page_indices) + 1 if item.page_indices else None,
        }

        if item.chunk_kind == "amendment":
            metadata.update(
                {
                    "is_amendment": True,
                    "change_type": item.action,
                    "source_article_number": item.article_number,
                    "target_article_number": item.target_article_number,
                    "target_clause_text": item.target_clause_text,
                    "article_number": (
                        item.target_article_number or item.article_number
                    ),
                    "parent_chunk_id": None,
                    "supersedes_chunk_id": None,
                    "superseded_by_chunk_id": None,
                    "amendment_order_number": item.order_number,
                    "amendment_title": item.title,
                }
            )
        else:
            metadata.update(
                {
                    "is_amendment": False,
                    "change_type": None,
                    "target_article_number": None,
                    "target_clause_text": None,
                    "parent_chunk_id": None,
                    "supersedes_chunk_id": None,
                    "superseded_by_chunk_id": None,
                }
            )

        return metadata

    def _resolve_version_number(self, document: Document) -> int | None:
        version_no = getattr(document, "version_no", None)
        if version_no is not None:
            return version_no

        return getattr(document, "version_number", None)

    def _dedupe_path_parts(self, parts: List[str]) -> List[str]:
        normalized: List[str] = []

        for part in parts:
            cleaned = part.strip()
            if not cleaned:
                continue

            if normalized and normalized[-1] == cleaned:
                continue

            normalized.append(cleaned)

        return normalized

    def _action_label(self, action: Optional[str]) -> str:
        labels = {
            "modify": "Sửa đổi",
            "supplement": "Bổ sung",
            "replace": "Thay thế",
            "repeal": "Bãi bỏ",
            "rename": "Sửa đổi tên gọi",
            "unknown": "Không xác định",
            None: "Không xác định",
        }

        return labels.get(action, str(action))
