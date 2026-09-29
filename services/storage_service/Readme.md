# Storage Service

## Role

This service abstracts storage providers.

It supports:

- Nextcloud
- OneDrive
- SharePoint

It handles:

- upload
- download
- delete
- move
- copy
- create-folder
- list
- info

It also registers document metadata through `postgres_service`.

## Local port

```text
8012
```

## Providers

The provider is selected with a query parameter:

- `provider=nextcloud`
- `provider=onedrive`
- `provider=sharepoint`

Example:

```text
POST /storage/upload?provider=sharepoint
```

## Useful endpoints

- `GET /health`
- `POST /storage/upload`
- `GET /storage/download`
- `DELETE /storage/delete`
- `POST /storage/move`
- `POST /storage/copy`
- `POST /storage/create-folder`
- `GET /storage/info`
- `GET /storage/list`

## Configuration

Copy the template:

```bash
cp services/storage_service/.env.example services/storage_service/.env
```

Verify at least:

```env
POSTGRES_SERVICE_URL=http://127.0.0.1:8008
REQUEST_TIMEOUT_SECONDS=60
```

### Nextcloud

```env
NEXTCLOUD_BASE_URL=http://102.54.244.89:8094
NEXTCLOUD_USERNAME=rag-test
NEXTCLOUD_PASSWORD=your-nextcloud-password
NEXTCLOUD_ROOT_PATH=HR-Documents
NEXTCLOUD_UPLOAD_FOLDER=raw-documents
NEXTCLOUD_PROCESSED_FOLDER=processed-documents
```

### OneDrive

```env
GRAPH_BASE_URL=https://graph.microsoft.com/v1.0
ONEDRIVE_CLIENT_ID=your-client-id
ONEDRIVE_CLIENT_SECRET=your-client-secret
ONEDRIVE_AUTHORITY=https://login.microsoftonline.com/common
ONEDRIVE_REFRESH_TOKEN_FILE=refresh_token.txt
ONEDRIVE_ROOT_FOLDER=HR-Documents
ONEDRIVE_UPLOAD_FOLDER=raw-documents
ONEDRIVE_PROCESSED_FOLDER=processed-documents
```

### SharePoint

```env
SHAREPOINT_POWER_AUTOMATE_URL=your-power-automate-url
SHAREPOINT_FOLDER=/sites/Document-AI-Project/Shared Documents/HR-Documents
SHAREPOINT_UPLOAD_FOLDER=raw-documents
SHAREPOINT_PROCESSED_FOLDER=processed-documents
```

## SharePoint certificate setup in WSL

For SharePoint, the Power Automate endpoint may be correct while Python HTTPS requests still fail because the corporate certificate chain is not trusted inside WSL.

### 1. Verify SharePoint / Power Automate configuration

Make sure these values are defined in `services/storage_service/.env`:

```env
SHAREPOINT_POWER_AUTOMATE_URL=...
SHAREPOINT_FOLDER=/sites/Document-AI-Project/Shared Documents/HR-Documents
SHAREPOINT_UPLOAD_FOLDER=raw-documents
SHAREPOINT_PROCESSED_FOLDER=processed-documents
```

### 2. Install the corporate certificate in WSL

Example with the local Zscaler certificate:

```bash
sudo cp /mnt/c/Users/sfirdaou/Downloads/zscaler-root-ca.cer /usr/local/share/ca-certificates/zscaler-root-ca.crt
sudo update-ca-certificates
```

### 3. Test the Power Automate endpoint with curl

```bash
curl -I "https://your-power-automate-endpoint"
```

Expected result:

- `HTTP/2 200`

If `curl` succeeds, the endpoint is reachable and the system certificate bundle is accepted.

### 4. Force Python `requests` to use the WSL CA bundle

In the same terminal used to start `storage_service`:

```bash
export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
```

This is important because `requests.post(...)` may still fail even when `curl` already works.

### 5. Start the service

```bash
cd /mnt/c/Users/sfirdaou/Downloads/system_rag1/rag_system
source .venv/bin/activate
uvicorn services.storage_service.app.main:app --host 127.0.0.1 --port 8012 --reload
```

### 6. Test SharePoint upload

```bash
curl -X POST "http://127.0.0.1:8012/storage/upload?provider=sharepoint" \
  -F "file=@/mnt/c/Users/sfirdaou/Downloads/Reading.txt"
```

If this works, the effective fix was:

- correct Power Automate configuration
- corporate certificate installed in WSL
- `REQUESTS_CA_BUNDLE` and `SSL_CERT_FILE` exported for Python

## Local startup

```bash
cd /mnt/c/Users/sfirdaou/Downloads/system_rag1/rag_system
source .venv/bin/activate
uvicorn services.storage_service.app.main:app --host 127.0.0.1 --port 8012 --reload
```

## Simple tests

### Nextcloud

```bash
curl -X POST "http://127.0.0.1:8012/storage/upload?provider=nextcloud" \
  -F "file=@/mnt/c/Users/sfirdaou/Downloads/Reading.txt"
```

### OneDrive

```bash
curl -X POST "http://127.0.0.1:8012/storage/upload?provider=onedrive" \
  -F "file=@/mnt/c/Users/sfirdaou/Downloads/Reading.txt"
```

### SharePoint

```bash
curl -X POST "http://127.0.0.1:8012/storage/upload?provider=sharepoint" \
  -F "file=@/mnt/c/Users/sfirdaou/Downloads/Reading.txt"
```

## Actual workflow

1. the client selects a provider
2. the service uploads the file to that provider
3. the service creates or updates the document row through `postgres_service`
4. the `storage_backend` value is stored with the document
5. other services reuse the same `document_id`

## Troubleshooting

### `Internal Server Error` during upload

Check:

- provider configuration
- credentials
- corporate certificate trust inside WSL
- access to the SharePoint / Power Automate / Nextcloud endpoint

### Zscaler / blocked file type

If you receive an HTML Zscaler page instead of the real file:

- the provider endpoint is reachable
- but access to that file type is blocked
- the issue is network policy, not Python business logic
