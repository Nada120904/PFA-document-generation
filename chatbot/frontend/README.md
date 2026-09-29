# Chatbot Frontend

## Role

This is the React/Vite user interface for the project.

It allows a user to:

- sign in
- create, open, and delete chat sessions
- choose a storage provider
- upload a document
- trigger processing and indexing when needed
- ask questions about indexed documents

## Current pages

The main navigation currently exposes:

- `Chatbot`
- `Documents`
- `Settings`

## First screen before login

The frontend can start with a workspace configuration screen before the user reaches login or sign up.

This screen is used to fill runtime configuration values from the browser UI.

Expected user flow:

1. open the frontend
2. fill the configuration form
3. click `Save and continue`
4. continue to login or sign up
5. open the chatbot workspace

Important behavior:

- values entered on this page are stored locally in the browser
- they are attached to API requests as runtime headers
- they are not meant to replace every backend `.env` variable immediately
- they are meant to support runtime configuration from the UI, especially for future deployed/server-based usage

## Real UI flows

### 1. Document pipeline flow

From the right-side document panel:

1. select a storage provider
2. upload a file
3. process the file
4. index the file

The frontend talks mainly to:

- `orchestration_service`
- `upload_service` for some base64 uploads
- `chatbot backend` for chat

### 2. Chat flow

From the chat panel:

1. the user sends a message
2. the frontend calls `chatbot backend`
3. the backend performs retrieval and answer generation
4. the response is shown in the active chat session

## Frontend environment variables

Template file:

- `chatbot/frontend/.env.example`

Typical values:

```env
VITE_CHATBOT_API_URL=/api/chatbot
VITE_ORCHESTRATION_API_URL=/api/orchestration
VITE_UPLOAD_SERVICE_API_URL=/api/upload-service
```

In local development, the Vite proxy should point to:

- `/api/chatbot` -> `http://127.0.0.1:8015`
- `/api/orchestration` -> `http://127.0.0.1:8002`
- `/api/upload-service` -> `http://127.0.0.1:8011`

## Frontend configuration pages

There are two different frontend configuration surfaces:

### 1. Initial configuration gate

This is the first page shown before the user continues to authentication.

Use it when the workspace still needs runtime values to be filled from the browser.

### 2. Settings page

The Settings page is for runtime-facing configuration, not for secret infrastructure setup.

Use it for:

- checking runtime configuration presence
- user/session-level settings
- configuration values exposed through runtime headers

Do not rely on the frontend Settings page for:

- secret API keys
- database URLs
- Qdrant credentials
- server-only model configuration

Those must stay in backend/service `.env` files.

## Local ports

- frontend: `5173`
- chatbot backend: `8015`
- orchestration: `8002`
- upload: `8011`

## Local startup

```bash
cd chatbot/frontend
npm install
npm run dev
```

For a self-contained local run of the whole user-facing flow, use
`python scripts/start_demo.py` from the repository root instead.

Then open:

```text
http://127.0.0.1:5173
```

## Important UI features

### Chat sessions

- create a new chat
- list saved sessions
- delete a session with confirmation

### Refresh button

The `Refresh` button:

- does not perform a full browser reload
- refreshes chatbot state and service status
- can show a spinner while loading

### Document status panel

The document panel shows:

- selected storage provider
- upload state
- processing state
- indexing state
- final status message
- current file
- current overall status

### Play / Retry buttons

The frontend shows:

- `Play` when the previous step succeeded and the next step can be started manually
- `Retry` when a step failed and can be tried again

The button is displayed in the frontend, but the real execution happens through backend endpoints.

## Important logic

### Upload routing

- `.pdf` and `.docx` use a base64 upload flow to `upload_service`
- other files use `orchestration/upload`

### State restoration after refresh

The UI restores the last known document state for the current user.

However, the source of truth remains the backend data:

- `uploaded_documents`
- `document_processing`
- `indexing_runs`

## Troubleshooting

### Blank page

If the page becomes blank:

1. open DevTools
2. check JavaScript errors
3. clear local storage for `127.0.0.1:5173`
4. run `npm run dev` again

### Service counter

The `x/y services online` badge comes from `orchestration/status`.

It does not represent every process in the repository. It represents the services tracked by orchestration.

### PDF blocked by Zscaler

If a PDF is blocked by the corporate network policy:

- upload may succeed
- processing may fail later during remote download
- the final UI state should follow the real failed stage

## Important frontend files

- `src/App.tsx`
- `src/lib/api.ts`
- `src/components/chat/ChatPage.tsx`
- `src/components/layout/AppShell.tsx`
- `src/styles.css`
