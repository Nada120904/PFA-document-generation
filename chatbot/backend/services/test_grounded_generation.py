"""Generation must use indexed content and refuse absent subjects."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from chatbot.backend.graph.workflow import handle_generation_request_node


class GroundedGenerationTest(unittest.TestCase):
    def test_ml_pdf_uses_retrieved_indexed_excerpt(self) -> None:
        chunk = {
            "file_path": "uploads/quality_criteria.pdf",
            "content": "Machine learning (ML) helps classify uploaded documents.",
        }
        state = {
            "requested_format": "pdf",
            "request_params": {"topic": "ML"},
            "user_message": "Generate a PDF summary on ML",
        }
        with patch("chatbot.backend.graph.workflow.retrieve_document_context", return_value=[chunk]), \
             patch("chatbot.backend.graph.workflow.generate_pdf", return_value="a" * 32 + ".pdf") as build:
            result = handle_generation_request_node(state)
        build.assert_called_once()
        self.assertIn("quality_criteria.pdf", build.call_args.args[1][0])
        self.assertIn("[Download PDF]", result["answer"])

    def test_absent_subject_creates_no_file(self) -> None:
        chunk = {
            "file_path": "uploads/quality_criteria.pdf",
            "content": "Machine learning (ML) helps classify uploaded documents.",
        }
        state = {
            "requested_format": "pdf",
            "request_params": {"topic": "lunar geology"},
            "user_message": "Generate a PDF summary about lunar geology",
        }
        with patch("chatbot.backend.graph.workflow.retrieve_document_context", return_value=[chunk]), \
             patch("chatbot.backend.graph.workflow.generate_pdf") as build:
            result = handle_generation_request_node(state)
        build.assert_not_called()
        self.assertIn("no data in the indexed files", result["answer"])
        self.assertNotIn("/generate/download/", result["answer"])


if __name__ == "__main__":
    unittest.main()
