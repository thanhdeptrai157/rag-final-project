import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from html import unescape
from bs4 import BeautifulSoup


@dataclass
class ParsedChunk:
    chunk_kind: str  # article | amendment | appendix | section | unknown

    title: str
    content: str

    part_title: Optional[str] = None
    chapter_title: Optional[str] = None
    section_title: Optional[str] = None
    appendix_title: Optional[str] = None
    appendix_number: Optional[str] = None

    article_title: Optional[str] = None
    article_number: Optional[str] = None

    heading_level: Optional[int] = None
    heading_number: Optional[str] = None
    section_path: Optional[str] = None

    order_number: Optional[str] = None
    action: Optional[str] = None

    target_article_number: Optional[str] = None
    target_clause_text: Optional[str] = None

    # Layout information from MinerU para_blocks.
    # Each item keeps its own page_idx so downstream/highlight logic does not
    # need to infer the page from a separate parallel list.
    # Example: [{"bbox": [x0, y0, x1, y1], "page_idx": 0}]
    bboxes: Optional[List[Dict[str, Any]]] = None

    # Page size per page_idx touched by this chunk.
    # Example: {0: {"width": 595, "height": 842}}
    page_sizes: Optional[Dict[int, Dict[str, float]]] = None

    # Backward-compatible convenience field. Prefer bboxes[*].page_idx.
    page_indices: Optional[List[int]] = None


