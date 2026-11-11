# Hack the Future — Hackathon Registration

A responsive React application backed by a Flask API. Local development uses SQLite; production uses PostgreSQL so registrations persist across backend deploys. Account passwords are hashed on the server, authentication uses an HttpOnly session cookie, and all registration validation and access control are enforced by the backend. SMTP is optional; a registration is never reported as emailed unless SMTP delivery succeeds.

## Project layout

- `frontend/` — React interface and Vite development server.
- `backend/` — Flask API, SQLite/PostgreSQL database support, authentication, registration and admin routes, and SMTP email.
- `backend/database.py` — database connection adapter for local SQLite and hosted PostgreSQL.
- `backend/schema_postgres.sql` — PostgreSQL schema initialized by the Flask app when `DATABASE_URL` is set.
- `render.yaml` — Render web service configuration for the Flask API.
- `frontend/api/[...path].js` — same-origin Vercel function that forwards `/api/*` requests to the Flask API.
- `backend/chatbot.py` — Groq-powered assistant reply generation and sensitive-value redaction.
- `backend/hackathon_knowledge.py` — Categorized, hackathon-only context retrieval and topic filtering for the assistant.
- `backend/hackathon_faq.py` — Structured FAQ entries, question variations, typo-tolerant matching, and official answers.
- `backend/rag.py` — Knowledge ingestion, chunking, BM25, semantic, and hybrid retrieval.
- `backend/embeddings.py` — Gemini REST embedding client with retries and normalized vectors.
- `backend/knowledge/hackathon_knowledge_base.md` — The 18-section source document ingested into the knowledge index.
- `backend/test_chatbot.py` — Chatbot retrieval, redaction, API validation, and rate-limit tests.
- `backend/test_database.py` — PostgreSQL adapter/startup checks and SQLite API smoke tests.
- `backend/schema.sql` — Database schema; the Flask app creates the tables automatically.
- `backend/.env.example` — Environment variables needed by the backend.
- `backend/app.py` and `frontend/src/App.jsx` — Food facility publishing, the public Food & Facilities page, and database-backed food FAQ answers.

## Run locally (Windows PowerShell)

1. Install Python 3.10+ and Node.js 20.19+ (or 22.12+).
2. Create a virtual environment and install the backend requirements:

   ```powershell
   cd backend
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

3. Edit `backend/.env`. Set `SECRET_KEY` to a long, random value (for example, generate one with `py -c "import secrets; print(secrets.token_hex(32))"`). To use the organizer dashboard, set `ADMIN_EMAIL` and `ADMIN_PASSWORD`; the admin password must be at least 12 characters. For the AI assistant, add your Groq key as `GROQ_API_KEY` in this local `.env` file. The default model is `openai/gpt-oss-120b`; only set `GROQ_MODEL` if you choose a model currently available to your Groq account. Never put the key in React code, commit it, or share it in chat. The assistant is available only to signed-in users. For local testing you may leave SMTP blank; registration will still be saved and the confirmation page will explain that email is not configured.
4. In the `backend` directory, start Flask:

   ```powershell
   py app.py
   ```

   With `DATABASE_URL` empty, Flask initializes the local SQLite database at `backend/instance/hackathon.db` on first run. Set `DATABASE_PATH` to use another local file. When `DATABASE_URL` is set, Flask connects to PostgreSQL and does not create or write a local database file.
5. In a second terminal, install and start the frontend:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

6. Open the Vite URL shown in the terminal (normally `http://localhost:5173`). The Vite development server proxies `/api` requests to Flask at `http://127.0.0.1:5000`.

## How it works

