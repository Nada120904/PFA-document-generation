from __future__ import annotations

import json
import mimetypes
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import requests
from bs4 import BeautifulSoup, NavigableString
from markitdown import MarkItDown

from app.config import get_settings
from app.logging import get_logger
from app.ocr_schema import schema_input


logger = get_logger(__name__)


class VLMClientError(RuntimeError):
    pass


def fix_html_inputs(html_text: str) -> str:
    if not html_text:
        return ""

    soup = BeautifulSoup(html_text, "html.parser")

    for tag in soup.find_all("input"):
        input_type = (tag.get("type") or "").lower()
        checked = tag.has_attr("checked")

        if input_type == "checkbox":
            tag.replace_with(NavigableString("[x] " if checked else "[ ] "))
        elif input_type == "radio":
            tag.replace_with(NavigableString("(x) " if checked else "( ) "))

    return str(soup)


def looks_like_html(text: str) -> bool:
    if not text:
        return False

    stripped = text.strip()

    if re.search(r"<!doctype\s+html|<html[\s>]|<body[\s>]|<head[\s>]", stripped, re.I):
        return True

    html_tags = (
        "article", "section", "main", "div", "p", "br", "span",
        "table", "thead", "tbody", "tr", "td", "th",
        "ul", "ol", "li",
        "h1", "h2", "h3", "h4", "h5", "h6",
        "img", "figure", "figcaption",
        "input", "label", "strong", "em", "b", "i",
    )

    tag_pattern = r"</?(" + "|".join(html_tags) + r")(\s+[^>]*)?/?>"
    return bool(re.search(tag_pattern, stripped, re.I))


def html_to_markdown_text(text: str) -> str:
    if not text:
        return ""

    if not looks_like_html(text):
        return text.strip()

    fixed_html = fix_html_inputs(text)
    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".html",
            encoding="utf-8",
            delete=False,
        ) as temp_file:
            temp_file.write(fixed_html)
            temp_path = Path(temp_file.name)

        converter = MarkItDown()
        result = converter.convert(str(temp_path))

        return result.text_content.strip()

    except Exception as exc:
        logger.warning(
            "MarkItDown conversion failed. Returning fixed HTML fallback | error=%s",
            exc,
        )
        return fixed_html.strip()

    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)


def build_markdown_text_with_json(markdown_text: str, outlines_payload: dict[str, Any]) -> str:
    json_text = json.dumps(
        outlines_payload,
        indent=2,
        ensure_ascii=False,
    )

    return f"""
## 1. Markdown Extraction

{markdown_text}

## 2. Structured JSON Extraction

```json
{json_text}
```
"""


def parse_json_string_if_needed(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    stripped = value.strip()
    if not (stripped.startswith("{") or stripped.startswith("[")):
        return value

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def get_outlines_payload(payload: dict[str, Any]) -> dict[str, Any]:
    outlines_payload = payload.get("outlines_data") or {
        "valid": False,
        "data": {},
        "errors": ["No outlines_data returned by server."],
    }

    if isinstance(outlines_payload, str):
        parsed = parse_json_string_if_needed(outlines_payload)
        if isinstance(parsed, dict):
            outlines_payload = parsed

    if not isinstance(outlines_payload, dict):
        return {
            "valid": False,
            "data": {},
            "errors": ["Invalid outlines_data returned by server."],
        }

    data = outlines_payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("_raw"), str):
        parsed_raw = parse_json_string_if_needed(data["_raw"])
        if isinstance(parsed_raw, dict):
            outlines_payload["data"] = parsed_raw

    return outlines_payload


