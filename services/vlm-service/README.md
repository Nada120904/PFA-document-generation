# VLM Service

## Role

`vlm-service` handles OCR/VLM fallback for documents that Docling alone cannot process sufficiently.

It is responsible for:

- reading a `processing_id`
- retrieving the document through `postgres_service`
- retrieving the file through `storage_service`
- calling the remote OCR/VLM API
- updating `document_processing`

## Local port

```text
8003
```

## Useful endpoints

- `GET /health`
- `POST /vlm/process-document/{processing_id}`
- `GET /vlm/process-check/{processing_id}`

## Dependencies

- `postgres_service`
- `storage_service`
- remote OCR/VLM API

## Important variables

Copy the template:

```bash
cp services/vlm-service/.env.example services/vlm-service/.env
```

Verify local values:

```env
POSTGRES_SERVICE_URL=http://127.0.0.1:8008
STORAGE_SERVICE_URL=http://127.0.0.1:8012
VLM_BASE_URL=<BASE_URL>
VLM_OCR_API_KEY=<OCR_API_KEY>
VLM_MODEL_ID=Qwen/Qwen3-VL-2B-Instruct
VLM_REQUEST_TIMEOUT_SECONDS=300
VLM_MAX_RETRIES=3
VLM_RETRY_SLEEP_SECONDS=120
```

## Local startup

Important: this service must be started from its own folder or with the correct import path.

Recommended command:

```bash
cd /mnt/c/Users/sfirdaou/Downloads/system_rag1/rag_system/services/vlm-service
source ../../.venv/bin/activate
uvicorn app.api:app --host 127.0.0.1 --port 8003 --reload
```

## Verification

```bash
curl http://127.0.0.1:8003/health
```

## Actual flow

1. orchestration or another service sends a `processing_id`
2. `vlm-service` reads the processing row
3. it finds the related document
4. it downloads the file
5. it calls the OCR/VLM API
6. it stores the final markdown/text in `document_processing`

## Retry behavior

VLM retry is mainly controlled by:

- `VLM_MAX_RETRIES`
- `VLM_RETRY_SLEEP_SECONDS`

This applies to calls toward the remote VLM backend, not to frontend behavior.

## Common problems

### Import error at startup

Do not start it with:

```bash
uvicorn services.vlm_service.app:app ...
```

because the real folder is:

```text
services/vlm-service
```

The correct command is based on:

```bash
uvicorn app.api:app ...
```

from inside `services/vlm-service`.

### GPU / model load failure

If the remote API returns errors such as:

- out of memory
- model failed to load

the issue is infrastructure/model-side, not in this service itself.

### Storage download error

If `storage_service` cannot return the file, VLM will not be able to process anything.
