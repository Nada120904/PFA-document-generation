# Upload Service

## Role

This service handles file intake.

It is responsible for:

- receiving a file from the frontend or an HTTP client
- computing its hash
- detecting duplicates
- sending the file to `storage_service`
- registering document metadata through `postgres_service`

It does not write directly to SQL.

## Local port

```text
8011
```

## Dependencies

This service depends on:

- `storage_service`
- `postgres_service`

## Useful endpoints

- `GET /health`
- `GET /documents/ping`
- `POST /documents/upload`

## Important variables

Copy the template:

```bash
cp services/upload_service/.env.example services/upload_service/.env
```

Then verify local values:

```env
STORAGE_SERVICE_URL=http://127.0.0.1:8012
STORAGE_PROVIDER=nextcloud
POSTGRES_SERVICE_URL=http://127.0.0.1:8008
```

Note:

- an older example may contain an obsolete postgres port
- in local mode, `postgres_service` typically runs on `8008`

## Local startup

```bash
cd /mnt/c/Users/sfirdaou/Downloads/system_rag1/rag_system
source .venv/bin/activate
uvicorn services.upload_service.app:app --host 127.0.0.1 --port 8011 --reload
```

## Simple test

```bash
curl -X POST "http://127.0.0.1:8011/documents/upload?provider=nextcloud" \
  -F "file=@/mnt/c/Users/sfirdaou/Downloads/Reading.txt"
```

## Actual flow

1. receive the file
2. compute `file_hash`
3. ask `postgres_service` whether a document with this hash already exists
4. if not:
   - call `storage_service`
   - store the document in the selected provider
   - receive `document_id`, `file_path`, and metadata back
5. return the document to the client

## Supported providers

The provider is passed as a query parameter:

- `nextcloud`
- `onedrive`
- `sharepoint`

Example:

```text
POST /documents/upload?provider=sharepoint
```

## Retry behavior

This service applies short retry logic on outgoing HTTP calls:

- duplicate lookup by hash
- lookup by path
- upload to `storage_service`
- download from `storage_service`

Current policy:

- `3` attempts
- `1` second sleep
- only for timeout, connect error, read error, protocol error, and HTTP 5xx

No retry for:

- `400`
- document already exists
- validation errors

## Important business cases

### First successful upload

Expected message:

- `Document uploaded, processed, and indexed successfully.`

or

- `Document uploaded successfully.` depending on the stage reached

### Second upload of the same file

The service detects the duplicate using `file_hash`.

Expected message:

- `This document already exists ...`

## Troubleshooting

### `502 Bad Gateway`

Verify:

- `storage_service` is running
- `postgres_service` is running
- URLs in `.env` are correct

### PDF / DOCX blocked by Zscaler

In some cases:

- upload may succeed
- but the remote file may be blocked later during download

So the real problem is not always in `upload_service`.