class VLMClient:
    def __init__(self) -> None:
        settings = get_settings()

        self.base_url = settings.base_url.rstrip("/")
        self.api_key = settings.ocr_api_key
        self.model_id = settings.model_id
        self.prompt = settings.prompt
        self.parse_prompt = settings.parse_prompt
        self.timeout = settings.request_timeout_seconds
        self.max_retries = settings.vlm_max_retries
        self.retry_sleep_seconds = settings.vlm_retry_sleep_seconds
        self.unload_models_on_cuda_error = settings.vlm_unload_models_on_cuda_error
        self.schema_input = schema_input

    def extract_markdown_text(
        self,
        file_path: str,
        prompt: str | None = None,
        model_id: str | None = None,
    ) -> dict[str, Any]:
        path = Path(file_path)

        if not path.exists():
            raise VLMClientError(f"File not found: {file_path}")

        if not path.is_file():
            raise VLMClientError(f"Path is not a file: {file_path}")

        selected_prompt = prompt or self.prompt
        selected_model_id = model_id or self.model_id

        if path.suffix.lower() == ".pdf":
            return self.extract_pdf_markdown(
                pdf_path=path,
                prompt=selected_prompt,
                model_id=selected_model_id,
            )

        return self.extract_image_markdown(
            image_path=path,
            prompt=selected_prompt,
            model_id=selected_model_id,
        )

    def extract_image_markdown(
        self,
        image_path: Path,
        prompt: str,
        model_id: str,
    ) -> dict[str, Any]:
        raw_output, payload = self.call_model(
            file_path=image_path,
            prompt=prompt,
            model_id=model_id,
        )

        markdown_text = html_to_markdown_text(raw_output)
        outlines_payload = get_outlines_payload(payload)
        final_markdown_text = build_markdown_text_with_json(
            markdown_text=markdown_text,
            outlines_payload=outlines_payload,
        )

        return {
            "model_id": model_id,
            "markdown_text": final_markdown_text,
            "characters": len(final_markdown_text),
            "raw_markdown_text": markdown_text,
            "outlines_data": outlines_payload,
            "raw_payload": payload,
        }

    def extract_pdf_markdown(
        self,
        pdf_path: Path,
        prompt: str,
        model_id: str,
    ) -> dict[str, Any]:
        logger.info("PDF detected. Converting pages to images | file=%s", pdf_path)

        temp_dir = Path(tempfile.mkdtemp(prefix="vlm_pdf_pages_"))
        all_markdown_pages: list[str] = []
        all_payloads: list[dict[str, Any]] = []
        all_outlines: list[dict[str, Any]] = []

        try:
            pdf_doc = fitz.open(pdf_path)
            total_pages = len(pdf_doc)

            if total_pages == 0:
                raise VLMClientError(f"PDF has no pages: {pdf_path}")

            for page_index in range(total_pages):
                page_number = page_index + 1
                page = pdf_doc.load_page(page_index)

                zoom = 2.0
                matrix = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=matrix, alpha=False)

                page_image_path = temp_dir / f"{pdf_path.stem}_page_{page_number}.png"
                pix.save(str(page_image_path))

                logger.info(
                    "Processing PDF page with VLM model | file=%s | page=%s/%s",
                    pdf_path.name,
                    page_number,
                    total_pages,
                )

                raw_output, payload = self.call_model(
                    file_path=page_image_path,
                    prompt=prompt,
                    model_id=model_id,
                )

                page_markdown = html_to_markdown_text(raw_output)
                page_outlines = get_outlines_payload(payload)

                all_markdown_pages.append(
                    f"<!-- Page {page_number} -->\n\n{page_markdown}"
                )
                all_payloads.append(
                    {
                        "page": page_number,
                        "payload": payload,
                    }
                )
                all_outlines.append(
                    {
                        "page": page_number,
                        "outlines_data": page_outlines,
                    }
                )

            pdf_doc.close()

        except Exception as exc:
            raise VLMClientError(f"PDF processing failed: {exc}") from exc

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        markdown_text = "\n\n---\n\n".join(all_markdown_pages).strip()
        outlines_payload = {
            "valid": True,
            "data": {
                "type": "pdf_pages",
                "pages": len(all_markdown_pages),
                "outlines": all_outlines,
            },
            "errors": [],
        }
        final_markdown_text = build_markdown_text_with_json(
            markdown_text=markdown_text,
            outlines_payload=outlines_payload,
        )

        return {
            "model_id": model_id,
            "markdown_text": final_markdown_text,
            "characters": len(final_markdown_text),
            "raw_markdown_text": markdown_text,
            "outlines_data": outlines_payload,
            "raw_payload": {
                "type": "pdf_pages",
                "pages": len(all_markdown_pages),
                "payloads": all_payloads,
            },
        }

    def _is_cuda_or_memory_error(self, message: str) -> bool:
        lower_message = message.lower()

        return any(
            pattern in lower_message
            for pattern in (
                "cuda out of memory",
                "outofmemoryerror",
                "out of memory",
                "torch.cuda",
                "cudnn",
                "gpu memory",
                "memory is insufficient",
            )
        )

    def unload_all_models(self) -> None:
        unload_url = f"{self.base_url}/models/unload_all"
        headers = {"X-API-Key": self.api_key}

        try:
            logger.warning("Calling OCR/VLM unload_all before retry | url=%s", unload_url)
            response = requests.post(
                unload_url,
                headers=headers,
                timeout=120,
            )

            if response.status_code >= 400:
                logger.warning(
                    "OCR/VLM unload_all returned error | status=%s | body=%s",
                    response.status_code,
                    response.text,
                )
            else:
                logger.info("OCR/VLM unload_all completed | status=%s", response.status_code)

        except requests.RequestException as exc:
            logger.warning("OCR/VLM unload_all request failed | error=%s", exc)

    def call_model(
        self,
        file_path: Path,
        prompt: str,
        model_id: str,
    ) -> tuple[str, dict[str, Any]]:
        extract_url = f"{self.base_url}/extract"
        headers = {"X-API-Key": self.api_key}
        mime_type = mimetypes.guess_type(file_path.name)[0] or "image/png"

        total_attempts = max(1, self.max_retries + 1)
        last_error: str | None = None

        for attempt in range(1, total_attempts + 1):
            logger.info(
                "Calling model OCR/VLM | attempt=%s/%s | url=%s | model=%s | file=%s | mime=%s | schema_input=true",
                attempt,
                total_attempts,
                extract_url,
                model_id,
                file_path.name,
                mime_type,
            )

            try:
                with file_path.open("rb") as f:
                    files = {
                        "file": (
                            file_path.name,
                            f,
                            mime_type,
                        )
                    }

                    data = {
                        "model_id": model_id,
                        "prompt": prompt,
                        "schema_input": self.schema_input,
                    }

                    if self.parse_prompt:
                        data["parse_prompt"] = self.parse_prompt

                    response = requests.post(
                        extract_url,
                        headers=headers,
                        files=files,
                        data=data,
                        timeout=self.timeout,
                    )

            except requests.RequestException as exc:
                last_error = f"request failed: {exc}"
            else:
                logger.info(
                    "response received | attempt=%s/%s | status=%s | file=%s",
                    attempt,
                    total_attempts,
                    response.status_code,
                    file_path.name,
                )

                if response.status_code < 400:
                    content_type = response.headers.get("content-type", "")

                    if content_type.startswith("application/json"):
                        payload = response.json()
                    else:
                        payload = {"raw_text": response.text}

                    raw_output = (
                        payload.get("generated_text")
                        or payload.get("markdown_text")
                        or payload.get("html_text")
                        or payload.get("text")
                        or payload.get("raw_text")
                        or ""
                    )

                    if not isinstance(raw_output, str):
                        raw_output = str(raw_output)

                    return raw_output, payload

                last_error = f"error {response.status_code}: {response.text}"

            is_cuda_error = self._is_cuda_or_memory_error(last_error or "")

            if attempt < total_attempts:
                if is_cuda_error and self.unload_models_on_cuda_error:
                    self.unload_all_models()

                logger.warning(
                    "OCR/VLM attempt failed. Retrying after sleep | attempt=%s/%s | sleep=%ss | cuda_error=%s | error=%s",
                    attempt,
                    total_attempts,
                    self.retry_sleep_seconds,
                    is_cuda_error,
                    last_error,
                )

                time.sleep(self.retry_sleep_seconds)

        raise VLMClientError(
            f"OCR/VLM failed after {total_attempts} attempts. Last error: {last_error}"
        )
