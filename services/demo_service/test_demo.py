"""Focused contract check for the standalone local demo API.

Run from repository root: .venv-demo/Scripts/python.exe -m unittest services.demo_service.test_demo
"""

from __future__ import annotations

import base64
import io
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


_temporary_data = tempfile.TemporaryDirectory(prefix="rag-demo-test-")
os.environ["DEMO_DATA_DIR"] = _temporary_data.name

from services.demo_service.app import app  # noqa: E402


class DemoContractTest(unittest.TestCase):
    def setUp(self) -> None:
        target = Path(_temporary_data.name).resolve()
        temp_root = Path(tempfile.gettempdir()).resolve()
        if target.parent != temp_root or not target.name.startswith("rag-demo-test-"):
            raise RuntimeError("Refusing to reset data outside this test's temporary directory.")
        shutil.rmtree(target, ignore_errors=True)

    def test_frontend_flows(self) -> None:
        with TestClient(app) as client:
            health = client.get("/health")
            self.assertEqual(health.status_code, 200)
            self.assertTrue(health.json()["demo_mode"])

            status = client.get("/orchestration/status").json()
            self.assertTrue(status["demo_mode"])
            self.assertTrue(status["orchestration"]["reachable"])
            self.assertFalse(status["lightrag"]["reachable"])

            signup = client.post(
                "/auth/signup",
                json={"name": "Pilot Tester", "email": "pilot@example.com", "password": "pass12345"},
            )
            self.assertEqual(signup.status_code, 201, signup.text)
            token = signup.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            self.assertEqual(client.get("/auth/me", headers=headers).json()["name"], "Pilot Tester")
            self.assertEqual(
                client.post("/auth/login", json={"email": "pilot@example.com", "password": "pass12345"}).status_code,
                200,
            )
            self.assertEqual(client.get("/chat/sessions").status_code, 401)

            sample = (
                b"The pilot team is based in Casablanca, Morocco. "
                b"The assistant supports documents in English, French, and Arabic."
            )
            upload = client.post(
                "/orchestration/upload?provider=nextcloud",
                files={"file": ("project-brief.txt", sample, "text/plain")},
                data={"metadata_json": '{"Department":"Pilot","Year":"2026"}'},
            )
            self.assertEqual(upload.status_code, 200, upload.text)
            document = upload.json()
            document_id = document["document_id"]
            file_path = document["file_path"]
            self.assertEqual(document["storage_backend"], "local-demo:nextcloud")
            self.assertEqual(
                client.post("/orchestration/upload", files={"file": ("copy.txt", sample, "text/plain")}).status_code,
                409,
            )
            self.assertEqual(client.get("/orchestration/documents").json()[0]["document_id"], document_id)
            self.assertEqual(
                client.get("/orchestration/document-metadata/options").json()["items"]["Department"],
                ["Pilot"],
            )
            self.assertEqual(
                client.get("/orchestration/document-state/by-document-id", params={"document_id": document_id})
                .json()["uploaded_document"]["status"],
                "uploaded",
            )

            processed = client.post("/orchestration/process", json={"file_path": file_path, "language_hint": "auto"})
            self.assertEqual(processed.status_code, 200, processed.text)
            self.assertEqual(processed.json()["latest_processing"]["processing_status"], "parsed")
            indexed = client.post("/orchestration/lightrag/index-by-path", json={"file_path": file_path})
            self.assertEqual(indexed.status_code, 200, indexed.text)
            self.assertEqual(indexed.json()["indexing_result"]["status"], "indexed")
            self.assertEqual(
                client.get("/orchestration/document-state", params={"file_path": file_path})
                .json()["uploaded_document"]["status"],
                "indexed",
            )

            response = client.post(
                "/chat/message",
                headers=headers,
                json={"session_id": None, "message": "Where is the pilot team based?"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn("Casablanca", response.json()["answer"])
            session_id = response.json()["session_id"]
            self.assertEqual(len(client.get("/chat/sessions", headers=headers).json()), 1)
            self.assertEqual(len(client.get(f"/chat/sessions/{session_id}/messages", headers=headers).json()), 2)

            filtered = client.post(
                "/chat/message", headers=headers,
                json={"session_id": session_id, "message": "Which languages are supported?", "filters": {"Department": ["Pilot"]}},
            )
            self.assertEqual(filtered.status_code, 200, filtered.text)
            self.assertIn("English", filtered.json()["answer"])
            self.assertIn("Arabic", filtered.json()["answer"])

            # Video reruns can leave several near-identical indexed documents.
            # Repeated location sentences must not crowd the language sentence out.
            repeated_document_ids = []
            for copy_number in range(3):
                repeated = client.post(
                    "/orchestration/upload",
                    files={
                        "file": (
                            f"project-brief-copy-{copy_number}.txt",
                            sample + f"\nRun marker {copy_number}.".encode(),
                            "text/plain",
                        )
                    },
                )
                self.assertEqual(repeated.status_code, 200, repeated.text)
                repeated_document_ids.append(repeated.json()["document_id"])
                repeated_path = repeated.json()["file_path"]
                self.assertEqual(
                    client.post("/orchestration/process", json={"file_path": repeated_path}).status_code,
                    200,
                )
                self.assertEqual(
                    client.post("/orchestration/lightrag/index-by-path", json={"file_path": repeated_path}).status_code,
                    200,
                )

            combined = client.post(
                "/chat/message", headers=headers,
                json={
                    "session_id": session_id,
                    "message": "According to the project brief, where is the pilot team based, and which three languages are supported?",
                },
            )
            self.assertEqual(combined.status_code, 200, combined.text)
            for fact in ("Casablanca", "English", "French", "Arabic"):
                self.assertIn(fact, combined.json()["answer"])
            self.assertEqual(combined.json()["answer"].count("Casablanca"), 1)

            generated = client.post(
                "/chat/message", headers=headers,
                json={"session_id": session_id, "message": "Generate a TXT summary of the indexed project brief"},
            )
            self.assertEqual(generated.status_code, 200, generated.text)
            match = re.search(r"\[Download TXT\]\((/api/chatbot/generate/download/[0-9a-f]{32}\.txt)\)", generated.json()["answer"])
            self.assertIsNotNone(match)
            download_path = match.group(1).replace("/api/chatbot", "", 1)
            self.assertIn(b"Casablanca", client.get(download_path).content)
            preview = client.get(download_path.replace("/download/", "/preview/"))
            self.assertEqual(preview.status_code, 200)
            self.assertIn("Casablanca", preview.json()["text"])
            self.assertIn("project-brief.txt", preview.json()["text"])

            for file_format, signature in (("CSV", b"Source"), ("PDF", b"%PDF"), ("DOCX", b"PK")):
                generated = client.post(
                    "/chat/message", headers=headers,
                    json={"session_id": session_id, "message": f"Generate a {file_format} summary of the indexed project brief"},
                )
                self.assertEqual(generated.status_code, 200, generated.text)
                match = re.search(
                    rf"\[Download {file_format}\]\((/api/chatbot/generate/download/[0-9a-f]{{32}}\.{file_format.lower()})\)",
                    generated.json()["answer"],
                )
                self.assertIsNotNone(match)
                content = client.get(match.group(1).replace("/api/chatbot", "", 1)).content
                self.assertTrue(content.startswith(signature) or signature in content[:100])
                preview_path = match.group(1).replace("/api/chatbot", "", 1).replace("/download/", "/preview/")
                preview = client.get(preview_path)
                self.assertEqual(preview.status_code, 200)
                self.assertIn("Casablanca", preview.json()["text"])
                self.assertIn("project-brief.txt", preview.json()["text"])

            unsupported = client.post(
                "/chat/message", headers=headers,
                json={"session_id": session_id, "message": "Generate a PDF about lunar geology"},
            )
            self.assertEqual(unsupported.status_code, 200)
            self.assertIn("did not generate", unsupported.json()["answer"])
            self.assertNotIn("/generate/download/", unsupported.json()["answer"])

            deletion = client.post(
                "/orchestration/document/delete", json={"document_id": document_id}
            )
            self.assertEqual(deletion.status_code, 200, deletion.text)
            for repeated_id in repeated_document_ids:
                self.assertEqual(
                    client.post("/orchestration/document/delete", json={"document_id": repeated_id}).status_code,
                    200,
                )
            self.assertEqual(client.get("/orchestration/documents").json(), [])
            self.assertEqual(client.delete(f"/chat/sessions/{session_id}", headers=headers).status_code, 200)

    def test_base64_docx(self) -> None:
        from docx import Document

        with TestClient(app) as client:
            doc = Document()
            doc.add_paragraph("The demo document says the project is based in Casablanca.")
            handle = io.BytesIO()
            doc.save(handle)
            data = handle.getvalue()
            upload = client.post(
                "/documents/upload?provider=sharepoint",
                json={
                    "filename": "brief.docx",
                    "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "size_bytes": len(data),
                    "base64_data": base64.b64encode(data).decode("ascii"),
                    "metadata_json": {"Team": "Pilot"},
                },
            )
            self.assertEqual(upload.status_code, 200, upload.text)
            processed = client.post("/orchestration/process", json={"file_path": upload.json()["file_path"]})
            self.assertEqual(processed.status_code, 200, processed.text)
            self.assertIn("Casablanca", processed.json()["final_markdown"])

    def test_four_exports_use_four_uploaded_file_types(self) -> None:
        from scripts.build_demo_samples import build_samples
        from services.demo_service.files import extract_text

        with TestClient(app) as client:
            token = client.post(
                "/auth/signup",
                json={"name": "Source Tester", "email": "sources@example.com", "password": "pass12345"},
            ).json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            samples = build_samples(Path(_temporary_data.name) / "samples", "contract")
            sources = {sample.name: extract_text(sample.name, sample.read_bytes()) for sample in samples}
            for sample in samples:
                upload = client.post(
                    "/orchestration/upload",
                    files={"file": (sample.name, sample.read_bytes(), "application/octet-stream")},
                )
                self.assertEqual(upload.status_code, 200)
                path = upload.json()["file_path"]
                self.assertEqual(client.post("/orchestration/process", json={"file_path": path}).status_code, 200)
                self.assertEqual(client.post("/orchestration/lightrag/index-by-path", json={"file_path": path}).status_code, 200)

            ml_answer = client.post(
                "/chat/message", headers=headers,
                json={"message": "Generate a PDF summary on ML using only indexed documents"},
            ).json()["answer"]
            ml_match = re.search(r"/api/chatbot/generate/download/([0-9a-f]{32}\.pdf)", ml_answer)
            self.assertIsNotNone(ml_match, ml_answer)
            ml_preview = client.get(f"/generate/preview/{ml_match.group(1)}").json()["text"]
            self.assertIn("quality_criteria.pdf", ml_preview)
            self.assertIn("Machine learning (ML)", ml_preview)
            self.assertNotIn("pilot_metrics.csv", ml_preview)

            missing_answer = client.post(
                "/chat/message", headers=headers,
                json={"message": "Generate a PDF summary about lunar geology"},
            ).json()["answer"]
            self.assertIn("no data in the indexed files", missing_answer)
            self.assertNotIn("/generate/download/", missing_answer)

            for file_format in ("PDF", "DOCX", "TXT", "CSV"):
                answer = client.post(
                    "/chat/message", headers=headers,
                    json={"message": f"Generate a {file_format} using only uploaded files"},
                ).json()["answer"]
                match = re.search(r"/api/chatbot/generate/download/([0-9a-f]{32}\.[a-z]+)", answer)
                self.assertIsNotNone(match, answer)
                preview = client.get(f"/generate/preview/{match.group(1)}").json()
                opened = client.get(f"/generate/open/{match.group(1)}")
                self.assertEqual(opened.status_code, 200)
                if file_format == "PDF":
                    self.assertEqual(opened.headers["content-type"], "application/pdf")
                    self.assertIn("inline", opened.headers["content-disposition"])
                    self.assertTrue(opened.content.startswith(b"%PDF"))
                else:
                    self.assertIn("text/html", opened.headers["content-type"])
                    self.assertIn("project_brief.txt", opened.text)
                for source_name in sources:
                    self.assertIn(source_name, preview["text"])
                self.assertIn("Casablanca", preview["text"])
                self.assertIn("Amal Benali", preview["text"])
                self.assertIn("Salma Idrissi", preview["text"])
                self.assertIn("zero unsupported claims", preview["text"])
                if file_format == "CSV":
                    self.assertEqual(preview["rows"][0], ["ID", "Section", "Source file", "File type", "Evidence excerpt"])
                    for _item_id, _section, source, _file_type, excerpt in preview["rows"][1:]:
                        self.assertIn(excerpt, sources[source])

    def test_subject_requires_document_content(self) -> None:
        with TestClient(app) as client:
            token = client.post(
                "/auth/signup",
                json={"name": "Subject Tester", "email": "subject@example.com", "password": "pass12345"},
            ).json()["access_token"]
            upload = client.post(
                "/orchestration/upload",
                files={"file": ("ML-notes.txt", b"The pilot office is in Casablanca.", "text/plain")},
            )
            path = upload.json()["file_path"]
            client.post("/orchestration/process", json={"file_path": path})
            client.post("/orchestration/lightrag/index-by-path", json={"file_path": path})
            answer = client.post(
                "/chat/message", headers={"Authorization": f"Bearer {token}"},
                json={"message": "Generate a PDF summary on ML"},
            ).json()["answer"]
            self.assertIn("no data in the indexed files", answer)
            self.assertNotIn("/generate/download/", answer)


if __name__ == "__main__":
    unittest.main()
