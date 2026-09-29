"""Save representative, source-backed exports for visual QA and sharing."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from scripts.build_demo_samples import build_samples


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "demo_assets" / "example_exports"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="pfa-export-qa-") as temporary:
        os.environ["DEMO_DATA_DIR"] = temporary
        from services.demo_service.app import app

        samples = build_samples(Path(temporary) / "uploads", "export-example")
        with TestClient(app) as client:
            token = client.post("/auth/signup", json={
                "name": "Export Example", "email": "exports@example.test", "password": "LocalDemo2026!",
            }).json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            for path in samples:
                upload = client.post("/orchestration/upload", files={
                    "file": (path.name, path.read_bytes(), "application/octet-stream"),
                })
                upload.raise_for_status()
                file_path = upload.json()["file_path"]
                client.post("/orchestration/process", json={"file_path": file_path}).raise_for_status()
                client.post("/orchestration/lightrag/index-by-path", json={"file_path": file_path}).raise_for_status()

            requests = (
                ("pdf", "Generate a PDF summary on ML using only indexed documents", "machine_learning_evidence_brief.pdf"),
                ("docx", "Generate a DOCX using only the uploaded files", "document_intelligence_evidence_report.docx"),
                ("txt", "Generate a TXT using only the uploaded files", "document_intelligence_evidence_report.txt"),
                ("csv", "Generate a CSV using only the uploaded files", "document_intelligence_evidence_report.csv"),
            )
            OUTPUT.mkdir(parents=True, exist_ok=True)
            for extension, prompt, name in requests:
                response = client.post("/chat/message", headers=headers, json={"message": prompt})
                response.raise_for_status()
                match = re.search(rf"/api/chatbot/generate/download/([0-9a-f]{{32}}\.{extension})", response.json()["answer"])
                if not match:
                    raise RuntimeError(f"No {extension} download in response: {response.json()['answer']}")
                download = client.get(f"/generate/download/{match.group(1)}")
                download.raise_for_status()
                target = OUTPUT / name
                target.write_bytes(download.content)
                print(target)


if __name__ == "__main__":
    main()
