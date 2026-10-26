# Hack the Future — Hackathon Registration

A responsive React application backed by a Flask API and SQLite database. Account passwords are hashed on the server, sessions use an HttpOnly cookie, and all registration validation and access control are enforced by the backend. SMTP is optional during local development; a registration is never reported as emailed unless SMTP delivery succeeds.

## Project layout

- `frontend/` — React interface and Vite development server.
- `backend/` — Flask API, SQLite schema, authentication, registration and admin routes, and SMTP email.
- `backend/schema.sql` — Database schema; the Flask app creates the tables automatically.
- `backend/.env.example` — Environment variables needed by the backend.

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

3. Edit `backend/.env`. Set `SECRET_KEY` to a long, random value (for example, generate one with `py -c "import secrets; print(secrets.token_hex(32))"`). To use the organizer dashboard, set `ADMIN_EMAIL` and `ADMIN_PASSWORD`; the admin password must be at least 12 characters. For local testing you may leave SMTP blank; registration will still be saved and the confirmation page will explain that email is not configured.
4. In the `backend` directory, start Flask:

   ```powershell
   py app.py
   ```

   Flask initializes the SQLite database at `backend/instance/hackathon.db` on first run. Override `DATABASE_PATH` if desired.
5. In a second terminal, install and start the frontend:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

6. Open the Vite URL shown in the terminal (normally `http://localhost:5173`). The Vite development server proxies `/api` requests to Flask at `http://127.0.0.1:5000`.

## How it works

- **Accounts:** Sign-up and login use Flask endpoints. Passwords are stored as Werkzeug password hashes, not plaintext. Flask session cookies are HttpOnly and SameSite=Lax. Requests that change state require a session-bound CSRF token.
- **Registration:** The signed-in user's account email is used as the registration email. The API validates all required fields, domain/degree choices, dates, phone digits, team details and declarations. A unique registration ID is generated and the full registration is committed to SQLite. A unique database constraint prevents duplicate registrations per account.
- **Confirmation:** SMTP delivery happens after the database commit. If SMTP is missing or fails, the registration remains saved and the UI reports the email issue without claiming an email was sent.
- **My registration:** The API looks up registration by the authenticated account ID. Participants cannot supply another user's ID to access private data.
- **Organizer dashboard:** Set both `ADMIN_EMAIL` and `ADMIN_PASSWORD` before starting Flask to provision/promote the organizer account. Admin-only API routes provide searchable/filterable registrations, status changes, details, and CSV export.

## Production configuration

- Replace `SECRET_KEY` with a strong, unique secret stored in your hosting provider's secret manager. Never commit `.env`.
- Set `SESSION_COOKIE_SECURE=true` behind HTTPS. Use HTTPS for both frontend and backend.
- Configure an SMTP provider using `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, and optionally `SMTP_USE_SSL=true` for implicit TLS. Confirm the sender/domain with the provider. SMTP credentials remain backend-only.
- Set a unique `ADMIN_EMAIL` and strong `ADMIN_PASSWORD`. The configured account is granted administrator access at startup; protect these variables and rotate the password through your deployment process.
- Use a persistent, backed-up database volume for SQLite or adapt the database layer/schema for a managed production database. SQLite is appropriate for local development and modest single-instance deployments.
- Build the UI with `npm run build`, then deploy the static `frontend/dist` output and Flask API behind a production web server/reverse proxy. The Vite proxy is for development only. Configure the production proxy so the UI and `/api` share an origin, or implement strict same-site cookie/CSRF/CORS settings for a split-origin deployment.
- Configure production logging, backups, monitoring, SMTP deliverability, and abuse/rate limiting with the chosen hosting provider before opening public registration.

## Useful routes

- `GET /api/auth`, `GET /api/csrf`, `POST /api/signup`, `POST /api/login`, `POST /api/logout`
- `GET /api/registration`, `POST /api/registration`
- `GET /api/admin/registrations`, `PATCH /api/admin/registrations/<registration_id>`, `GET /api/admin/export.csv`
