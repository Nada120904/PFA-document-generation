# Chatbot

This folder contains the chatbot layer of the RAG project.

It is split into two parts:

- `backend/`: FastAPI chatbot API
- `frontend/`: React/Vite user interface

## Real architecture

There are two different flows in this project.

### 1. Document pipeline flow

- chatbot frontend
- orchestration service
- upload service
- storage service
- docling service
- vlm service
- lightrag service
- postgres service

### 2. Chat question/answer flow

- chatbot frontend
- chatbot backend
- lightrag service
- postgres service

Important:

- the chatbot backend does not use `orchestration_service` for `/chat/message`
- `orchestration_service` is mainly used for the document pipeline

## Local ports

- `frontend`: `5173`
- `chatbot backend`: `8015`
- `orchestration`: `8002`
- `lightrag`: `8000`
- `upload`: `8011`
- `storage`: `8012`
- `docling`: `8005`
- `vlm`: `8003`
- `postgres service`: `8008`

## Recommended startup order

From the project root:

```bash
cd <repository-root>
source .venv/bin/activate
```

For a self-contained local demo without the production infrastructure, run
`python scripts/start_demo.py` from the repository root.

Then start the services in separate terminals:

1. `postgres_service`
2. `storage_service`
3. `upload_service`
4. `docling_service`
5. `vlm-service`
6. `lightrag_service`
7. `orchestration_service`
8. `chatbot backend`
9. `chatbot frontend`

## Quick health check

```bash
curl http://127.0.0.1:8008/health
curl http://127.0.0.1:8012/health
curl http://127.0.0.1:8011/health
curl http://127.0.0.1:8005/health
curl http://127.0.0.1:8003/health
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8002/orchestration/status
curl http://127.0.0.1:8015/health
```

## Configuration

Read these files for concrete setup:

- `chatbot/backend/.env.example`
- `chatbot/frontend/.env.example`
- `chatbot/backend/README.md`
- `chatbot/frontend/README.md`

## First UI screen: workspace configuration

When the frontend opens for the first time, the user does not go directly to login.

The first screen is the workspace configuration page.

The user must fill the required runtime values there and click `Save and continue`.

After that, the UI can continue to:

- login
- sign up
- open the chatbot workspace

Important:

- this page stores values locally in the browser
- these values are sent as runtime headers with requests
- this is intended to progressively replace direct dependency on static local `.env` values for user-facing runtime configuration
- server-side secrets and infrastructure-only values still remain on backend/service configuration where required

## Common issues

### Certificate / Zscaler

If a PDF or DOCX is blocked by Zscaler:

- upload may succeed
- later download from `storage_service` or `docling_service` may fail
- the final document state depends on the exact stage where the failure happened

### Remote database unavailable

If you see errors such as:

- `No route to host`
- `server closed the connection unexpectedly`

then the issue is network, VPN, firewall, or remote server access, not the chatbot UI itself.

### UI document controls

In the current UI:

- the user selects a storage provider
- upload, processing, and indexing are shown as separate states
- play/retry controls are frontend actions that call the corresponding backend endpoints

## Goal of this layer

This folder provides a user-facing chatbot experience so that a user can:

- sign in
- upload a document
- process and index it if needed
- ask questions about indexed documents