- **Accounts:** Sign-up and login use Flask endpoints. Passwords are stored as Werkzeug password hashes, not plaintext. Authentication uses Flask's signed, HttpOnly session cookie (not JWT); cookies are SameSite=Lax. Requests that change state require a session-bound CSRF token.
- **Registration:** The signed-in user's account email is used as the registration email. The API validates all required fields, domain/degree choices, dates, phone digits, team details and declarations. A unique registration ID is generated and the full registration is committed to SQLite locally or PostgreSQL in production. A unique database constraint prevents duplicate registrations per account.
- **Confirmation:** SMTP delivery happens after the database commit. If SMTP is missing or fails, the registration remains saved and the UI reports the email issue without claiming an email was sent.
- **My registration:** The API looks up registration by the authenticated account ID. Participants cannot supply another user's ID to access private data.
- **Organizer dashboard:** Set both `ADMIN_EMAIL` and `ADMIN_PASSWORD` before starting Flask to provision/promote the organizer account. Admin-only API routes provide searchable/filterable registrations, status changes, details, and CSV export.
- **Food & facilities:** The participant page shows the confirmed schedule: breakfast 8:00–9:00 AM, lunch 1:00–2:00 PM, evening snacks 4:00–4:30 PM, dinner 7:30–8:30 PM, and drinking water throughout the event. All four meals are completely free for eligible participants. Participants must be college students aged 16 or older and may come with family. Organizers can continue to manage the existing facility categories; published timing and menu details update chatbot answers, while the confirmed eligibility and food-price rules take precedence over older records.
- **AI assistant:** The signed-in Hackathon Website Assistant uses the structured FAQ dataset in `backend/hackathon_faq.py`, including question variations and typo-tolerant matching, before considering Groq. It answers known questions directly, uses the categorized knowledge base and current published food records for relevant unanswered questions, and fails closed on unrelated or instruction-overriding requests before Groq is called. Groq receives only matching context under a strict grounding prompt and the latest question. The assistant does not read user records or the database beyond published food information. The browser keeps conversation history in memory, and users can clear it. Common credential formats, email addresses, and phone numbers are redacted before requests to Groq. The endpoint requires the existing session and CSRF token and limits each signed-in account to 10 requests per minute per Flask process. `CHATBOT_REFUSAL_MESSAGE` customizes the fixed out-of-scope reply (default set in `render.yaml`); `CHATBOT_MAX_MESSAGE_LENGTH` sets the per-message limit (default `500`, maximum `1200`). Both are backend/Render settings; neither is needed in Vercel.
- **RAG index and chatbot (Steps 1–3):** The database index includes the 18-section Markdown file, published FAQs, tracks, and food facilities. Search uses BM25 and, when configured, Gemini semantic retrieval merged with Reciprocal Rank Fusion. Unchanged chunks retain their vectors; startup embedding runs in a daemon thread. Set `GEMINI_API_KEY`, `EMBEDDING_MODEL` (default `gemini-embedding-001`), `EMBEDDING_DIM` (default `768`), and optionally `SEMANTIC_MIN_SCORE` (default `0.55`) in backend settings. Set `GEMINI_API_KEY` only in the ignored `backend/.env` locally or Render's environment settings in production—never in source code or frontend settings. Admin-only `POST /api/admin/knowledge/reindex` (CSRF required) rebuilds the system index and reports embedding totals; `GET /api/admin/knowledge/search?q=...&k=4&mode=bm25|semantic|hybrid` previews retrieval; `GET /api/admin/knowledge/status` reports index and embedding status.
- **RAG chatbot:** `RAG_ENABLED` defaults to `false`; in that mode `/api/chat` keeps its legacy behavior and response shape. Set it to `true` to enable blocklist checks, deterministic FAQ/food answers, then grounded hybrid retrieval and a constrained Groq response. If retrieval or Groq fails, the assistant uses safe unknown or extractive answers; ungrounded numbers trigger the extractive fallback. RAG responses include `{"reply":"...","sources":[{"title":"...","source_type":"..."}]}`; deterministic answers may return an empty `sources` list. Structured `chatbot_rag` logs record the path, retrieval mode, top source keys/scores, redacted/truncated question, and latency—never user identifiers or full prompts. To roll back, set `RAG_ENABLED=false` in the backend environment and restart/redeploy; the legacy chat path resumes without a database migration.
- **Knowledge admin:** The organizer's Knowledge tab lists and searches indexed documents, views chunks, manages custom plain-text answers, tests keyword/semantic/hybrid retrieval, and reviews knowledge gaps. Admin-only endpoints (all require an admin session; mutations also require CSRF) are `GET /api/admin/knowledge/documents?q=&origin=system|admin`, `GET /api/admin/knowledge/documents/<id>`, `POST /api/admin/knowledge/documents`, `PUT /api/admin/knowledge/documents/<id>`, `PATCH /api/admin/knowledge/documents/<id>/publish`, and `DELETE /api/admin/knowledge/documents/<id>`. The `system` origin (Markdown, FAQ, track, and food content) is maintained by reindexing; organizers may publish or hide system documents but cannot edit or delete them. `admin` origin documents are custom answers and survive reindexing.
- **Knowledge gaps:** RAG-path questions that are event-related but have no relevant retrieval result are added to the open gaps list. Admin-only `GET /api/admin/knowledge/gaps` lists gaps, `PATCH /api/admin/knowledge/gaps/<id>` marks one `open` or `resolved`, and `DELETE /api/admin/knowledge/gaps/<id>` removes it. Only the redacted question text (up to 200 characters), a normalized form, counts, timestamps, and status are stored; no user ID, email, or IP address is recorded. Repeated questions increment their count, and the table is capped at 500 rows, removing resolved entries first.

