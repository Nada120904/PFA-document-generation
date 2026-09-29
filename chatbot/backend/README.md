# Chatbot Backend

## Role

The chatbot backend handles the conversation layer.

It is responsible for:

- authentication
- chat sessions
- message history
- query optimization
- context retrieval
- answer generation
- calling the LightRAG retrieval API

It does not orchestrate the full document pipeline.

## Important behavior

For `/chat/message`, the backend:

- does not call `orchestration_service`
- uses its own internal workflow
- calls `lightrag_service` directly for retrieval

## `/chat/message` flow

1. the frontend sends the user message
2. the backend validates the user token
3. it loads the session and recent history
4. it may rewrite the query with `query_optimizer`
5. it calls `lightrag_service`
6. it filters the returned chunks
7. it builds the final answer
8. it saves the conversation state

## Main endpoints

- `POST /auth/signup`
- `POST /auth/login`
- `GET /auth/me`
- `POST /chat/message`
- `GET /chat/sessions`
- `GET /chat/sessions/{session_id}/messages`
- `DELETE /chat/sessions/{session_id}`
- `GET /health`

## Environment configuration

Main file:

- `chatbot/backend/.env`

Template:

- `chatbot/backend/.env.example`

Important groups of variables:

### Query optimizer

- `CHATBOT_QUERY_OPTIMIZER_MODEL`
- `CHATBOT_QUERY_OPTIMIZER_API_KEY`
- `CHATBOT_QUERY_OPTIMIZER_BASE_URL`
- `CHATBOT_QUERY_OPTIMIZER_TIMEOUT_SECONDS`
- `CHATBOT_QUERY_OPTIMIZER_MAX_RETRIES`

### Retrieval behavior

- `CHATBOT_RETRIEVAL_ENABLED`
- `CHATBOT_RETRIEVAL_SEARCH_TYPE`
- `CHATBOT_RETRIEVAL_TOP_K`
- `CHATBOT_RETRIEVAL_ENABLE_RERANKER`
- `CHATBOT_RETRIEVAL_RERANK_TOP_N`
- `CHATBOT_RETRIEVAL_CONTEXT_TOP_N`
- `CHATBOT_RETRIEVAL_MAX_CHUNKS`
- `CHATBOT_RETRIEVAL_MAX_CHUNK_CHARS`
- `CHATBOT_RETRIEVAL_MIN_RERANK_SCORE`
- `CHATBOT_RETRIEVAL_ORIGINAL_SUFFICIENT_SCORE`

### Main LLM

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `LLM_MODEL_NAME`
- `TIKTOKEN_MODEL_NAME`

### Summary / answer models

- `CHATBOT_SUMMARY_MODEL`
- `CHATBOT_ANSWER_MODEL`
- `CHATBOT_SUMMARY_TRIGGER_MESSAGES`
- `CHATBOT_SUMMARY_TRIGGER_TOKENS`
- `CHATBOT_SUMMARY_KEEP_MESSAGES`
- `CHATBOT_SUMMARY_TRIM_TOKENS`

### Memory / Qdrant

- `CHATBOT_MEMORY_LLM_MODEL`
- `CHATBOT_MEMORY_EMBEDDING_MODEL`
- `CHATBOT_MEMORY_EMBEDDING_DIM`
- `CHATBOT_MEMORY_BASE_URL`
- `CHATBOT_MEMORY_API_KEY`
- `CHATBOT_MEMORY_TOP_K`
- `CHATBOT_MEMORY_EXISTING_LIMIT`
- `QDRANT_URL`
- `QDRANT_COLLECTION`
- `QDRANT_API_KEY`

### LightRAG access

- `LIGHTRAG_SERVICE_URL`
- `LIGHTRAG_TIMEOUT_SECONDS`

## Example local gateway setup

If you use a local OpenAI-compatible gateway:

```env
CHATBOT_QUERY_OPTIMIZER_MODEL=ministral-3:8b
CHATBOT_QUERY_OPTIMIZER_API_KEY=dummy-or-real-token
CHATBOT_QUERY_OPTIMIZER_BASE_URL=http://102.54.244.89:8088/ollama-v2/api/v1

OPENAI_API_KEY=dummy-or-real-token
OPENAI_BASE_URL=http://102.54.244.89:8088/ollama-v2/api/v1
LLM_MODEL_NAME=ministral-3:8b
```

## Local startup

```bash
cd /mnt/c/Users/sfirdaou/Downloads/system_rag1/rag_system
source .venv/bin/activate
set -a
source chatbot/backend/.env
set +a
uvicorn chatbot.backend.app:app --host 127.0.0.1 --port 8015 --reload
```

## Health check

```bash
curl http://127.0.0.1:8015/health
```

## Simple API test

```bash
curl -X POST http://127.0.0.1:8015/chat/message \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d "{\"session_id\": null, \"message\": \"What is writing?\"}"
```

## Frontend settings relation

The frontend does not fill backend `.env` values directly.

There are two configuration layers:

1. backend `.env`
   - controls model URLs, API keys, Qdrant, LightRAG, and runtime behavior

2. frontend Settings / runtime configuration UI
   - controls runtime headers and user-facing configuration values passed to services
   - does not replace every backend `.env` variable

Use backend `.env` for server-side defaults and secrets.

## Retry behavior

The chatbot backend uses short retries only for selected outbound HTTP calls:

- typically `2` attempts
- short sleep
- retryable network/timeout/5xx cases only

Long retries in chat are discouraged because they increase total user response time.

## Troubleshooting

### Slow query optimizer

If logs show:

- `query_optimizer.llm start`
- then `done` after several seconds

the latency is usually coming from the model gateway, not from the frontend.

### Generic answer instead of document-grounded answer

This usually means:

- no chunk passed the rerank threshold
- or the retrieved context was not strong enough

### Unauthorized

If `/chat/message` returns `401`, the token is invalid or expired.
