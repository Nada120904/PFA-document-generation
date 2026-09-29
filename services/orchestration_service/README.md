# Orchestration Service

## Role

This service centralizes the document pipeline for the user interface.

It orchestrates:

- upload
- Docling processing
- VLM fallback when needed
- LightRAG indexing
- document state lookup
- health/status checks for connected services

## What it does not do

It does not handle chat requests for `/chat/message`.

The conversation flow goes through `chatbot/backend`, not through orchestration.

## Local port

```text
8002
```

## Tracked services

Orchestration typically calls:

- `postgres_service`
- `upload_service`
- `docling_service`
- `vlm-service`
- `lightrag_service`

`storage_service` is used indirectly through `upload_service` and `docling_service`.

## Useful endpoints

- `GET /health`
- `GET /orchestration/status`
- `POST /orchestration/upload`
- `POST /orchestration/process`
- `POST /orchestration/lightrag/index-by-path`
- `GET /orchestration/document-state`
- `GET /orchestration/document-state/by-document-id`

## Important variables

Copy the template:

```bash
cp services/orchestration_service/.env.example services/orchestration_service/.env
```

Then replace Docker-style URLs with local URLs if you are working in WSL/local mode:

```env
POSTGRES_SERVICE_URL=http://127.0.0.1:8008
UPLOAD_SERVICE_URL=http://127.0.0.1:8011
DOCLING_SERVICE_URL=http://127.0.0.1:8005
VLM_SERVICE_URL=http://127.0.0.1:8003
LIGHTRAG_SERVICE_URL=http://127.0.0.1:8000
REQUEST_TIMEOUT_SECONDS=900
VLM_POLL_INTERVAL_SECONDS=2
VLM_POLL_TIMEOUT_SECONDS=90
```

## Local startup

```bash
cd /mnt/c/Users/sfirdaou/Downloads/system_rag1/rag_system
source .venv/bin/activate
uvicorn services.orchestration_service.app:app --host 127.0.0.1 --port 8002 --reload
```

## Verification

```bash
curl http://127.0.0.1:8002/orchestration/status
```

## Main flow

### Upload

1. receive the file from the frontend
2. call `upload_service`
3. return the document response

### Processing

1. receive `file_path`
2. call `docling_service`
3. monitor VLM fallback if needed
4. return the processing state

### Indexing

1. receive `file_path`
2. call `lightrag_service`
3. return the indexing result

### Document state

It rebuilds the real UI-visible state by reading:

- `uploaded_documents`
- `document_processing`
- `indexing_runs`

## Retry behavior

This service already uses an HTTP retry helper for outgoing calls.

General policy:

- `3` attempts
- sleep between attempts
- only for network errors, timeouts, and HTTP 5xx responses

No automatic retry for:

- `400`
- logical duplicates
- business/validation errors

## Troubleshooting

### Inconsistent status in the UI

Check the real source-of-truth tables through `postgres_service`:

- `uploaded_documents`
- `document_processing`
- `indexing_runs`

### LightRAG not triggered

If `docling_service` fails, orchestration should not report a real successful indexing run.

### UI refresh behavior

The frontend `Refresh` button reloads orchestration-driven state endpoints; it does not restart any backend service.
