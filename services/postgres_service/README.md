# Postgres Service

## Role

This is the central HTTP database service for the whole project.

Other services do not write SQL directly. They call this service instead.

## Local port

```text
8008
```

## What this service manages

Main tables:

- `uploaded_documents`
- `document_processing`
- `indexing_runs`
- `retrieval_runs`
- `chat_sessions`
- `chat_messages`
- `users`
- `service_errors`

## Service error tracking

The project now uses a `service_errors` table.

Purpose:

- record errors reported by services
- track their status
- automatically mark some errors as `resolved`

Useful business fields:

- `service_name`
- `operation_name`
- `status`
- `error_message`
- `error_context`
- `retry_count`
- `duration_ms`
- `created_at`
- `resolved_at`
- `updated_at`

## Main endpoints

- `GET /health`
- `POST /db/init`
- `GET /db/schema`
- `POST /db/uploaded-documents`
- `GET /db/uploaded-documents/by-hash/{file_hash}`
- `GET /db/uploaded-documents/by-path`
- `GET /db/uploaded-documents/{document_id}`
- `PATCH /db/uploaded-documents/{document_id}`
- `DELETE /db/uploaded-documents/{document_id}/purge`
- `POST /db/document-processing`
- `GET /db/document-processing/latest/{document_id}`
- `PATCH /db/document-processing/{processing_id}`
- `POST /db/indexing-runs`
- `GET /db/indexing-runs/latest/by-document/{document_id}`
- `PATCH /db/indexing-runs/{run_id}`
- `POST /db/retrieval-runs`
- `PATCH /db/retrieval-runs/{run_id}`
- `POST /db/service-errors`
- `GET /db/service-errors`
- `PATCH /db/service-errors/{error_id}`

## Configuration

Copy the template:

```bash
cp services/postgres_service/.env.example services/postgres_service/.env
```

Verify:

```env
POSTGRES_URL=postgresql+psycopg://username:password@host:5432/database_name
```

## Local startup

```bash
cd /mnt/c/Users/sfirdaou/Downloads/system_rag1/rag_system
source .venv/bin/activate
uvicorn services.postgres_service.app:app --host 127.0.0.1 --port 8008 --reload
```

## Verification

```bash
curl http://127.0.0.1:8008/health
curl -X POST http://127.0.0.1:8008/db/init
```

## Connection pool

The service uses a SQLAlchemy connection pool.

The pool is used to:

- reuse connections
- avoid opening a new connection for every request
- behave more reliably under load

Important stability options that were added:

- `pool_pre_ping`
- `pool_recycle`
- `pool_timeout`

Purpose:

- detect dead connections before use
- recycle old connections
- fail more clearly when the pool is saturated

## Diagnosing a server-side outage

If you see errors such as:

- `No route to host`
- `server closed the connection unexpectedly`
- `QueuePool limit ... reached`

first verify connectivity directly:

```bash
nc -vz 102.54.244.89 15432
psql "postgresql://..."
```

If even `nc` or `psql` fails, the issue is network/server access, not FastAPI logic.

## Useful SQL examples

Check documents:

```sql
select document_id, file_name, file_path, status, created_at, updated_at
from uploaded_documents
order by created_at desc
limit 20;
```

Check service errors:

```sql
select error_id, service_name, operation_name, status, duration_ms, created_at, resolved_at
from service_errors
order by created_at desc
limit 20;
```

Check Postgres activity:

```sql
select state, count(*)
from pg_stat_activity
group by state
order by count(*) desc;
```
