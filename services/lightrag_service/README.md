# LightRAG Service

## Role

This service is responsible for:

- full-text indexing from already parsed documents
- deleting a document from LightRAG
- retrieval
- reranking
- answer generation on the retrieval API side

It reads and writes metadata through `postgres_service` over HTTP.

## Local port

```text
8000
```

## Main endpoints

- `GET /health`
- `POST /indexing/text/full/by-document`
- `POST /indexing/text/full/batch-from-db`
- `POST /indexing/text/full/delete/by-document`
- `POST /retrieval/text`

## Dependencies

- `postgres_service`
- OpenAI-compatible LLM / embedding gateway
- Qdrant
- Neo4j depending on configuration

## Important variables

Copy the template:

```bash
cp services/lightrag_service/.env.example services/lightrag_service/.env
```

Verify at least:

```env
DB_SERVICE_BASE_URL=http://127.0.0.1:8008
OPENAI_BASE_URL=http://102.54.244.89:8088/ollama-v2/api/v1
OPENAI_API_KEY=
LLM_MODEL_NAME=ministral-3:8b
EMBEDDING_MODEL_NAME=qwen3-embedding:latest
EMBEDDING_DIM=4096
LLM_MODEL_MAX_ASYNC=1
EMBEDDING_FUNC_MAX_ASYNC=1
LLM_TIMEOUT=1200
EMBEDDING_TIMEOUT=300
RERANK_BINDING=huggingface
RERANK_MODEL_NAME=cross-encoder/ms-marco-MiniLM-L-6-v2
RERANK_BATCH_SIZE=8
MIN_RERANK_SCORE=0.0
```

## Local startup

```bash
cd /mnt/c/Users/sfirdaou/Downloads/system_rag1/rag_system
source .venv/bin/activate
set -a
source services/lightrag_service/.env
set +a
uvicorn services.lightrag_service.app:app --host 127.0.0.1 --port 8000 --reload
```

## Health check

```bash
curl http://127.0.0.1:8000/health
```

## Retrieval tests

Without answer generation:

```bash
curl -X POST http://127.0.0.1:8000/retrieval/text \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is writing?",
    "search_type": "hybrid",
    "top_k": 5,
    "enable_reranker": true,
    "rerank_top_n": 10,
    "generate_answer": false,
    "evaluate_ragas": false
  }'
```

With answer generation:

```bash
curl -X POST http://127.0.0.1:8000/retrieval/text \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the three qualities mentioned as necessary for good writing?",
    "search_type": "hybrid",
    "top_k": 5,
    "enable_reranker": true,
    "rerank_top_n": 10,
    "generate_answer": true,
    "evaluate_ragas": false
  }'
```

## Indexing prerequisites

This service indexes a document only after parsing is complete.

Before calling `/indexing/text/full/by-document`, make sure:

- `uploaded_documents.status` is consistent
- `document_processing.markdown_text` exists
- parsing has completed successfully

## Retry behavior

The service already has short retry logic for DB-facing client calls.

For model or infrastructure failures:

- do not hide them with aggressive retry loops
- first verify the upstream model gateway

## Hugging Face certificate setup in WSL

If Hugging Face downloads fail with `CERTIFICATE_VERIFY_FAILED`, install the corporate root certificate inside WSL.

### 1. Export the corporate certificate from Windows

In Windows:

1. Press `Win + R`
2. Run `certmgr.msc`
3. Open `Trusted Root Certification Authorities`
4. Open `Certificates`
5. Find the company certificate, for example a `Zscaler` root certificate
6. Right-click it
7. Select `All Tasks` -> `Export`
8. Click `Next`
9. Choose `No, do not export the private key`
10. Select `Base-64 encoded X.509 (.CER)`
11. Save it somewhere accessible, for example:

```text
C:\Users\sfirdaou\Downloads\company-ca.cer
```

### 2. Add the certificate to WSL

```bash
sudo cp /mnt/c/Users/sfirdaou/Downloads/company-ca.cer /usr/local/share/ca-certificates/company-ca.crt
sudo update-ca-certificates
```

For the actual local case that was used:

```bash
sudo cp /mnt/c/Users/sfirdaou/Downloads/zscaler-root-ca.cer /usr/local/share/ca-certificates/zscaler-root-ca.crt
sudo update-ca-certificates
```

### 3. Test HTTPS access

```bash
curl -I https://huggingface.co
```

Expected result:

- `HTTP/2 200`
- or `HTTP/2 302`

You should no longer get `CERTIFICATE_VERIFY_FAILED`.

### 4. Pre-download the reranker model

```bash
cd /mnt/c/Users/sfirdaou/Downloads/system_rag1/rag_system
source .venv/bin/activate
python - <<'PY'
from transformers import AutoTokenizer, AutoModelForSequenceClassification

model = "cross-encoder/ms-marco-MiniLM-L-6-v2"

AutoTokenizer.from_pretrained(model)
AutoModelForSequenceClassification.from_pretrained(model)

print("OK model downloaded:", model)
PY
```

## Common cases

### `generated_answer = null` with retrieved chunks

This means:

- retrieval succeeded
- generation failed or was disabled

### Low rerank score

A chunk can still be top 1 with a low score if:

- it is still the best chunk among the retrieved candidates
- but a later business threshold may still filter it out

### `model failed to load`

This issue comes from the model backend / gateway, not from the LightRAG router itself.

### Long execution time

The total time may come from:

- chatbot-side query optimization
- embeddings
- LightRAG retrieval
- final answer generation

Use service logs to inspect the time spent in each step.
