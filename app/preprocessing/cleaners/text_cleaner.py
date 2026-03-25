import re
from typing import List


class TextCleaner:
    """
    Làm sạch text OCR ở mức cơ bản để phục vụ detect cấu trúc văn bản pháp lý.
    Chưa sửa lỗi OCR sâu, chỉ tập trung:
    - chuẩn hóa whitespace
    - bỏ dòng rỗng thừa
    - nối dòng bị ngắt vô lý
    """

    CHAPTER_RE = re.compile(r"\b(chương|chuong)\s+[ivxlcdm0-9]+\b", re.IGNORECASE)
    SECTION_RE = re.compile(r"\b(mục|muc|mic)\s+\d+\b", re.IGNORECASE)
    ARTICLE_RE = re.compile(r"\b(điều|dieu)\s+\d+\b", re.IGNORECASE)

    BULLET_RE = re.compile(r"^\s*(\d+\.|[a-z]\)|-|\+)\s+")

    def clean(self, text: str) -> str:
        if not text:
            return ""

        text = self._normalize_newlines(text)
        text = self._normalize_spaces(text)
        lines = self._split_lines(text)
        lines = self._strip_lines(lines)
        lines = self._remove_extra_empty_lines(lines)
        lines = self._merge_broken_lines(lines)
        text = "\n".join(lines)
        text = self._final_cleanup(text)
        return text

    def _normalize_newlines(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        return text

    def _normalize_spaces(self, text: str) -> str:
        # thay tab thành space
        text = text.replace("\t", " ")
        # gom nhiều space liên tiếp thành 1
        text = re.sub(r"[ \xa0]+", " ", text)
        return text

    def _split_lines(self, text: str) -> List[str]:
        return text.split("\n")

    def _strip_lines(self, lines: List[str]) -> List[str]:
        return [line.strip() for line in lines]

    def _remove_extra_empty_lines(self, lines: List[str]) -> List[str]:
        cleaned = []
        prev_empty = False

        for line in lines:
            is_empty = not line
            if is_empty and prev_empty:
                continue
            cleaned.append(line)
            prev_empty = is_empty

        return cleaned

    def _merge_broken_lines(self, lines: List[str]) -> List[str]:
        """
        Nối các dòng bị xuống hàng vô lý do OCR/PDF extraction.
        Giữ nguyên khi gặp heading như Chương / Mục / Điều.
        """
        if not lines:
            return []

        merged: List[str] = []
        buffer = ""

        for line in lines:
            if not line:
                if buffer:
                    merged.append(buffer.strip())
                    buffer = ""
                merged.append("")
                continue

            if self._is_heading(line):
                if buffer:
                    merged.append(buffer.strip())
                    buffer = ""
                merged.append(line)
                continue

            if not buffer:
                buffer = line
                continue

            if self._should_merge(buffer, line):
                buffer = f"{buffer} {line}"
            else:
                merged.append(buffer.strip())
                buffer = line

        if buffer:
            merged.append(buffer.strip())

        return merged

    def _is_heading(self, line: str) -> bool:
        return bool(
            self.CHAPTER_RE.match(line)
            or self.SECTION_RE.match(line)
            or self.ARTICLE_RE.match(line)
        )

    def _should_merge(self, prev_line: str, current_line: str) -> bool:
        """
        Rule đơn giản:
        - nếu dòng trước chưa kết thúc câu -> có xu hướng merge
        - nếu dòng hiện tại bắt đầu bằng bullet/heading -> không merge
        """
        if self._is_heading(current_line):
            return False

        if self.BULLET_RE.match(current_line):
            return False

        if prev_line.endswith((".", ":", ";", "?", "!")):
            return False

        return True

    def _final_cleanup(self, text: str) -> str:
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ ]{2,}", " ", text)
        return text.strip()