## Evaluating the chatbot

Run the local retrieval evaluation from `backend` before deploying:

```powershell
python eval_rag.py
python eval_rag.py --mode all --sweep --json eval-results.json
python eval_rag.py --mode hybrid --baseline eval-results.json --min-hit3 0.90 --min-reject 0.90
```

The harness always uses a temporary SQLite database, reindexes only published knowledge, and never reads the application's real database. It reports Hit@1, Hit@3, MRR, and off-topic rejection rate overall and by case category. Failed cases show expected and retrieved source keys with scores; false-positive off-topic retrievals include their BM25 or semantic scores. Semantic and hybrid modes are clearly skipped if `GEMINI_API_KEY` is unavailable. `--sweep` checks `SEMANTIC_MIN_SCORE` from `0.40` through `0.75`, reusing cached chunks and query embeddings, and recommends the threshold maximizing the lower of Hit@3 and rejection rate. The default quality gates fail the command if any evaluated mode is below 90% Hit@3 or rejection.

Use `--chat` only when you intentionally want to make real Groq/Gemini calls. It exercises `/api/chat` using a temporary test account and throttles calls below the per-user rate limit. Chat reports check required/forbidden answer phrases, source presence, response paths, and ungrounded-number fallbacks; `--min-answer 0.90` adds an answer-pass gate. `--json path` writes full case-level results, and `--baseline path` lists pass/fail flips against an earlier run.

Tuning guide: if off-topic questions are retrieved, raise `SEMANTIC_MIN_SCORE` or add that topic to the blocklist. If real event questions are rejected as unavailable, lower the threshold or add a knowledge document. If a wrong section ranks first, improve that section's wording or include the question phrasing in it. If organizers publish real prize or contact details, update evaluation cases 28–29 and rerun the report.

## Production deployment (Vercel + Render + PostgreSQL)

Vercel serves the React/Vite frontend and a small same-origin API proxy. Render runs Flask and connects it to managed PostgreSQL. The proxy forwards `/api/*` to the backend URL configured in Vercel, preserving the session cookie and CSRF flow without exposing database credentials or requiring cross-origin cookies. The Vite proxy is for local development only.

### Render backend and database

1. Push this repository to GitHub and create a PostgreSQL database. The free web service has an ephemeral filesystem, so local SQLite data is not durable; use a PostgreSQL database for production registrations. Check the database provider's current free-tier limits and retention policy.
2. In Render, create a Blueprint from the repository using the root `render.yaml`. It configures the `hackathon-registration-api` Python web service on the free plan, with `backend` as its root directory, `pip install -r requirements.txt` as its build command, Gunicorn bound to Render's `$PORT`, and `/api/config` as its health check.
3. Set the web service's `DATABASE_URL` to the PostgreSQL connection URL in Render. Prefer the database's internal URL when it is on Render in the same region. Do not put this URL in the repository or Vercel. The app creates its PostgreSQL tables on startup.
4. The Blueprint generates `SECRET_KEY` and enables secure session cookies for HTTPS. These are the backend environment variables:
   - Required: `DATABASE_URL`, `SECRET_KEY`, and `SESSION_COOKIE_SECURE=true` (the Blueprint sets `SECRET_KEY` and `SESSION_COOKIE_SECURE`).
   - `ADMIN_EMAIL` and `ADMIN_PASSWORD` to provision the organizer account. Use a unique password of at least 12 characters.
   - Optional chatbot settings: `GROQ_API_KEY` and `GROQ_MODEL`.
   - Optional email settings: `SMTP_HOST`, `SMTP_PORT` (defaults to `587`), `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, and `SMTP_USE_SSL` (defaults to `false`).
   - Optional display setting: `HACKATHON_NAME`.
   - `PORT` is assigned by Render; do not set it yourself. `PYTHON_VERSION` is set to `3.13.4` in the Blueprint. `DATABASE_PATH` (default `instance/hackathon.db`) and `FLASK_DEBUG` (default `false`) are local-development settings, not production settings.
5. Deploy the service from this repository and wait for Render's `/api/config` health check to succeed. The Blueprint service URL is normally `https://hackathon-registration-api.onrender.com`; use the actual URL shown in the Render dashboard.

