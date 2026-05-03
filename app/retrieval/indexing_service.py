from __future__ import annotations

from typing import List, Dict, Any

from app.schemas.chunk import Chunk


def chunk_to_payload(chunk: Chunk) -> Dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "chunk_type": chunk.chunk_type,
        "section_path": chunk.section_path,
        "title": chunk.title,
        "chunk_index": chunk.chunk_index,
        "total_chunks": chunk.total_chunks,
        "text": chunk.text,
        "metadata": chunk.metadata,
    }


def prepare_text_for_embedding(chunk: Chunk) -> str:
    parts = []
    if chunk.title:
        parts.append(f"Tiêu đề: {chunk.title}")
    if chunk.section_path:
        parts.append(f"Mục: {chunk.section_path}")
    parts.append(chunk.text)
    return "\n".join(parts)
