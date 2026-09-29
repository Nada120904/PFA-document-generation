# Docling Service

## Role

This service handles document parsing.

It is responsible for:

- finding the already registered document
- downloading the file through `storage_service`
- applying Docling
- producing parsed markdown / text
- saving the result through `postgres_service`

## Local port

```text
8005
```

## Dependencies

- `postgres_service`
- `storage_service`

## Useful endpoints

- `GET /health`
- `POST /indexing/docling-only`
- `POST /indexing/docling-only/upload`
- `POST /indexing/text`
- `POST /indexing/text/upload`

## Important variables

Copy the template:

```bash
cp services/docling_service/.env.example services/docling_service/.env
```

Verify at least:

```env
POSTGRES_SERVICE_URL=http://127.0.0.1:8008
STORAGE_SERVICE_URL=http://127.0.0.1:8012
PDF_OCR_ENGINE=easyocr
DOCLING_LAYOUT_MODEL=docling_layout_v2
```

## Local startup

```bash
cd /mnt/c/Users/sfirdaou/Downloads/system_rag1/rag_system
source .venv/bin/activate
uvicorn services.docling_service.app:app --host 127.0.0.1 --port 8005 --reload
```

## Actual flow

1. receive `file_path` or `document_id`
2. read `uploaded_documents`
3. move the document to `parsing`
4. create a `document_processing` row
5. download the file through `storage_service`
6. apply Docling
7. update:
   - `document_processing`
   - `uploaded_documents.status`

## Retry behavior

This service uses two main retry layers:

1. short HTTP retry
   - postgres calls
   - storage download
   - transport / timeout / 5xx

2. postgres update retry
   - to avoid leaving the document in an inconsistent state after a short network failure

## Important failure cases

### PDF blocked by Zscaler

Typical case:

- upload succeeds
- Docling tries to download the PDF
- instead of the PDF, it receives an HTML Zscaler page
- processing fails

In that case:

- the issue is not Docling itself
- the real issue is remote file access through the corporate network policy

### `500` returned by storage

If `storage/download` returns `500`, verify:

- certificate trust in WSL
- Zscaler policy
- provider access

## Simple test

```bash
curl -X POST "http://127.0.0.1:8005/indexing/docling-only?file_path=http://.../myfile.pdf&language_hint=auto"
```

## Tables updated by this service

Main tables:

- `uploaded_documents`
- `document_processing`

Typical statuses:

- `uploaded`
- `parsing`
- `parsed`
- `error`
