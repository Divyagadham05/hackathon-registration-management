# Hack the Future — Hackathon Registration

A responsive React application backed by a Flask API. Local development uses SQLite; production uses PostgreSQL so registrations persist across backend deploys. Account passwords are hashed on the server, authentication uses an HttpOnly session cookie, and all registration validation and access control are enforced by the backend. SMTP is optional; a registration is never reported as emailed unless SMTP delivery succeeds.

## Project layout

- `frontend/` — React interface and Vite development server.
- `backend/` — Flask API, SQLite/PostgreSQL database support, authentication, registration and admin routes, and SMTP email.
- `backend/database.py` — database connection adapter for local SQLite and hosted PostgreSQL.
- `backend/schema_postgres.sql` — PostgreSQL schema initialized by the Flask app when `DATABASE_URL` is set.
- `render.yaml` — Render web service configuration for the Flask API.
- `frontend/vercel.json` — same-origin `/api/*` rewrite from Vercel to the Render API.
- `backend/chatbot.py` — Groq-powered assistant reply generation and sensitive-value redaction.
- `backend/project_knowledge.py` — Allowlisted project-source loading and lightweight keyword retrieval for chatbot context.
- `backend/test_chatbot.py` — Chatbot retrieval, redaction, API validation, and rate-limit tests.
- `backend/test_database.py` — PostgreSQL adapter/startup checks and SQLite API smoke tests.
- `backend/schema.sql` — Database schema; the Flask app creates the tables automatically.
- `backend/.env.example` — Environment variables needed by the backend.
- `backend/app.py` and `frontend/src/App.jsx` — Food facility administration, the public Food & Facilities page, and database-backed food FAQ answers.

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

3. Edit `backend/.env`. Set `SECRET_KEY` to a long, random value (for example, generate one with `py -c "import secrets; print(secrets.token_hex(32))"`). To use the organizer dashboard, set `ADMIN_EMAIL` and `ADMIN_PASSWORD`; the admin password must be at least 12 characters. For the AI assistant, add your Groq key as `GROQ_API_KEY` in this local `.env` file. The default model is `openai/gpt-oss-20b`; only set `GROQ_MODEL` if you choose a model currently available to your Groq account. Never put the key in React code, commit it, or share it in chat. The assistant is available only to signed-in users. For local testing you may leave SMTP blank; registration will still be saved and the confirmation page will explain that email is not configured.
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
- **Food & facilities:** Organizers manage breakfast, lunch, evening snacks, dinner, tea, coffee, other beverages, and drinking water from the existing dashboard. Meal and stall serving times, food items, availability, free/paid status, prices, and locations are stored in the existing SQLite/PostgreSQL database. The participant page groups organizer meals, tea and coffee stalls, and water stations; paid prices are shown only when entered. The chatbot reads current food records directly, replies with the announced values, and uses the organizer-contact message when requested information is missing. Existing SQLite food records are migrated to support separate start/end times and menu items.
- **AI assistant:** Signed-in users can ask questions about the project, frontend, Flask routes, authentication, SQLite/PostgreSQL schemas, registration, and event. Food questions are answered from the current food-facility database records rather than generated by the language model. A small retrieval helper searches an explicit allowlist of README and source files; it never reads `.env`, the database file, or user records. Only the most relevant source excerpts and recent chat are sent to Groq for other project questions. The browser keeps conversation history in memory, and users can clear it. Common credential formats, email addresses, and phone numbers are redacted before messages are sent. The endpoint requires the existing session and CSRF token and limits each signed-in account to 10 requests per minute per Flask process. The assistant is read-only and should not receive sensitive information. If project sources do not answer a question, it is instructed to say so rather than guess.

## Production deployment (Vercel + Render + PostgreSQL)

The Vercel deployment serves only the static React/Vite frontend. Render runs Flask and connects it to managed PostgreSQL. The Vercel rewrite forwards `/api/*` to Render while keeping requests same-origin in the browser, so the existing session cookie and CSRF flow works without exposing database credentials or requiring cross-origin cookies. The Vite proxy is for local development only.

### Render backend and database

1. Push this repository to GitHub and create a persistent PostgreSQL database in Render. Choose a production-capable plan (not a temporary/expiring database) and use the same region for the database and web service.
2. In Render, create a Blueprint from the repository using the root `render.yaml`. The Flask web service is named `hackathon-registration-api`; its build and Gunicorn start commands are configured there.
3. Set the web service's `DATABASE_URL` to the database's **internal** connection URL in Render. Do not put this URL in the repository or Vercel. The app creates its PostgreSQL tables on startup.
4. The Blueprint generates `SECRET_KEY` and enables secure session cookies for HTTPS. In the Render service's environment settings, add the following as needed:
   - `ADMIN_EMAIL` and `ADMIN_PASSWORD` to provision the organizer account. Use a unique password of at least 12 characters.
   - `GROQ_API_KEY` and optionally `GROQ_MODEL` for the AI FAQ chatbot.
   - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, and optionally `SMTP_USE_SSL` for registration confirmation email.
   - Optionally `HACKATHON_NAME` to customize the event name.
5. Deploy and wait for Render's health check at `/api/config` to succeed. Its default service URL should be `https://hackathon-registration-api.onrender.com`.

All keys and passwords belong only in Render's environment settings. The Groq chatbot and email features remain optional; the rest of the application works without those credentials.

### Vercel frontend

1. Import the same GitHub repository into Vercel and set **Root Directory** to `frontend`.
2. Use the Vite defaults: install `npm install` (or `npm ci`), build `npm run build`, output directory `dist`.
3. `frontend/vercel.json` forwards `/api/*` to `https://hackathon-registration-api.onrender.com`. If Render assigned your service a different hostname, update the rewrite destination to that exact HTTPS URL and redeploy Vercel.
4. No `VITE_*` API URL, secret, database password, `SECRET_KEY`, or Groq key is needed in Vercel. The frontend keeps using relative `/api/...` URLs; Vercel proxies them to Flask.

### Deployment checks and data

- Visit `https://<your-render-service>.onrender.com/api/config` to confirm the backend is healthy, then open the Vercel URL and exercise signup, login, registration, and the organizer dashboard.
- The hosted PostgreSQL database starts empty. The ignored local `backend/instance/hackathon.db` is not uploaded or migrated automatically; keep it private and request a migration plan if its existing records must be transferred.
- This repository implements signed Flask sessions and CSRF protection, not JWT. That existing authentication is intentionally preserved.
- Render's one-worker Gunicorn configuration preserves the current in-memory chatbot rate limit behavior. If you later scale to multiple backend instances, move rate limiting to shared storage or the hosting edge.
- Keep backups enabled for the production database, use HTTPS, and rotate secrets through Render rather than committing them.

## Useful routes

- `GET /api/auth`, `GET /api/csrf`, `POST /api/signup`, `POST /api/login`, `POST /api/logout`
- `GET /api/registration`, `POST /api/registration`
- `POST /api/chat` (signed-in session and CSRF token required)
- `GET /api/admin/registrations`, `PATCH /api/admin/registrations/<registration_id>`, `GET /api/admin/export.csv`

## Run chatbot tests

From the `backend` directory with the virtual environment active:

```powershell
python -m unittest discover -s . -p "test_*.py" -v
```
