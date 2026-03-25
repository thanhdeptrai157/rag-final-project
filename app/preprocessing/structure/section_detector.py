import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class DetectedSection:
    level: str
    title: str
    line_index: int
    number: Optional[str] = None


class SectionDetector:
    CHAPTER_RE = re.compile(
        r"^\s*(chương\s+([ivxlcdm0-9]+)\s*[:.\-]?\s*.*)$",
        re.IGNORECASE
    )

    SECTION_RE = re.compile(
        r"^\s*(mục\s+(\d+)\s*[:.\-]?\s*.*)$",
        re.IGNORECASE
    )

    ARTICLE_RE = re.compile(
        r"^\s*(điều\s+(\d+)\s*[:.\-]?\s*.*)$",
        re.IGNORECASE
    )

    def detect(self, text: str) -> List[DetectedSection]:
        lines = text.splitlines()
        sections: List[DetectedSection] = []

        for idx, raw_line in enumerate(lines):
            line = raw_line.strip()
            if not line:
                continue

            m = self.CHAPTER_RE.match(line)
            if m:
                sections.append(
                    DetectedSection(
                        level="chapter",
                        title=m.group(1).strip(),
                        line_index=idx,
                        number=m.group(2).strip(),
                    )
                )
                continue

            m = self.SECTION_RE.match(line)
            if m:
                sections.append(
                    DetectedSection(
                        level="section",
                        title=m.group(1).strip(),
                        line_index=idx,
                        number=m.group(2).strip(),
                    )
                )
                continue

            m = self.ARTICLE_RE.match(line)
            if m:
                sections.append(
                    DetectedSection(
                        level="article",
                        title=m.group(1).strip(),
                        line_index=idx,
                        number=m.group(2).strip(),
                    )
                )

        return sections