All keys and passwords belong only in Render's environment settings. The Groq chatbot and email features remain optional; the rest of the application works without those credentials.

### Vercel frontend

1. Import the same GitHub repository into Vercel and set **Root Directory** to `frontend`.
2. Use the Vite defaults: install `npm install` (or `npm ci`), build `npm run build`, output directory `dist`.
3. In **Vercel → Settings → Environment Variables**, set `API_BACKEND_URL` to the Render backend's HTTPS origin, for example `https://hackathon-registration-api.onrender.com` (no path suffix). Add it for Production and any Preview environments you use.
4. No database URL, `SECRET_KEY`, admin password, Groq key, or `VITE_*` API URL belongs in Vercel. The browser continues to call relative `/api/...` routes; the Vercel function proxies those requests to Flask. Since requests go to Vercel first, the browser sees same-origin requests and no `FRONTEND_URL`/CORS setting is required.
5. Redeploy the Vercel frontend after setting or changing `API_BACKEND_URL`.

### Deployment checks and data

- After deploying the backend, check `https://<your-render-service>.onrender.com/api/config`, `/api/auth`, and `/api/csrf`; each GET should return HTTP 200. `/api/auth` returns `{"user":null}` when signed out; `/api/csrf` also sets a session cookie.
- If the Render root page works but these API routes return 404, Render is serving an old or different app. Confirm the service uses this repository and `backend` as its root directory, then deploy the latest commit. The Blueprint's `/api/config` health check should fail instead of treating that old app as healthy.
- After setting `API_BACKEND_URL` and redeploying Vercel, check the same three paths on the Vercel domain. They should return HTTP 200 before testing signup, login, registration, and the organizer dashboard.
- The hosted PostgreSQL database starts empty. The ignored local `backend/instance/hackathon.db` is not uploaded or migrated automatically; keep it private and request a migration plan if its existing records must be transferred.
- This repository implements signed Flask sessions and CSRF protection, not JWT. That existing authentication is intentionally preserved.
- Render's one-worker Gunicorn configuration preserves the current in-memory chatbot rate limit behavior. If you later scale to multiple backend instances, move rate limiting to shared storage or the hosting edge.
- Keep backups enabled for the production database, use HTTPS, and rotate secrets through Render rather than committing them.

## Useful routes

- `GET /api/auth`, `GET /api/csrf`, `POST /api/signup`, `POST /api/login`, `POST /api/logout`
- `GET /api/registration`, `POST /api/registration`
- `GET /api/tracks`, `GET /api/tracks/<slug>`
- `POST /api/chat` (signed-in session and CSRF token required)
- `GET /api/admin/registrations`, `PATCH /api/admin/registrations/<registration_id>`, `GET /api/admin/export.csv`
- `GET /api/admin/tracks`, `POST /api/admin/tracks`, `PATCH /api/admin/tracks/<id>`, `DELETE /api/admin/tracks/<id>` (organizer session and CSRF token required for writes)

### Redeploy and verify (PowerShell)

1. Push the changes to the Git branch connected to Render and Vercel.
2. In Render, confirm the backend service root directory is `backend`, then choose **Manual Deploy → Deploy latest commit**. Wait until the `/api/config` health check passes.
3. In Vercel, set `API_BACKEND_URL` to the backend's HTTPS origin, then choose **Deployments → Redeploy** for the latest frontend commit.
4. Run this against the Vercel domain. Each result should be `200`:

   ```powershell
   $base = "https://hackathon-registration-management.vercel.app"
   foreach ($route in @("/api/auth", "/api/config", "/api/csrf")) {
     $response = Invoke-WebRequest -Uri "$base$route" -UseBasicParsing
     "$($response.StatusCode) $route"
   }
   ```

The app now shows the backend's useful error response for API failures, identifies missing routes as deployment/routing issues, and reports network failures separately instead of displaying a generic error.

## Run chatbot tests

From the `backend` directory with the virtual environment active:

```powershell
python -m unittest discover -s . -p "test_*.py" -v
```
