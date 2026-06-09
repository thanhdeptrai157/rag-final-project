import json
import os
import time
from pathlib import Path
from typing import Any

import fitz
import requests

from app.schemas.document import Document

JOB_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
MODEL = "PaddleOCR-VL-1.5"


class PDFLoader:
    def __init__(
        self,
        enable_ocr: bool = True,
        force_ocr: bool = False,
        token: str | None = None,
        model: str | None = None,
        poll_interval: int = 5,
    ) -> None:
        self.enable_ocr = enable_ocr
        self.force_ocr = force_ocr
        self.token = token or os.getenv("PADDLE_OCR_TOKEN")
        self.model = model or MODEL
        self.poll_interval = poll_interval

        if not self.token:
            raise RuntimeError(
                "Paddle OCR token not provided. Set PADDLE_OCR_TOKEN env var."
            )

    def load(self, file_path: str | Path) -> Document:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Build headers and payload
        headers = {"Authorization": f"bearer {self.token}"}
        optional_payload = {
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useChartRecognition": False,
        }

        # Upload file and create job
        data = {"model": self.model, "optionalPayload": json.dumps(optional_payload)}
        with open(path, "rb") as f:
            files = {"file": f}
            resp = requests.post(JOB_URL, headers=headers, data=data, files=files)

        if resp.status_code != 200:
            raise RuntimeError(
                f"Paddle OCR job submission failed: {resp.status_code} {resp.text}"
            )

        job_id = resp.json()["data"]["jobId"]

        # poll for completion
        jsonl_url = ""
        while True:
            job_resp = requests.get(f"{JOB_URL}/{job_id}", headers=headers)
            if job_resp.status_code != 200:
                raise RuntimeError(
                    f"Failed to get job status: {job_resp.status_code} {job_resp.text}"
                )

            state = job_resp.json()["data"].get("state")
            if state == "done":
                jsonl_url = job_resp.json()["data"]["resultUrl"]["jsonUrl"]
                break
            if state == "failed":
                error_msg = job_resp.json()["data"].get("errorMsg")
                raise RuntimeError(
                    f"Paddle OCR job failed: {error_msg}"
                )

            time.sleep(self.poll_interval)

        # download and parse result
        jsonl_resp = requests.get(jsonl_url)
        jsonl_resp.raise_for_status()
        lines = [ln for ln in jsonl_resp.text.splitlines() if ln.strip()]

        page_texts: list[str] = []
        ocr_pages: list[int] = []
        for line in lines:
            obj = json.loads(line)
            result = obj.get("result") or {}
            for i, res in enumerate(result.get("layoutParsingResults", [])):
                markdown = (res.get("markdown") or {}).get("text") or ""
                page_texts.append(markdown)
                if markdown.strip():
                    ocr_pages.append(len(page_texts))

        raw_text = "\n\n".join(page_texts).strip()

        # try to extract title and page count using fitz
        try:
            doc = fitz.open(str(path))
            page_count = doc.page_count
            metadata: dict[str, Any] = doc.metadata or {}
            meta_title = (metadata.get("title") or "").strip()
            doc.close()
        except Exception:
            page_count = len(page_texts)
            metadata = {}
            meta_title = ""

        title = meta_title or path.stem

        return Document(
            doc_id=self._build_doc_id(path),
            source_path=str(path),
            source_type="pdf",
            title=title,
            raw_text=raw_text,
            metadata={
                "file_name": path.name,
                "page_count": page_count,
                "pages": page_texts,
                "ocr_enabled": self.enable_ocr,
                "force_ocr": self.force_ocr,
                "ocr_pages": ocr_pages,
                "paddle_job_id": job_id,
            },
        )

    def _build_doc_id(self, path: Path) -> str:
        return path.stem.lower().replace(" ", "_")
