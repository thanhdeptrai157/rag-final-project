from pathlib import Path
from typing import Any

import fitz
import pytesseract
from PIL import Image, ImageFilter, ImageOps

from app.schemas.document import Document

pytesseract.pytesseract.tesseract_cmd = r"D:\Program Files\Tesseract-OCR\tesseract.exe"


class PDFLoader:
    def __init__(
        self,
        enable_ocr: bool = True,
        force_ocr: bool = False,
        ocr_lang: str = "vie+eng",
        ocr_dpi: int = 300,
        min_text_length: int = 20,
        preprocess_for_ocr: bool = True,
    ) -> None:
        self.enable_ocr = enable_ocr
        self.force_ocr = force_ocr
        self.ocr_lang = ocr_lang
        self.ocr_dpi = ocr_dpi
        self.min_text_length = min_text_length
        self.preprocess_for_ocr = preprocess_for_ocr

    def load(self, file_path: str | Path) -> Document:
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File {file_path} does not exist.")

        doc = fitz.open(str(path))
        page_texts: list[str] = []
        ocr_pages: list[int] = []

        try:
            for page_num, page in enumerate(doc):
                extracted_text = (page.get_text("text") or "").strip()

                should_ocr = self.enable_ocr and (
                    self.force_ocr or self._should_use_ocr(extracted_text)
                )

                if should_ocr:
                    ocr_text = self._ocr_page(page).strip()
                    if ocr_text:
                        extracted_text = ocr_text
                        ocr_pages.append(page_num + 1)

                page_texts.append(extracted_text)

            raw_text = "\n\n".join(page_texts).strip()
            title = self._extract_title(doc, path, page_texts)

            return Document(
                doc_id=self._build_doc_id(path),
                source_path=str(path),
                source_type="pdf",
                title=title,
                raw_text=raw_text,
                metadata={
                    "file_name": path.name,
                    "page_count": len(page_texts),
                    "pages": page_texts,
                    "ocr_enabled": self.enable_ocr,
                    "force_ocr": self.force_ocr,
                    "ocr_lang": self.ocr_lang,
                    "ocr_dpi": self.ocr_dpi,
                    "ocr_pages": ocr_pages,
                },
            )
        finally:
            doc.close()

    def _build_doc_id(self, path: Path) -> str:
        return path.stem.lower().replace(" ", "_")

    def _extract_title(
        self,
        doc: fitz.Document,
        path: Path,
        page_texts: list[str],
    ) -> str:
        meta: dict[str, Any] = doc.metadata or {}
        meta_title = (meta.get("title") or "").strip()
        if meta_title:
            return meta_title

        first_page = page_texts[0] if page_texts else ""
        lines = [line.strip() for line in first_page.splitlines() if line.strip()]

        for line in lines[:10]:
            if len(line) > 12:
                return line

        return path.stem

    def _should_use_ocr(self, text: str) -> bool:
        return len(text.strip()) < self.min_text_length

    def _ocr_page(self, page: fitz.Page) -> str:
        zoom = self.ocr_dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        mode = "RGB" if pix.n < 4 else "RGBA"
        image = Image.frombytes(mode, [pix.width, pix.height], pix.samples)

        if mode == "RGBA":
            image = image.convert("RGB")

        if self.preprocess_for_ocr:
            image = self._preprocess_image_for_ocr(image)

        return pytesseract.image_to_string(
            image,
            lang=self.ocr_lang,
            config="--oem 3 --psm 6",
        )

    def _preprocess_image_for_ocr(self, image: Image.Image) -> Image.Image:
        image = ImageOps.grayscale(image)
        image = image.filter(ImageFilter.SHARPEN)
        image = ImageOps.autocontrast(image)
        return image