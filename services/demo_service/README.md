# Local demo service

This is a **local demo mode** for the RAG workspace. It replaces the network of
production microservices with one FastAPI process, SQLite, and local file storage.
The frontend uses the same API paths. No external service or API key is needed.

Install the small demo dependency set and start the API from the repository root:

```powershell
python -m pip install -r services/demo_service/requirements.txt
python -m uvicorn services.demo_service.app:app --host 127.0.0.1 --port 8015
```

The frontend development proxy must send `/api/chatbot`, `/api/orchestration`, and
`/api/upload-service` to `http://127.0.0.1:8015`, stripping each prefix as its
current Vite configuration does. Then start the frontend at port 5173.

The local starter login is `demo@example.com` / `demo12345`. It is created only
when the database has no users. `POST /auth/signup` can create more local users.
This fixed login is strictly for a loopback demo, not deployment.

Data is stored under `services/demo_service/.local` by default. Set
`DEMO_DATA_DIR` to another directory before launch to isolate a recording or
reset its data. Uploaded files and generated downloads live alongside the SQLite
database. Deleting this data directory resets the demo.

Document processing extracts text from TXT, Markdown, CSV, JSON, HTML, PDF and
DOCX. Image-only PDFs have no OCR in this mode. Indexing marks parsed text as
searchable; chat selects relevant text locally by lexical overlap and cites the
source document. Generated TXT, CSV, PDF and DOCX downloads are simple local
demonstrations using the indexed document text.

`/orchestration/status` identifies demo mode and reports the production
microservices as offline. Its single reachable card represents this local API.
