import io
import json
import os
import time
import zipfile
from pathlib import Path
from typing import Any

import fitz
import requests

from app.schemas.document import Document

MINERU_APPLY_UPLOAD_URL = "https://mineru.net/api/v4/file-urls/batch"
MINERU_BATCH_RESULT_URL = "https://mineru.net/api/v4/extract-results/batch"

MINERU_MODEL = "vlm"


class MinerUPDFLoader:
    def __init__(
        self,
        enable_ocr: bool = True,
        force_ocr: bool = False,
        token: str | None = None,
        model: str | None = None,
        poll_interval: int = 5,
        enable_formula: bool = True,
        enable_table: bool = True,
        artifact_dir: str | Path = "output/mineru",
        store_layout_in_metadata: bool = False,
    ) -> None:
        self.enable_ocr = enable_ocr
        self.force_ocr = force_ocr
        self.token = token or os.getenv("MINERU_TOKEN")
        self.model = model or MINERU_MODEL
        self.poll_interval = poll_interval
        self.enable_formula = enable_formula
        self.enable_table = enable_table
        self.artifact_dir = Path(artifact_dir)
        self.store_layout_in_metadata = store_layout_in_metadata

        if not self.token:
            raise RuntimeError("MinerU token not provided. Set MINERU_TOKEN env var.")

    def load(self, file_path: str | Path) -> Document:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        batch_id = self._submit_local_file(path)
        result_item = self._poll_batch_result(batch_id, path.name)

        full_zip_url = result_item["full_zip_url"]

        extracted = self._extract_core_artifacts(
            full_zip_url=full_zip_url,
            source_path=path,
        )

        raw_markdown = extracted["raw_markdown"]
        layout_json = extracted["layout_json"]

        page_texts = self._build_pages_from_layout(layout_json)
        if not page_texts and raw_markdown:
            page_texts = [raw_markdown]

        ocr_pages = [idx + 1 for idx, text in enumerate(page_texts) if text.strip()]

        try:
            pdf_doc = fitz.open(str(path))
            page_count = pdf_doc.page_count
            pdf_metadata: dict[str, Any] = pdf_doc.metadata or {}
            meta_title = (pdf_metadata.get("title") or "").strip()
            pdf_doc.close()
        except Exception:
            page_count = len(page_texts)
            pdf_metadata = {}
            meta_title = ""

        title = meta_title or path.stem

        metadata: dict[str, Any] = {
            "file_name": path.name,
            "page_count": page_count,
            "pages": page_texts,
            "ocr_enabled": self.enable_ocr,
            "force_ocr": self.force_ocr,
            "ocr_pages": ocr_pages,
            # MinerU info
            "mineru_batch_id": batch_id,
            "mineru_model": self.model,
            "mineru_state": result_item.get("state"),
            "mineru_full_zip_url": full_zip_url,
            "mineru_layout_path": extracted["layout_path"],
            "artifact_dir": extracted["artifact_dir"],
        }

        if self.store_layout_in_metadata:
            metadata["layout"] = layout_json

        return Document(
            doc_id=self._build_doc_id(path),
            source_path=str(path),
            source_type="pdf",
            title=title,
            raw_text=raw_markdown,
            metadata=metadata,
        )

    def _submit_local_file(self, path: Path) -> str:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

        payload: dict[str, Any] = {
            "files": [
                {
                    "name": path.name,
                    "data_id": path.name,
                    "is_ocr": self.enable_ocr,
                }
            ],
            "model_version": self.model,
            "enable_formula": self.enable_formula,
            "enable_table": self.enable_table,
        }

        resp = requests.post(
            MINERU_APPLY_UPLOAD_URL,
            headers=headers,
            json=payload,
            timeout=60,
        )
        body = self._check_mineru_response(resp, "MinerU upload URL request failed")

        batch_id = body["data"]["batch_id"]
        upload_url = body["data"]["file_urls"][0]

        with open(path, "rb") as f:
            upload_resp = requests.put(upload_url, data=f, timeout=300)

        if upload_resp.status_code != 200:
            raise RuntimeError(
                f"MinerU file upload failed: "
                f"{upload_resp.status_code} {upload_resp.text}"
            )

        return batch_id

    def _poll_batch_result(self, batch_id: str, file_name: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.token}"}

        while True:
            resp = requests.get(
                f"{MINERU_BATCH_RESULT_URL}/{batch_id}",
                headers=headers,
                timeout=60,
            )
            body = self._check_mineru_response(resp, "MinerU batch polling failed")

            results = body.get("data", {}).get("extract_result", [])
            if not results:
                time.sleep(self.poll_interval)
                continue

            item = next(
                (x for x in results if x.get("file_name") == file_name),
                results[0],
            )

            state = item.get("state")

            if state == "done":
                return item

            if state == "failed":
                raise RuntimeError(f"MinerU job failed: {item.get('err_msg') or item}")

            time.sleep(self.poll_interval)

    def _extract_core_artifacts(
        self,
        full_zip_url: str,
        source_path: Path,
    ) -> dict[str, Any]:
        resp = requests.get(full_zip_url, timeout=300)
        resp.raise_for_status()

        doc_id = self._build_doc_id(source_path)
        output_dir = self.artifact_dir / doc_id
        output_dir.mkdir(parents=True, exist_ok=True)

        raw_markdown = ""
        layout_json: dict[str, Any] = {}

        raw_markdown_path = output_dir / "full.md"
        layout_path = output_dir / "layout.json"

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            for name in zf.namelist():
                base = Path(name).name

                if base == "full.md":
                    raw_markdown = zf.read(name).decode("utf-8", errors="replace")
                    raw_markdown_path.write_text(raw_markdown, encoding="utf-8")

                elif base == "layout.json":
                    layout_json = json.loads(
                        zf.read(name).decode("utf-8", errors="replace")
                    )
                    layout_path.write_text(
                        json.dumps(layout_json, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )

        if not raw_markdown:
            raise RuntimeError("MinerU result zip does not contain full.md")

        if not layout_json:
            raise RuntimeError("MinerU result zip does not contain layout.json")

        return {
            "raw_markdown": raw_markdown.strip(),
            "raw_markdown_path": str(raw_markdown_path),
            "layout_json": layout_json,
            "layout_path": str(layout_path),
            "artifact_dir": str(output_dir),
        }

    def _build_pages_from_layout(self, layout_json: dict[str, Any]) -> list[str]:
        pdf_info = layout_json.get("pdf_info", [])
        pages: list[str] = []

        for page in pdf_info:
            blocks = page.get("para_blocks") or page.get("preproc_blocks") or []

            texts: list[str] = []
            for block in blocks:
                text = self._extract_text_from_layout_block(block)
                if text:
                    texts.append(text)

            pages.append("\n\n".join(texts).strip())

        return pages

    def _extract_text_from_layout_block(self, block: dict[str, Any]) -> str:
        parts: list[str] = []

        for line in block.get("lines", []) or []:
            for span in line.get("spans", []) or []:
                content = span.get("content")
                if isinstance(content, str) and content.strip():
                    parts.append(content.strip())

        for child in block.get("blocks", []) or []:
            child_text = self._extract_text_from_layout_block(child)
            if child_text:
                parts.append(child_text)

        return "\n".join(parts).strip()

    def _check_mineru_response(
        self,
        resp: requests.Response,
        message: str,
    ) -> dict[str, Any]:
        if resp.status_code != 200:
            raise RuntimeError(f"{message}: {resp.status_code} {resp.text}")

        body = resp.json()
        if body.get("code") != 0:
            raise RuntimeError(f"{message}: {body.get('msg')} | raw={body}")

        return body

    def _build_doc_id(self, path: Path) -> str:
        return path.stem.lower().replace(" ", "_")