class UniversalLegalParser:
    PART_RE = re.compile(r"^\s*(?:phần|phan)\s+([ivxlcdm]+|\d+)\b.*$", re.I)
    CHAPTER_RE = re.compile(r"^\s*(?:chương|chuong)\s+([ivxlcdm]+|\d+)\b.*$", re.I)
    SECTION_RE = re.compile(r"^\s*(?:mục|muc)\s+([ivxlcdm]+|\d+)\b.*$", re.I)

    APPENDIX_RE = re.compile(
        r"^\s*(?:phụ\s*lục|phu\s*luc)(?:\s+([ivxlcdm]+|\d+))?\s*$",
        re.I,
    )

    ARTICLE_RE = re.compile(
        r"^\s*(?:điều|dieu)\s+(\d+[a-zA-Z]?)\s*[.:]?\s*(.*)$",
        re.I,
    )

    ROMAN_HEADING_RE = re.compile(
        r"^\s*([IVXLCDM]+)\.\s+(.+)$",
        re.I,
    )

    NUMBERED_HEADING_RE = re.compile(
        r"^\s*((?:\d+\.)+\d*|\d+)\.?\s+(.+)$",
        re.I,
    )

    CLAUSE_RE = re.compile(
        r"^\s*(\d+)\.\s+(.+)$",
        re.I,
    )

    POINT_RE = re.compile(
        r"^\s*([a-zđ])\)\s+(.+)$",
        re.I,
    )

    BULLET_RE = re.compile(
        r"^\s*[-+•]\s+(.+)$",
        re.I,
    )

    AMENDMENT_ITEM_RE = re.compile(r"^\s*(\d+)\.\s+(.+)$", re.I)

    ARTICLE_ACTION_RE = re.compile(
        r"(sửa đổi|bổ sung|thay thế|bãi bỏ)\s+điều\s+(\d+[a-zA-Z]?)",
        re.I,
    )

    ARTICLE_ACTION_ASCII_RE = re.compile(
        r"(sua doi|bo sung|thay the|bai bo)\s+dieu\s+(\d+[a-zA-Z]?)",
        re.I,
    )

    CLAUSE_ACTION_RE = re.compile(
        r"(sửa đổi|bổ sung|thay thế|bãi bỏ)"
        r"\s+khoản\s+(.+?)"
        r"\s*,?\s*điều\s+(\d+[a-zA-Z]?)",
        re.I,
    )

    CLAUSE_ACTION_ASCII_RE = re.compile(
        r"(sua doi|bo sung|thay the|bai bo)"
        r"\s+khoan\s+(.+?)"
        r"\s*,?\s*dieu\s+(\d+[a-zA-Z]?)",
        re.I,
    )

    RENAME_RE = re.compile(
        r"(sửa đổi|thay thế)\s+tên\s+(.+?)\s+thành\s+(.+)",
        re.I,
    )

    RENAME_ASCII_RE = re.compile(
        r"(sua doi|thay the)\s+ten\s+(.+?)\s+thanh\s+(.+)",
        re.I,
    )

    FREE_FORM_AMENDMENT_RE = re.compile(
        r"^\s*(bãi bỏ|sửa đổi|bổ sung|thay thế)\s+(.+)$",
        re.I,
    )

    FREE_FORM_AMENDMENT_ASCII_RE = re.compile(
        r"^\s*(bai bo|sua doi|bo sung|thay the)\s+(.+)$",
        re.I,
    )

    def __init__(
        self,
        max_chunk_chars: int = 4500,
        min_section_chunk_chars: int = 900,
    ) -> None:
        self.max_chunk_chars = max_chunk_chars
        self.min_section_chunk_chars = min_section_chunk_chars

    def _break_trailing_numbered_heading(self, text: str) -> str:
        fixed_lines = []

        pattern = re.compile(
            r"^(.{20,}?)\s+(\d+\.\s+[A-ZÀ-Ỵa-zà-ỵ][^\n]{1,80})$",
            re.I,
        )

        for raw_line in text.splitlines():
            line = raw_line.strip()
            m = pattern.match(line)

            if not m:
                fixed_lines.append(raw_line)
                continue

            before = m.group(1).strip()
            heading = m.group(2).strip()

            # Tránh tách nhầm dòng văn bản thường
            before_folded = self._fold_text(before)
            if not any(
                k in before_folded
                for k in ["bang quy doi", "khung nang luc", "phu luc"]
            ):
                fixed_lines.append(raw_line)
                continue

            fixed_lines.append(before)
            fixed_lines.append(heading)

        return "\n".join(fixed_lines)

    def _dump_debug_text(self, text: str) -> None:
        """
        Dump text đã clean ra file để debug parser.
        """

        try:
            with open("debug_cleaned_text.txt", "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            print(f"[DEBUG] Failed to dump cleaned text: {e}")

    def parse(
        self,
        text: str,
        layout_index: Optional[List[Dict[str, Any]]] = None,
    ) -> List[ParsedChunk]:
        text = self._normalize_text(text)
        text = self._normalize_ocr_errors(text)
        text = self._normalize_footnote_markers(text)
        text = self._html_tables_to_markdown(text)
        text = self._html_blocks_to_text(text)
        text = self._break_appendix_inline_title(text)
        text = self._break_trailing_numbered_heading(text)
        text = self._break_inline_headings(text)
        # self._dump_debug_text(text)
        blocks = self._split_by_major_blocks(text, layout_index=layout_index)

        if blocks:
            chunks: List[ParsedChunk] = []

            for block in blocks:
                kind = block["kind"]

                if kind == "article":
                    chunks.extend(self._parse_article_block(block))

                elif kind == "appendix":
                    chunks.extend(self._parse_appendix_block(block))

                else:
                    chunks.extend(self._parse_generic_block(block))

            return self._post_process(chunks)

        section_chunks = self._parse_by_numbered_headings(
            text,
            layout_index=layout_index,
        )

        if section_chunks:
            return self._post_process(section_chunks)

        fallback = ParsedChunk(
            chunk_kind="unknown",
            title=self._extract_fallback_title(text),
            content=text.strip(),
        )
        self._apply_layout_payload(
            fallback,
            self._layout_payload_for_lines(text.splitlines(), layout_index),
        )

        return self._post_process(
            [fallback]
        )

    def parse_with_layout(
        self, text: str, layout_data: Dict[str, Any]
    ) -> List[ParsedChunk]:
        """
        Parse text và ghép bounding box + page_idx từ layout JSON.
        Layout info được gán TRONG LÚC parse (line-level matching)
        thay vì post-process sau khi text đã bị transform.

        Args:
            text: Cleaned text đã extract từ PDF.
            layout_data: Dict đã parse từ layout.json (cấu trúc MinerU).

        Returns:
            Danh sách ParsedChunk với bboxes có page_idx và page_sizes đã được gán.
        """
        if not layout_data:
            return self.parse(text)

        layout_index = self._build_layout_index(layout_data)
        return self.parse(text, layout_index=layout_index)

    # ------------------------------------------------------------------
    # Layout index building and line-level matching (primary approach)
    # ------------------------------------------------------------------

    def _build_layout_index(
        self, layout_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Build a flat index of layout entries for line-level matching during parse.
        Ưu tiên MinerU para_blocks vì đây là block đã có reading order và paragraph segmentation.
        """
        entries: List[Dict[str, Any]] = []

        for page in layout_data.get("pdf_info", []):
            page_idx = page.get("page_idx", 0)
            page_size = self._extract_page_size(page)

            # MinerU: para_blocks là kết quả đã xử lý paragraph/reading order.
            # Fallback sang preproc_blocks chỉ để tương thích với layout cũ.
            blocks = page.get("para_blocks") or page.get("preproc_blocks") or []
            for block in blocks:
                self._extract_block_entries_to_index(block, page_idx, page_size, entries)

        return entries

    def _extract_page_size(self, page: Dict[str, Any]) -> Optional[Dict[str, float]]:
        """Extract page width/height from common MinerU layout.json shapes."""
        size = page.get("page_size") or page.get("size")

        if isinstance(size, dict):
            width = size.get("width") or size.get("w")
            height = size.get("height") or size.get("h")
            if width is not None and height is not None:
                return {"width": float(width), "height": float(height)}

        if isinstance(size, (list, tuple)) and len(size) >= 2:
            return {"width": float(size[0]), "height": float(size[1])}

        width = page.get("width") or page.get("page_width")
        height = page.get("height") or page.get("page_height")
        if width is not None and height is not None:
            return {"width": float(width), "height": float(height)}

        return None

    def _extract_block_entries_to_index(
        self,
        block: Dict[str, Any],
        page_idx: int,
        page_size: Optional[Dict[str, float]],
        entries: List[Dict[str, Any]],
    ) -> None:
        """Recursively extract layout entries from a para/preproc block at span/line/block levels."""
        block_bbox = block.get("bbox")
        all_texts: List[str] = []

        for line in block.get("lines", []):
            line_bbox = line.get("bbox")
            line_texts: List[str] = []

            for span in line.get("spans", []):
                content = span.get("content", "")
                if not content or span.get("type") != "text":
                    continue

                line_texts.append(content)

                # Span-level entry (finest granularity)
                span_bbox = span.get("bbox") or line_bbox or block_bbox
                if span_bbox:
                    folded = self._normalize_for_layout_match(content)
                    if folded:
                        entries.append(
                            {
                                "text": content,
                                "folded": folded,
                                "bbox": span_bbox,
                                "page_idx": page_idx,
                                "page_size": page_size,
                            }
                        )

            if line_texts:
                all_texts.extend(line_texts)

                # Line-level entry (only when multiple spans merge into one line)
                if len(line_texts) > 1:
                    line_text = " ".join(line_texts)
                    use_bbox = line_bbox or block_bbox
                    if use_bbox:
                        folded = self._normalize_for_layout_match(line_text)
                        if folded:
                            entries.append(
                                {
                                    "text": line_text,
                                    "folded": folded,
                                    "bbox": use_bbox,
                                    "page_idx": page_idx,
                                    "page_size": page_size,
                                }
                            )

        # Block-level entry (full text of block, coarsest granularity)
        if all_texts and block_bbox:
            block_text = " ".join(all_texts)
            folded = self._normalize_for_layout_match(block_text)
            if folded:
                entries.append(
                    {
                        "text": block_text,
                        "folded": folded,
                        "bbox": block_bbox,
                        "page_idx": page_idx,
                        "page_size": page_size,
                    }
                )

        # Handle nested blocks (e.g., image blocks with sub-blocks)
        for child in block.get("blocks", []):
            self._extract_block_entries_to_index(child, page_idx, page_size, entries)

    def _normalize_for_layout_match(self, text: str) -> str:
        """
        Normalize text để so khớp giữa parser line và layout block text.
        Loại bỏ whitespace thừa, lowercase, bỏ dấu.
        """
        text = re.sub(r"\s+", " ", text).strip()
        return self._fold_text(text)

    def _lookup_layout_for_line(
        self,
        line_folded: str,
        layout_index: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Tìm layout entries khớp với một parser line dựa trên fold-text.
        Match theo cả hai chiều: line in entry, hoặc entry in line.

        Returns:
            Danh sách entries duy nhất (deduped theo bbox + page_idx).
        """
        if len(line_folded) < 10:
            return []

        matched: List[Dict[str, Any]] = []
        seen: set = set()

        for entry in layout_index:
            ef = entry["folded"]
            if not ef or len(ef) < 8:
                continue

            is_match = False

            if ef == line_folded:
                # Exact match
                is_match = True
            elif len(line_folded) >= 20 and line_folded in ef:
                # Parser line là substring của layout entry (line ngắn hơn block)
                is_match = True
            elif len(ef) >= 20 and ef in line_folded:
                # Layout entry là substring của parser line (block ngắn hơn line)
                is_match = True

            if is_match:
                bbox = entry.get("bbox")
                key = (tuple(bbox) if bbox else None, entry["page_idx"])
                if key not in seen:
                    seen.add(key)
                    matched.append(entry)

        return matched

    def _propagate_block_layout(
        self, block: dict, chunks: List[ParsedChunk]
    ) -> None:
        """
        Gán bboxes và page_indices từ block dict sang các ParsedChunks.
        Chỉ gán nếu chunk chưa có layout info (không ghi đè).
        """
        bboxes = block.get("bboxes")
        page_sizes = block.get("page_sizes")
        page_indices = block.get("page_indices")

        for chunk in chunks:
            if bboxes is not None and chunk.bboxes is None:
                chunk.bboxes = bboxes
            if page_sizes is not None and chunk.page_sizes is None:
                chunk.page_sizes = page_sizes
            if page_indices is not None and chunk.page_indices is None:
                chunk.page_indices = page_indices

    def _layout_payload_for_lines(
        self,
        lines: List[str],
        layout_index: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """
        Build layout payload for fallback parsers that split by headings rather
        than major legal blocks. This keeps _split_by_major_blocks unchanged.
        """
        if not layout_index:
            return {}

        bboxes: List[Dict[str, Any]] = []
        page_sizes: Dict[int, Dict[str, float]] = {}
        page_indices: set[int] = set()
        seen: set = set()

        for raw_line in lines:
            line = self._strip_md_heading(raw_line.strip())
            if not line or self._is_page_number(line):
                continue

            folded = self._normalize_for_layout_match(line)
            for entry in self._lookup_layout_for_line(folded, layout_index):
                page_idx = entry.get("page_idx")
                bbox = entry.get("bbox")

                if bbox:
                    key = (tuple(bbox), page_idx)
                    if key not in seen:
                        seen.add(key)
                        bboxes.append(
                            {
                                "bbox": bbox,
                                "page_idx": page_idx,
                            }
                        )

                if isinstance(page_idx, int):
                    page_indices.add(page_idx)
                    if entry.get("page_size") is not None:
                        page_sizes[page_idx] = entry["page_size"]

        payload: Dict[str, Any] = {}
        if bboxes:
            payload["bboxes"] = bboxes
        if page_sizes:
            payload["page_sizes"] = dict(sorted(page_sizes.items()))
        if page_indices:
            payload["page_indices"] = sorted(page_indices)
        return payload

    def _apply_layout_payload(
        self,
        chunk: ParsedChunk,
        payload: Dict[str, Any],
    ) -> None:
        if not payload:
            return

        chunk.bboxes = payload.get("bboxes")
        chunk.page_sizes = payload.get("page_sizes")
        chunk.page_indices = payload.get("page_indices")

    # ------------------------------------------------------------------
    # Legacy layout helpers (kept for backward compatibility)
    # ------------------------------------------------------------------

    def _build_layout_entries(
        self, layout_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Legacy: block-level only layout entries."""
        entries: List[Dict[str, Any]] = []

        for page in layout_data.get("pdf_info", []):
            page_idx = page.get("page_idx", 0)
            page_size = self._extract_page_size(page)

            for block in page.get("para_blocks") or page.get("preproc_blocks", []):
                text = self._extract_layout_block_text(block)

                if not text:
                    continue

                entries.append(
                    {
                        "text": text,
                        "normalized": self._normalize_for_layout_match(text),
                        "bbox": block.get("bbox"),
                        "page_idx": page_idx,
                        "page_size": page_size,
                    }
                )

        return entries

    def _extract_layout_block_text(self, block: Dict[str, Any]) -> str:
        """Legacy: extract text from a layout block."""
        texts: List[str] = []

        for line in block.get("lines", []):
            for span in line.get("spans", []):
                content = span.get("content", "")
                if content and span.get("type") == "text":
                    texts.append(content)

        for child in block.get("blocks", []):
            child_text = self._extract_layout_block_text(child)
            if child_text:
                texts.append(child_text)

        return " ".join(texts).strip()

    # ------------------------------------------------------------------
    # Split major blocks: Article / Appendix / Chapter / Section
    # ------------------------------------------------------------------

    def _split_by_major_blocks(
        self,
        text: str,
        layout_index: Optional[List[Dict[str, Any]]] = None,
    ) -> List[dict]:
        lines = text.splitlines()
        blocks: List[dict] = []

        current_part: Optional[str] = None
        current_chapter: Optional[str] = None
        current_section: Optional[str] = None
        current_appendix: Optional[str] = None

        current_kind: Optional[str] = None
        current_title: Optional[str] = None
        current_number: Optional[str] = None
        current_lines: List[str] = []

        # Layout accumulators for the current block
        current_bboxes: List[Dict[str, Any]] = []
        current_page_sizes: Dict[int, Dict[str, float]] = {}
        current_pages: set = set()

        inside_amendment_sequence = False

        def _collect_for(stripped_line: str) -> None:
            """Collect bbox/page_idx for a line into the current block's layout info."""
            if layout_index is None or not stripped_line:
                return
            lf = self._normalize_for_layout_match(stripped_line)
            for entry in self._lookup_layout_for_line(lf, layout_index):
                page_idx = entry.get("page_idx")
                if entry.get("bbox"):
                    current_bboxes.append(
                        {
                            "bbox": entry["bbox"],
                            "page_idx": page_idx,
                        }
                    )
                if page_idx is not None:
                    current_pages.add(page_idx)
                    if entry.get("page_size") is not None:
                        current_page_sizes[page_idx] = entry["page_size"]

        def flush() -> None:
            nonlocal current_kind
            nonlocal current_title
            nonlocal current_number
            nonlocal current_lines
            nonlocal inside_amendment_sequence
            nonlocal current_bboxes
            nonlocal current_page_sizes
            nonlocal current_pages

            if not current_kind or not current_title:
                return

            content = "\n".join(current_lines).strip()

            if content:
                block: dict = {
                    "kind": current_kind,
                    "title": current_title,
                    "number": current_number,
                    "content": content,
                    "part_title": current_part,
                    "chapter_title": current_chapter,
                    "section_title": current_section,
                    "appendix_title": current_appendix,
                }

                if current_bboxes:
                    # Deduplicate by bbox + page_idx before storing.
                    seen_b: set = set()
                    deduped: List[Dict[str, Any]] = []
                    for b in current_bboxes:
                        bbox = b.get("bbox")
                        page_idx = b.get("page_idx")
                        k = (tuple(bbox) if bbox else None, page_idx)
                        if k not in seen_b:
                            seen_b.add(k)
                            deduped.append(b)
                    block["bboxes"] = deduped

                if current_page_sizes:
                    block["page_sizes"] = dict(sorted(current_page_sizes.items()))

                if current_pages:
                    block["page_indices"] = sorted(current_pages)

                blocks.append(block)

            current_kind = None
            current_title = None
            current_number = None
            current_lines = []
            current_bboxes = []
            current_page_sizes = {}
            current_pages = set()
            inside_amendment_sequence = False

        for raw_line in lines:
            line = self._strip_md_heading(raw_line.strip())

            if not line or self._is_page_number(line):
                continue

            appendix_match = self.APPENDIX_RE.match(line)
            if appendix_match and self._is_real_appendix_heading(line):
                flush()
                current_appendix = line
                current_chapter = None
                current_section = None
                current_kind = "appendix"
                current_title = line
                current_number = appendix_match.group(1)
                current_lines = []
                current_bboxes = []
                current_page_sizes = {}
                current_pages = set()
                _collect_for(line)  # collect for appendix title line
                continue

            part_match = self.PART_RE.match(line)
            if part_match and current_kind != "appendix":
                flush()
                current_part = line
                current_chapter = None
                current_section = None
                continue

            chapter_match = self.CHAPTER_RE.match(line)
            if chapter_match and current_kind != "appendix":
                flush()
                current_chapter = line
                current_section = None
                continue

            section_match = self.SECTION_RE.match(line)
            if section_match and current_kind != "appendix":
                flush()
                current_section = line
                continue

            numbered = self.AMENDMENT_ITEM_RE.match(line)
            if numbered and self._looks_like_amendment_title(numbered.group(2)):
                inside_amendment_sequence = True
                if current_kind:
                    current_lines.append(line)
                    _collect_for(line)
                continue

            article_match = self.ARTICLE_RE.match(line)
            if article_match:
                if inside_amendment_sequence and current_kind == "article":
                    current_lines.append(line)
                    _collect_for(line)
                    continue

                flush()

                current_appendix = None
                current_kind = "article"
                current_title = line
                current_number = article_match.group(1).strip()
                current_lines = []
                current_bboxes = []
                current_page_sizes = {}
                current_pages = set()
                _collect_for(line)  # collect for article title line
                continue

            if current_kind:
                current_lines.append(line)
                _collect_for(line)

        flush()
        return blocks

    # ------------------------------------------------------------------
    # Article parsing
    # ------------------------------------------------------------------

    def _parse_article_block(self, block: dict) -> List[ParsedChunk]:
        article = {
            "part_title": block.get("part_title"),
            "chapter_title": block.get("chapter_title"),
            "section_title": block.get("section_title"),
            "article_title": block["title"],
            "article_number": block["number"],
            "content": block["content"],
        }

        amendment_items = self._split_numbered_amendment_items(article)

        if amendment_items:
            chunks = []
            for item in amendment_items:
                parsed = self._parse_amendment_item(article, item)
                if parsed:
                    chunks.append(parsed)
            self._propagate_block_layout(block, chunks)
            return chunks

        free_form_amendments = self._split_free_form_amendments(article)

        if free_form_amendments:
            chunks = []
            for item in free_form_amendments:
                parsed = self._parse_amendment_item(article, item)
                if parsed:
                    chunks.append(parsed)
            self._propagate_block_layout(block, chunks)
            return chunks

        normal = self._parse_normal_article(article)
        self._propagate_block_layout(block, [normal])

        if len(normal.content) <= self.max_chunk_chars:
            return [normal]

        clause_chunks = self._split_article_by_clauses(article)

        if clause_chunks:
            self._propagate_block_layout(block, clause_chunks)
            return clause_chunks

        return [normal]

    def _split_article_by_clauses(self, article: dict) -> List[ParsedChunk]:
        items = self._split_by_heading_lines(
            article["content"],
            allowed=("clause",),
        )

        if len(items) <= 1:
            return []

        chunks: List[ParsedChunk] = []

        for item in items:
            chunks.append(
                ParsedChunk(
                    chunk_kind="article",
                    title=f'{article["article_title"]} > {item["title"]}',
                    content=self._normalize_content(item["content"]),
                    part_title=article.get("part_title"),
                    chapter_title=article.get("chapter_title"),
                    section_title=article.get("section_title"),
                    article_title=article.get("article_title"),
                    article_number=article.get("article_number"),
                    heading_level=item.get("level"),
                    heading_number=item.get("number"),
                    section_path=f'{article["article_title"]} > {item["title"]}',
                )
            )

        return chunks

    # ------------------------------------------------------------------
    # Appendix parsing
    # ------------------------------------------------------------------

    def _parse_appendix_block(self, block: dict) -> List[ParsedChunk]:
        content = block["content"]
        appendix_title = block["title"]

        items = self._split_by_heading_lines(
            content,
            allowed=("roman", "numbered", "clause"),
        )

        if not items:
            chunks = [
                ParsedChunk(
                    chunk_kind="appendix",
                    title=appendix_title,
                    content=self._normalize_content(content),
                    part_title=block.get("part_title"),
                    appendix_title=appendix_title,
                    appendix_number=block.get("number"),
                    section_path=appendix_title,
                )
            ]
            self._propagate_block_layout(block, chunks)
            return chunks

        chunks: List[ParsedChunk] = []

        for item in items:
            title = f"{appendix_title} > {item['title']}"

            if len(item["content"]) > self.max_chunk_chars:
                sub_items = self._split_by_heading_lines(
                    item["content"],
                    allowed=("point", "bullet"),
                )

                if sub_items:
                    for sub in sub_items:
                        chunks.append(
                            ParsedChunk(
                                chunk_kind="appendix",
                                title=f"{title} > {sub['title']}",
                                content=self._normalize_content(sub["content"]),
                                part_title=block.get("part_title"),
                                appendix_title=appendix_title,
                                appendix_number=block.get("number"),
                                heading_level=sub.get("level"),
                                heading_number=sub.get("number"),
                                section_path=f"{title} > {sub['title']}",
                            )
                        )
                    continue

            chunks.append(
                ParsedChunk(
                    chunk_kind="appendix",
                    title=title,
                    content=self._normalize_content(item["content"]),
                    part_title=block.get("part_title"),
                    appendix_title=appendix_title,
                    appendix_number=block.get("number"),
                    heading_level=item.get("level"),
                    heading_number=item.get("number"),
                    section_path=title,
                )
            )

        self._propagate_block_layout(block, chunks)
        return chunks

    # ------------------------------------------------------------------
    # Generic block parsing
    # ------------------------------------------------------------------

    def _parse_generic_block(self, block: dict) -> List[ParsedChunk]:
        content = block["content"]

        items = self._split_by_heading_lines(
            content,
            allowed=("roman", "numbered", "clause", "point"),
        )

        if not items:
            chunks = [
                ParsedChunk(
                    chunk_kind="section",
                    title=block["title"],
                    content=self._normalize_content(content),
                    part_title=block.get("part_title"),
                    chapter_title=block.get("chapter_title"),
                    section_title=block.get("section_title"),
                    section_path=block["title"],
                )
            ]
            self._propagate_block_layout(block, chunks)
            return chunks

        chunks: List[ParsedChunk] = []

        for item in items:
            title = f"{block['title']} > {item['title']}"

            chunks.append(
                ParsedChunk(
                    chunk_kind="section",
                    title=title,
                    content=self._normalize_content(item["content"]),
                    part_title=block.get("part_title"),
                    chapter_title=block.get("chapter_title"),
                    section_title=block.get("section_title"),
                    heading_level=item.get("level"),
                    heading_number=item.get("number"),
                    section_path=title,
                )
            )

        self._propagate_block_layout(block, chunks)
        return chunks

    # ------------------------------------------------------------------
    # Generic heading splitter
    # ------------------------------------------------------------------

    def _split_by_heading_lines(
        self,
        text: str,
        allowed: tuple[str, ...],
        layout_index: Optional[List[Dict[str, Any]]] = None,
    ) -> List[dict]:
        lines = text.splitlines()
        items: List[dict] = []

        current_title: Optional[str] = None
        current_number: Optional[str] = None
        current_level: Optional[int] = None
        current_lines: List[str] = []

        preface_lines: List[str] = []
        preface_consumed = False

        def flush() -> None:
            nonlocal current_title
            nonlocal current_number
            nonlocal current_level
            nonlocal current_lines
            nonlocal preface_consumed

            if not current_title:
                return

            content_lines: List[str] = []
            if not preface_consumed:
                content_lines.extend(preface_lines)
                preface_consumed = True
            content_lines.extend(current_lines)
            content = "\n".join(content_lines).strip()
            if not content:
                content = current_title

            if content:
                item = {
                    "title": current_title,
                    "number": current_number,
                    "level": current_level,
                    "content": content,
                }
                item.update(
                    self._layout_payload_for_lines(
                        [current_title] + content_lines,
                        layout_index,
                    )
                )
                items.append(item)

            current_title = None
            current_number = None
            current_level = None
            current_lines = []

        for raw_line in lines:
            line = self._strip_md_heading(raw_line.strip())

            if not line or self._is_page_number(line):
                continue

            detected = self._detect_inner_heading(line)

            if detected and detected["kind"] in allowed:
                if self._looks_like_false_heading(line, detected["kind"]):
                    if current_title:
                        current_lines.append(line)
                    else:
                        preface_lines.append(line)
                    continue

                flush()
                current_title = line
                current_number = detected["number"]
                current_level = detected["level"]
                current_lines = []
                continue

            if current_title:
                current_lines.append(line)
            else:
                preface_lines.append(line)

        flush()
        return items

    def _detect_inner_heading(self, line: str) -> Optional[dict]:
        roman = self.ROMAN_HEADING_RE.match(line)
        if roman and roman.group(1).isupper() and self._looks_like_real_heading(line):
            return {
                "kind": "roman",
                "number": roman.group(1),
                "level": 1,
            }

        point = self.POINT_RE.match(line)
        if point:
            return {
                "kind": "point",
                "number": point.group(1),
                "level": 3,
            }

        bullet = self.BULLET_RE.match(line)
        if bullet:
            return {
                "kind": "bullet",
                "number": None,
                "level": 4,
            }

        numbered = self.NUMBERED_HEADING_RE.match(line)
        if numbered and self._looks_like_real_heading(line):
            number = numbered.group(1).strip().rstrip(".")

            if "." in number:
                return {
                    "kind": "numbered",
                    "number": number,
                    "level": len(number.split(".")) + 1,
                }

            return {
                "kind": "clause",
                "number": number,
                "level": 2,
            }

        return None

    def _looks_like_false_heading(self, line: str, kind: str) -> bool:
        lowered = line.lower()

        if len(line) > 180:
            return True

        if lowered.startswith(("1.000", "2.000", "3.000")):
            return True

        if kind in {"clause", "numbered"}:
            if re.match(r"^\d+\.\s*$", line):
                return True

            numbered = self.NUMBERED_HEADING_RE.match(line)
            if numbered:
                raw_number = numbered.group(1).strip()
                has_numbering_dot = raw_number.endswith(".") or bool(
                    re.match(r"^\s*\d+\.", line)
                )

                if raw_number.isdigit() and not has_numbering_dot:
                    number = int(raw_number)
                    folded = self._fold_text(line)
                    address_words = (
                        "duong",
                        "phuong",
                        "quan",
                        "huyen",
                        "tinh",
                        "thanh pho",
                        "nguyen",
                        "tran",
                        "le ",
                    )

                    if number > 20 or any(word in folded for word in address_words):
                        return True

        return False

    # ------------------------------------------------------------------
    # Amendment handling
    # ------------------------------------------------------------------

    def _split_numbered_amendment_items(self, article: dict) -> List[dict]:
        lines = article["content"].splitlines()

        items: List[dict] = []

        current_order: Optional[str] = None
        current_title: Optional[str] = None
        current_lines: List[str] = []

        def flush() -> None:
            nonlocal current_order
            nonlocal current_title
            nonlocal current_lines

            if current_title:
                items.append(
                    {
                        "order_number": current_order,
                        "title": current_title,
                        "content": "\n".join(current_lines).strip(),
                    }
                )

            current_order = None
            current_title = None
            current_lines = []

        for raw_line in lines:
            line = self._strip_md_heading(raw_line.strip())

            if not line or self._is_page_number(line):
                continue

            match = self.AMENDMENT_ITEM_RE.match(line)

            if match and self._looks_like_amendment_title(match.group(2)):
                flush()
                current_order = match.group(1).strip()
                current_title = line
                current_lines = []
                continue

            if current_title:
                current_lines.append(line)

        flush()
        return items

    def _split_free_form_amendments(self, article: dict) -> List[dict]:
        lines = article["content"].splitlines()

        items: List[dict] = []

        current_title: Optional[str] = None
        current_lines: List[str] = []

        def flush() -> None:
            nonlocal current_title
            nonlocal current_lines

            if current_title:
                items.append(
                    {
                        "order_number": None,
                        "title": current_title,
                        "content": "\n".join(current_lines).strip(),
                    }
                )

            current_title = None
            current_lines = []

        for raw_line in lines:
            line = self._strip_md_heading(raw_line.strip())

            if not line or self._is_page_number(line):
                continue

            folded = self._fold_text(line)

            if self.FREE_FORM_AMENDMENT_RE.match(
                line
            ) or self.FREE_FORM_AMENDMENT_ASCII_RE.match(folded):
                flush()
                current_title = line
                current_lines = []
                continue

            if current_title:
                numbered = self.AMENDMENT_ITEM_RE.match(line)

                if numbered and self._looks_like_amendment_title(numbered.group(2)):
                    flush()
                    continue

                current_lines.append(line)

        flush()
        return items

    def _parse_amendment_item(self, article: dict, item: dict) -> Optional[ParsedChunk]:
        title = self._clean_line(item.get("title") or "")
        content = self._normalize_content(item.get("content") or "")

        if not title:
            return None

        title_folded = self._fold_text(title)

        clause_match = self.CLAUSE_ACTION_RE.search(title)
        if not clause_match:
            clause_match = self.CLAUSE_ACTION_ASCII_RE.search(title_folded)

        if clause_match:
            return ParsedChunk(
                chunk_kind="amendment",
                title=title,
                content=content,
                part_title=article.get("part_title"),
                chapter_title=article.get("chapter_title"),
                section_title=article.get("section_title"),
                article_title=article.get("article_title"),
                article_number=article.get("article_number"),
                order_number=item.get("order_number"),
                action=self._normalize_action(clause_match.group(1)),
                target_clause_text=clause_match.group(2).strip(),
                target_article_number=clause_match.group(3).strip(),
            )

        article_match = self.ARTICLE_ACTION_RE.search(title)
        if not article_match:
            article_match = self.ARTICLE_ACTION_ASCII_RE.search(title_folded)

        if article_match:
            return ParsedChunk(
                chunk_kind="amendment",
                title=title,
                content=content,
                part_title=article.get("part_title"),
                chapter_title=article.get("chapter_title"),
                section_title=article.get("section_title"),
                article_title=article.get("article_title"),
                article_number=article.get("article_number"),
                order_number=item.get("order_number"),
                action=self._normalize_action(article_match.group(1)),
                target_article_number=article_match.group(2).strip(),
            )

        rename_match = self.RENAME_RE.search(title)
        if not rename_match:
            rename_match = self.RENAME_ASCII_RE.search(title_folded)

        if rename_match:
            return ParsedChunk(
                chunk_kind="amendment",
                title=title,
                content=content,
                part_title=article.get("part_title"),
                chapter_title=article.get("chapter_title"),
                section_title=article.get("section_title"),
                article_title=article.get("article_title"),
                article_number=article.get("article_number"),
                order_number=item.get("order_number"),
                action="rename",
            )

        legal_action_patterns = [
            r"(sửa đổi|bổ sung|thay thế|bãi bỏ)\s+(điều|khoản|điểm)",
            r"(sua doi|bo sung|thay the|bai bo)\s+(dieu|khoan|diem)",
        ]

        if any(re.search(p, title_folded, re.I) for p in legal_action_patterns):
            return ParsedChunk(
                chunk_kind="amendment",
                title=title,
                content=content,
                part_title=article.get("part_title"),
                chapter_title=article.get("chapter_title"),
                section_title=article.get("section_title"),
                article_title=article.get("article_title"),
                article_number=article.get("article_number"),
                order_number=item.get("order_number"),
                action=self._guess_action(title),
            )

        return None

    def _parse_normal_article(self, article: dict) -> ParsedChunk:
        return ParsedChunk(
            chunk_kind="article",
            title=article["article_title"],
            content=self._normalize_content(article["content"]),
            part_title=article.get("part_title"),
            chapter_title=article.get("chapter_title"),
            section_title=article.get("section_title"),
            article_title=article.get("article_title"),
            article_number=article.get("article_number"),
            section_path=article["article_title"],
        )

    # ------------------------------------------------------------------
    # Fallback numbered heading parser
    # ------------------------------------------------------------------

    def _parse_by_numbered_headings(
        self,
        text: str,
        layout_index: Optional[List[Dict[str, Any]]] = None,
    ) -> List[ParsedChunk]:
        items = self._split_by_heading_lines(
            text,
            allowed=("roman", "numbered", "clause"),
            layout_index=layout_index,
        )

        chunks: List[ParsedChunk] = []

        for item in items:
            chunks.append(
                ParsedChunk(
                    chunk_kind="section",
                    title=item["title"],
                    content=self._normalize_content(item["content"]),
                    heading_level=item.get("level"),
                    heading_number=item.get("number"),
                    section_path=item["title"],
                    bboxes=item.get("bboxes"),
                    page_sizes=item.get("page_sizes"),
                    page_indices=item.get("page_indices"),
                )
            )

        return chunks

    # ------------------------------------------------------------------
    # Normalize / utility
    # ------------------------------------------------------------------

    def _html_tables_to_markdown(self, text: str) -> str:
        def clean_cell(s: str) -> str:
            s = unescape(s)
            s = re.sub(r"\s+", " ", s).strip()
            return s.replace("|", r"\|")

        def table_to_grid(table):
            grid = []
            rowspan_map = {}

            for r_idx, tr in enumerate(table.find_all("tr")):
                row = []
                c_idx = 0

                while (r_idx, c_idx) in rowspan_map:
                    row.append(rowspan_map.pop((r_idx, c_idx)))
                    c_idx += 1

                for cell in tr.find_all(["td", "th"]):
                    while (r_idx, c_idx) in rowspan_map:
                        row.append(rowspan_map.pop((r_idx, c_idx)))
                        c_idx += 1

                    text = clean_cell(cell.get_text(" ", strip=True))
                    colspan = int(cell.get("colspan", 1) or 1)
                    rowspan = int(cell.get("rowspan", 1) or 1)

                    for dc in range(colspan):
                        row.append(text if dc == 0 else "")

                        if rowspan > 1:
                            for dr in range(1, rowspan):
                                rowspan_map[(r_idx + dr, c_idx + dc)] = (
                                    text if dc == 0 else ""
                                )

                    c_idx += colspan

                grid.append(row)

            max_cols = max(len(r) for r in grid)
            return [r + [""] * (max_cols - len(r)) for r in grid]

        def convert_table(match: re.Match) -> str:
            soup = BeautifulSoup(match.group(0), "html.parser")
            table = soup.find("table")
            if not table:
                return match.group(0)

            rows = table_to_grid(table)
            if not rows:
                return match.group(0)

            if len(rows) >= 2:
                header = []
                for a, b in zip(rows[0], rows[1]):
                    if a and b and a != b:
                        header.append(f"{a} - {b}")
                    else:
                        header.append(a or b)
                body = rows[2:]
            else:
                header = rows[0]
                body = rows[1:]

            md = []
            md.append("| " + " | ".join(header) + " |")
            md.append("| " + " | ".join(["---"] * len(header)) + " |")

            for row in body:
                md.append("| " + " | ".join(row) + " |")

            return "\n" + "\n".join(md) + "\n"

        return re.sub(
            r"<table\b.*?</table>",
            convert_table,
            text,
            flags=re.I | re.S,
        )

    def _is_real_appendix_heading(self, line: str) -> bool:
        line = self._clean_line(line)

        if len(line) > 50:
            return False

        if "(" in line or ")" in line:
            return False

        folded = self._fold_text(line)

        if re.search(
            r"\b(theo|xem|tai|quy dinh tai|duoc quy dinh tai|ban hanh kem)\b",
            folded,
            re.I,
        ):
            return False

        return bool(self.APPENDIX_RE.match(line))

    def _break_inline_headings(self, text: str) -> str:
        """
        Chỉ bẻ dòng heading Điều thật.
        Không bẻ các tham chiếu inline kiểu:
        - theo Điều 6.
        - tại Điều 7.
        - quy định tại Điều 8.
        - theo Phụ lục II
        """

        article_pattern = re.compile(
            r"(?<!^)(?<!\n)(\s+)"
            r"((?:ĐIỀU|Điều|điều|DIEU|Dieu|dieu)"
            r"\s+\d+[a-zA-Z]?\s*[.:]\s*)",
            re.I,
        )

        def repl(match: re.Match) -> str:
            space = match.group(1)
            heading = match.group(2)

            start = match.start()
            before = text[max(0, start - 80) : start]
            before_folded = self._fold_text(before)

            # Không bẻ nếu là tham chiếu inline
            inline_ref_patterns = [
                r"\btheo\s*$",
                r"\btai\s*$",
                r"\bxem\s*$",
                r"\bcan\s+cu\s*$",
                r"\bquy\s+dinh\s+tai\s*$",
                r"\bneu\s+tai\s*$",
                r"\bduoc\s+quy\s+dinh\s+tai\s*$",
            ]

            if any(re.search(p, before_folded, re.I) for p in inline_ref_patterns):
                return space + heading

            return "\n" + heading

        return article_pattern.sub(repl, text)

    def _strip_md_heading(self, line: str) -> str:
        return re.sub(r"^\s*#{1,6}\s*", "", line).strip()

    def _break_appendix_inline_title(self, text: str) -> str:
        fixed_lines = []

        pattern = re.compile(
            r"^\s*((?:Phụ\s*lục|PHỤ\s*LỤC|phu\s*luc)\s+([IVXLCDM]+|\d+))\s+(.+)$",
            re.I,
        )

        numbered_tail = re.compile(r"^(.*?)(\s+\d+\.\s+.+)$", re.S)

        for raw_line in text.splitlines():
            line = raw_line.strip()

            m = pattern.match(line)

            if not m:
                fixed_lines.append(raw_line)
                continue

            appendix_title = m.group(1).strip()
            rest = m.group(3).strip()

            fixed_lines.append(appendix_title)

            tail = numbered_tail.match(rest)

            if tail:
                main_title = tail.group(1).strip()
                numbered_heading = tail.group(2).strip()

                if main_title:
                    fixed_lines.append(main_title)

                fixed_lines.append(numbered_heading)
            else:
                fixed_lines.append(rest)

        return "\n".join(fixed_lines)

    def _looks_like_amendment_title(self, text: str) -> bool:
        folded = self._fold_text(text)

        patterns = [
            r"(sửa đổi|bổ sung|thay thế|bãi bỏ)\s+(điều|khoản|điểm)\s+\d+",
            r"(sua doi|bo sung|thay the|bai bo)\s+(dieu|khoan|diem)\s+\d+",
        ]

        return any(re.search(p, folded, re.I) for p in patterns)

    def _looks_like_real_heading(self, line: str) -> bool:
        if len(line) > 180:
            return False

        lowered = line.lower()

        if lowered.startswith(("1.000", "2.000", "3.000")):
            return False

        return True

    def _normalize_action(self, text: str) -> str:
        folded = self._fold_text(text)

        if "sua doi" in folded:
            return "modify"

        if "bo sung" in folded:
            return "supplement"

        if "thay the" in folded:
            return "replace"

        if "bai bo" in folded:
            return "repeal"

        return "unknown"

    def _guess_action(self, text: str) -> str:
        return self._normalize_action(text)

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _normalize_content(self, text: str) -> str:
        text = self._normalize_text(text)
        text = re.sub(r"^\s+", "", text)
        text = re.sub(r"\s+$", "", text)
        return text

    def _clean_line(self, line: str) -> str:
        return re.sub(r"\s+", " ", line).strip()

    def _fold_text(self, text: str) -> str:
        text = unicodedata.normalize("NFD", text)
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        text = text.replace("đ", "d").replace("Đ", "D")
        return text.lower()

    def _is_page_number(self, line: str) -> bool:
        return bool(re.fullmatch(r"\d{1,3}", line.strip()))

    def _extract_fallback_title(self, text: str) -> str:
        for line in text.splitlines():
            line = self._strip_md_heading(line.strip())
            if line and not self._is_page_number(line):
                return line[:180]
        return "Untitled"

    def _normalize_footnote_markers(self, text: str) -> str:
        """
        OCR/PDF hay tạo kiểu:
        2.8 Đối với các học phần Anh văn
        5.11 Đối với các học phần Tiếng Anh
        => sửa thành:
        2. Đối với các học phần Anh văn
        5. Đối với các học phần Tiếng Anh
        """

        fixed_lines = []

        for line in text.splitlines():
            line = re.sub(
                r"^(\s*\d+)\.\d{1,2}\s+((?:Đối|Doi|Trường|Truong|Sinh|Nếu|Neu|Chứng|Chung|Thời|Thoi)\b)",
                r"\1. \2",
                line,
                flags=re.I,
            )
            fixed_lines.append(line)

        return "\n".join(fixed_lines)

    def _html_blocks_to_text(self, text: str) -> str:
        """
        Chuyển các block HTML còn sót lại như div/p/center/h1-h6 thành text.
        Mục đích:
        - <div>Phụ lục II</div> -> dòng riêng "Phụ lục II"
        - giúp APPENDIX_RE detect được phụ lục mới
        """

        def convert_block(match: re.Match) -> str:
            html = match.group(0)
            soup = BeautifulSoup(html, "html.parser")
            content = soup.get_text(" ", strip=True)

            if not content:
                return "\n"

            return f"\n{content}\n"

        text = re.sub(
            r"<(?:div|p|center|h[1-6])\b[^>]*>.*?</(?:div|p|center|h[1-6])>",
            convert_block,
            text,
            flags=re.I | re.S,
        )

        # Xóa tag HTML lẻ còn sót lại, nhưng giữ text bên trong nếu có
        text = re.sub(r"</?(?:span|strong|b|i|em|u)\b[^>]*>", "", text, flags=re.I)

        return text

    def _normalize_ocr_errors(self, text: str) -> str:
        def looks_like_legal_action(after: str) -> bool:
            folded = self._fold_text(after.lower())

            fuzzy_patterns = (
                r"s\w{0,2}a\s+d\w{0,2}i",
                r"b\w{0,2}\s+sung",
                r"b\w{0,2}i\s+b\w{0,2}",
                r"thay\s+th\w{0,2}",
                r"dieu\s+\d+",
                r"khoan\s+.+?\s+dieu\s+\d+",
            )

            return any(re.search(p, folded, re.I) for p in fuzzy_patterns)

        text = re.sub(
            r"\b(điểu|diểu|diều|dieu)\s+(\d+[a-zA-Z]?)\b",
            r"Điều \2",
            text,
            flags=re.I,
        )

        fixed_lines = []

        for line in text.splitlines():
            m = re.match(r"^\s*§\s*\.?\s*(.+)$", line)

            if m and looks_like_legal_action(m.group(1)):
                line = re.sub(r"^\s*§\s*\.?\s*", "8. ", line)

            if "§" in line and not line.lstrip().startswith("§"):

                def inline_repl(match: re.Match) -> str:
                    after = match.group(1)
                    if looks_like_legal_action(after):
                        return "\n8. " + after
                    return match.group(0)

                line = re.sub(r"\s*§\s*\.?\s*(.+)$", inline_repl, line)

            fixed_lines.append(line)

        return "\n".join(fixed_lines)

    def _post_process(self, chunks: List[ParsedChunk]) -> List[ParsedChunk]:
        cleaned: List[ParsedChunk] = []

        for chunk in chunks:
            title = self._clean_line(chunk.title or "")
            content = self._normalize_content(chunk.content or "")

            if not title and not content:
                continue

            chunk.title = title
            chunk.content = content

            if not chunk.content:
                continue

            cleaned.append(chunk)

        return self._merge_small_section_chunks(cleaned)

    def _merge_small_section_chunks(
        self, chunks: List[ParsedChunk]
    ) -> List[ParsedChunk]:
        if self.min_section_chunk_chars <= 0:
            return chunks

        merged: List[ParsedChunk] = []
        pending: Optional[ParsedChunk] = None

        def flush_pending() -> None:
            nonlocal pending
            if pending is not None:
                merged.append(pending)
                pending = None

        for chunk in chunks:
            if chunk.chunk_kind != "section":
                flush_pending()
                merged.append(chunk)
                continue

            if pending is None:
                pending = chunk
                continue

            if self._should_merge_section_chunks(pending, chunk):
                pending = self._combine_section_chunks(pending, chunk)
                continue

            flush_pending()
            pending = chunk

        flush_pending()
        return merged

    def _should_merge_section_chunks(
        self,
        left: ParsedChunk,
        right: ParsedChunk,
    ) -> bool:
        if left.chunk_kind != "section" or right.chunk_kind != "section":
            return False

        if right.heading_level == 1:
            return False

        if (
            left.heading_level is not None
            and right.heading_level is not None
            and right.heading_level < left.heading_level
        ):
            return False

        combined_len = len(left.content) + len(right.content) + len(right.title) + 2
        if combined_len > self.max_chunk_chars:
            return False

        return len(left.content) < self.min_section_chunk_chars

    def _combine_section_chunks(
        self,
        left: ParsedChunk,
        right: ParsedChunk,
    ) -> ParsedChunk:
        right_content = self._content_with_title(right)
        left.content = self._normalize_content(
            "\n\n".join(part for part in [left.content, right_content] if part)
        )

        if left.section_path and right.section_path:
            left.section_path = f"{left.section_path} > {right.section_path}"
        elif right.section_path:
            left.section_path = right.section_path

        left.bboxes = self._merge_bboxes(left.bboxes, right.bboxes)
        left.page_sizes = self._merge_page_sizes(left.page_sizes, right.page_sizes)
        left.page_indices = self._merge_page_indices(
            left.page_indices,
            right.page_indices,
        )

        return left

    def _content_with_title(self, chunk: ParsedChunk) -> str:
        return self._normalize_content(
            "\n".join(part for part in [chunk.title, chunk.content] if part)
        )

    def _merge_bboxes(
        self,
        left: Optional[List[Dict[str, Any]]],
        right: Optional[List[Dict[str, Any]]],
    ) -> Optional[List[Dict[str, Any]]]:
        if not left and not right:
            return None

        merged: List[Dict[str, Any]] = []
        seen: set = set()

        for item in (left or []) + (right or []):
            bbox = item.get("bbox")
            page_idx = item.get("page_idx")
            key = (tuple(bbox) if bbox else None, page_idx)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)

        return merged

    def _merge_page_sizes(
        self,
        left: Optional[Dict[int, Dict[str, float]]],
        right: Optional[Dict[int, Dict[str, float]]],
    ) -> Optional[Dict[int, Dict[str, float]]]:
        if not left and not right:
            return None

        merged = dict(left or {})
        merged.update(right or {})
        return dict(sorted(merged.items()))

    def _merge_page_indices(
        self,
        left: Optional[List[int]],
        right: Optional[List[int]],
    ) -> Optional[List[int]]:
        if not left and not right:
            return None
        return sorted(set(left or []) | set(right or []))
