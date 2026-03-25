import uuid
from typing import List

from app.preprocessing.structure.regulation_parser import RegulationParser
from app.schemas.chunk import Chunk
from app.schemas.document import Document


class RegulationChunker:
    def __init__(self):
        self.parser = RegulationParser()

    def chunk(self, document: Document) -> List[Chunk]:
        parsed_articles = self.parser.parse(document.raw_text)

        chunks: List[Chunk] = []

        total_articles = len(parsed_articles)

        for idx, article in enumerate(parsed_articles):
            section_path = self._build_section_path(article)

            full_text = self._build_chunk_text(document, article)

            chunk = Chunk(
                chunk_id=str(uuid.uuid4()),
                document_id=document.doc_id,
                text=full_text,
                cleaned_text=article.content,

                chunk_type="regulation",

                title=article.article_title,
                section_path=section_path,

                chunk_index=idx,
                total_chunks=total_articles,

                metadata={
                    "source": document.source_path,
                    "doc_title": document.title,
                    "chapter": article.chapter_title,
                    "section": article.section_title,
                    "article_number": article.article_number,
                }
            )

            chunks.append(chunk)

        return chunks

    def _build_section_path(self, article) -> str:
        parts = []
        if article.chapter_title:
            parts.append(article.chapter_title)
        if article.section_title:
            parts.append(article.section_title)
        if article.article_title:
            parts.append(article.article_title)

        return " > ".join(parts)

    def _build_chunk_text(self, document: Document, article) -> str:
        """
        Text dùng để embed → phải có context
        """
        parts = []

        parts.append(f"Tài liệu: {document.title}")

        if article.chapter_title:
            parts.append(f"Chương: {article.chapter_title}")

        if article.section_title:
            parts.append(f"Mục: {article.section_title}")

        parts.append(f"Điều: {article.article_title}")
        parts.append("Nội dung:")
        parts.append(article.content)

        return "\n".join(parts)