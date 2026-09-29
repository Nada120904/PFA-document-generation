# RAG document assistant

This repository contains a React chatbot, a Python document pipeline, and supporting services for storage, parsing, indexing, and retrieval.

## Run the local demo

The local demo exercises the existing frontend with a small API that stores users, documents, and conversations in SQLite. It needs Python 3.11+, Node.js, and npm. It does not need Docker, a cloud account, or an API key.

```powershell
python scripts/start_demo.py
```

The first run creates `.venv-demo`, installs the demo API requirements, and installs frontend packages. Open <http://127.0.0.1:5173>, select **Continue to local demo**, and create an account on the sign-in screen. Data stays in `data/demo/`. Stop the processes with Ctrl+C.

The demo supports document upload, text extraction, indexing, metadata filters, document-grounded chat, saved conversations, and the document library. Sample uploads for PDF, Word (.docx), CSV, and TXT are in `demo_assets/sample_uploads/`. It generates the same four formats from source-attributed passages. PDF and Word exports include highlights, a source index, and evidence grouped by document; TXT keeps numbered sections; CSV includes an evidence ID, section, source, file type, and excerpt. Each export has an inline preview and an **Open file** viewer. For example, `Generate a PDF summary on ML` uses the ML passages in the indexed sample PDF. A request about a subject absent from the indexed files creates no file and says there is no data on that subject. The local service uses lexical matching, so these are structured extractive reports rather than synthesized reports. The separate production services, external storage providers, Qdrant, Neo4j, OCR/VLM models, and OpenAI are not started by this command.

## Record the walkthrough

Install Playwright and have Chrome or Edge plus ffmpeg available, then keep the local demo running in one terminal:

```powershell
python -m pip install playwright
python scripts/record_demo.py
```

The script records the real browser interface and writes an MP4 under `demo_assets/`. To add the narrated, captioned edit, install Edge TTS and run:

```powershell
python -m pip install edge-tts
python scripts/enhance_demo_video.py
```

The finished video is `demo_assets/pfa2026_grounded_demo_narrated.mp4`. It focuses on uploading PDF, Word, CSV, and TXT samples, generating an ML PDF, refusing an unsupported subject, and opening, scrolling through, and downloading each of the four structured exports. It includes an English voiceover, a readable chapter band, and an optional full narration subtitle track; the matching `.srt` is beside it. No API keys are needed or recorded.

Representative exports can be recreated with `.venv-demo\Scripts\python.exe -m scripts.build_demo_exports`. They are saved under `demo_assets/example_exports/`.

## Production architecture

The production path is the React frontend → chatbot and orchestration APIs → upload, storage, Docling, VLM, LightRAG, and Postgres services. It also expects configured storage, Postgres, Qdrant, Neo4j, and model endpoints. The root `docker-compose.yml` currently defines only Postgres, upload, and Docling; use the service READMEs and `.env.example` files for the remaining processes and credentials. `chatbot/README.md` describes the API flow and local ports.

Keep service API keys in server-side environment variables. The local demo does not use the key shared in chat.
