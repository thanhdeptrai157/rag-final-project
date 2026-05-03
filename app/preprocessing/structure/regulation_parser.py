from dataclasses import dataclass
from typing import List, Optional

from app.preprocessing.structure.section_detector import SectionDetector


@dataclass
class ParsedArticle:
    chapter_title: Optional[str]
    section_title: Optional[str]
    article_title: str
    article_number: Optional[str]
    content: str


class RegulationParser:
    def __init__(self) -> None:
        self.section_detector = SectionDetector()

    def extract_title(self, text: str) -> Optional[str]:
        """
        Lấy tiêu đề văn bản từ khoảng 20 dòng đầu.
        Bỏ qua các dòng quá ngắn hoặc chỉ là quốc hiệu / số hiệu đơn lẻ.
        """
        lines = text.splitlines()[:20]

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if len(line) < 10 or len(line) > 200:
                continue

            lowered = line.lower()
            if lowered.startswith(("số:", "so:", "cộng hòa", "độc lập", "địa chỉ", "cong hoa", "doc lap", "dia chi")):
                continue

            return line

        return None

    def parse(self, text: str) -> List[ParsedArticle]:
        lines = text.splitlines()
        detected = self.section_detector.detect(text)

        if not detected:
            return []

        articles: List[ParsedArticle] = []

        current_chapter: Optional[str] = None
        current_section: Optional[str] = None

        article_chapter: Optional[str] = None
        article_section: Optional[str] = None

        current_article_title: Optional[str] = None
        current_article_number: Optional[str] = None
        current_lines: List[str] = []

        detected_map = {d.line_index: d for d in detected}

        def flush_article() -> None:
            nonlocal current_article_title
            nonlocal current_article_number
            nonlocal current_lines
            nonlocal article_chapter
            nonlocal article_section

            if not current_article_title:
                return

            content = "\n".join(
                line.strip()
                for line in current_lines
                if line and line.strip()
            ).strip()

            articles.append(
                ParsedArticle(
                    chapter_title=article_chapter,
                    section_title=article_section,
                    article_title=current_article_title,
                    article_number=current_article_number,
                    content=content,
                )
            )

            current_article_title = None
            current_article_number = None
            current_lines = []
            article_chapter = None
            article_section = None

        for idx, raw_line in enumerate(lines):
            line = raw_line.strip()
            item = detected_map.get(idx)

            if item:
                if item.level == "chapter":
                    # gặp chương mới thì đóng điều hiện tại trước
                    flush_article()
                    current_chapter = item.title
                    current_section = None
                    continue

                if item.level == "section":
                    # gặp mục mới thì đóng điều hiện tại trước
                    flush_article()
                    current_section = item.title
                    continue

                if item.level == "article":
                    # đóng điều trước đó
                    flush_article()

                    current_article_title = item.title
                    current_article_number = item.number
                    current_lines = []

                    # chụp chapter/section tại thời điểm mở điều này
                    article_chapter = current_chapter
                    article_section = current_section
                    continue

            if current_article_title and line:
                current_lines.append(line)

        flush_article()

        return self._post_process_articles(articles)

    def _post_process_articles(self, articles: List[ParsedArticle]) -> List[ParsedArticle]:
        """
        Hậu xử lý nhẹ:
        - bỏ article rỗng
        - bỏ article OCR lỗi quá nặng
        """
        cleaned: List[ParsedArticle] = []

        for article in articles:
            title = (article.article_title or "").strip()
            content = (article.content or "").strip()

            if not title:
                continue

            if not content:
                continue

            # lọc tiêu đề điều quá bẩn do OCR
            if len(title) > 250:
                continue

            cleaned.append(article)

        return cleaned