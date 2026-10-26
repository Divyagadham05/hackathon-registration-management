import csv
import io
import json
import logging
import os
import re
import secrets
import smtplib
import sqlite3
import ssl
from datetime import date
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import Flask, Response, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
logging.basicConfig(level=logging.INFO)

DOMAINS = {
    "Artificial Intelligence",
    "Generative AI",
    "Web Development",
    "Data Science",
    "Cybersecurity",
    "Other",
}
DEGREES = {"B.Tech", "B.Sc", "BCA", "MCA", "M.Tech", "Other"}
STATUSES = {"Submitted", "Under Review", "Accepted", "Waitlisted", "Rejected"}
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def create_app():
    app = Flask(__name__)
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("Set SECRET_KEY in backend/.env before starting the application.")

    database_path = Path(os.environ.get("DATABASE_PATH", "instance/hackathon.db"))
    if not database_path.is_absolute():
        database_path = BASE_DIR / database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)

    app.config.update(
        SECRET_KEY=secret_key,
        DATABASE=database_path,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
        MAX_CONTENT_LENGTH=1024 * 1024,
    )

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    app.get_db = get_db

    @app.teardown_appcontext
    def close_db(_error=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    with app.app_context():
        db = get_db()
        db.executescript((BASE_DIR / "schema.sql").read_text(encoding="utf-8"))
        registration_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(registrations)").fetchall()
        }
        if "email_sent" not in registration_columns:
            db.execute("ALTER TABLE registrations ADD COLUMN email_sent INTEGER NOT NULL DEFAULT 0")
        if "email_notice" not in registration_columns:
            db.execute("ALTER TABLE registrations ADD COLUMN email_notice TEXT")
        admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
        admin_password = os.environ.get("ADMIN_PASSWORD", "")
        if admin_email and admin_password:
            if len(admin_password) < 12:
                raise RuntimeError("ADMIN_PASSWORD must be at least 12 characters.")
            db.execute(
                """INSERT INTO users (full_name, email, password_hash, is_admin)
                   VALUES (?, ?, ?, 1)
                   ON CONFLICT(email) DO UPDATE SET
                       is_admin = 1,
                       password_hash = excluded.password_hash""",
                (
                    "Hackathon Organizer",
                    admin_email,
                    generate_password_hash(admin_password),
                ),
            )
        db.commit()

    def error(message, status=400, field_errors=None):
        payload = {"error": message}
        if field_errors:
            payload["field_errors"] = field_errors
        return jsonify(payload), status

    def csrf_valid():
        expected = session.get("csrf_token")
        supplied = request.headers.get("X-CSRF-Token", "")
        return bool(expected and secrets.compare_digest(expected, supplied))

    def require_csrf():
        if not csrf_valid():
            return error("Your session has expired. Refresh the page and try again.", 403)
        return None

    def current_user():
        user_id = session.get("user_id")
        if not user_id:
            return None
        return get_db().execute(
            "SELECT id, full_name, email, is_admin FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    def require_user(admin=False):
        user = current_user()
        if user is None:
            return None, error("Please log in to continue.", 401)
        if admin and not user["is_admin"]:
            return None, error("Administrator access is required.", 403)
        return user, None

    def registration_to_dict(row):
        result = dict(row)
        result["team_members"] = json.loads(result["team_members"])
        result["team_size"] = int(result["team_size"]) if result["team_size"] is not None else None
        return result

    @app.get("/api/csrf")
    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return jsonify({"csrf_token": session["csrf_token"]})

    @app.get("/api/auth")
    def auth_status():
        user = current_user()
        if user is None:
            return jsonify({"user": None})
        return jsonify(
            {
                "user": {
                    "full_name": user["full_name"],
                    "email": user["email"],
                    "is_admin": bool(user["is_admin"]),
                }
            }
        )

    @app.post("/api/signup")
    def signup():
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        data = request.get_json(silent=True) or {}
        name = str(data.get("full_name", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        problems = {}
        if not 2 <= len(name) <= 100:
            problems["full_name"] = "Enter your full name (2–100 characters)."
        if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
            problems["email"] = "Enter a valid email address."
        if len(password) < 10 or len(password) > 128:
            problems["password"] = "Use a password between 10 and 128 characters."
        if problems:
            return error("Please correct the highlighted fields.", field_errors=problems)

        db = get_db()
        try:
            cursor = db.execute(
                "INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(password)),
            )
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            return error("An account with that email already exists.", 409)
        session.clear()
        session["user_id"] = cursor.lastrowid
        session["csrf_token"] = secrets.token_urlsafe(32)
        return jsonify(
            {
                "user": {"full_name": name, "email": email, "is_admin": False},
                "csrf_token": session["csrf_token"],
            }
        ), 201

    @app.post("/api/login")
    def login():
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        data = request.get_json(silent=True) or {}
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        user = get_db().execute(
            "SELECT id, full_name, email, password_hash, is_admin FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            return error("Email or password is incorrect.", 401)
        session.clear()
        session["user_id"] = user["id"]
        session["csrf_token"] = secrets.token_urlsafe(32)
        return jsonify(
            {
                "user": {
                    "full_name": user["full_name"],
                    "email": user["email"],
                    "is_admin": bool(user["is_admin"]),
                },
                "csrf_token": session["csrf_token"],
            }
        )

    @app.post("/api/logout")
    def logout():
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        session.clear()
        return jsonify({"ok": True})

    def validate_registration(data, account_email):
        problems = {}
        required = {
            "full_name": "Full name",
            "mobile_number": "Mobile number",
            "college_name": "College or university",
            "degree": "Degree",
            "department": "Department or branch",
            "year_of_study": "Year of study or graduation year",
            "college_location": "College location",
            "technical_skills": "Programming languages and technical skills",
            "project_idea": "Project idea or problem statement",
        }
        for key, label in required.items():
            value = data.get(key)
            if not isinstance(value, str) or not value.strip():
                problems[key] = f"{label} is required."
            elif len(value.strip()) > 2000:
                problems[key] = f"{label} is too long."

        name = data.get("full_name", "")
        if isinstance(name, str) and not 2 <= len(name.strip()) <= 100:
            problems["full_name"] = "Enter a name between 2 and 100 characters."
        mobile = data.get("mobile_number", "")
        if isinstance(mobile, str):
            digits = re.sub(r"\D", "", mobile)
            if not 7 <= len(digits) <= 15 or not re.fullmatch(r"[+()\-\s\d.]+", mobile):
                problems["mobile_number"] = "Enter a valid mobile number (7–15 digits)."

        dob = data.get("date_of_birth", "")
        if dob:
            try:
                parsed_dob = date.fromisoformat(dob)
                if parsed_dob >= date.today():
                    raise ValueError
            except (TypeError, ValueError):
                problems["date_of_birth"] = "Enter a valid date of birth in the past."

        if not isinstance(data.get("degree"), str) or data.get("degree") not in DEGREES:
            problems["degree"] = "Choose a degree from the list."
        participation = data.get("participation_type")
        if not isinstance(participation, str) or participation not in {"Individual", "Team"}:
            problems["participation_type"] = "Choose Individual or Team participation."

        team_name = data.get("team_name", "")
        team_size = data.get("team_size")
        members = data.get("team_members", [])
        if participation == "Team":
            if not isinstance(team_name, str) or not team_name.strip() or len(team_name) > 100:
                problems["team_name"] = "Enter a team name (up to 100 characters)."
            if isinstance(team_size, bool) or not isinstance(team_size, int) or not 2 <= team_size <= 5:
                problems["team_size"] = "Team size must be between 2 and 5."
            if not isinstance(members, list) or not isinstance(team_size, int) or len(members) != team_size - 1:
                problems["team_members"] = "Enter the name and email for each other team member."
            else:
                for index, member in enumerate(members):
                    if not isinstance(member, dict):
                        problems["team_members"] = "Check the team member details."
                        break
                    member_name = str(member.get("name", "")).strip()
                    member_email = str(member.get("email", "")).strip()
                    if not member_name or len(member_name) > 100 or not EMAIL_PATTERN.fullmatch(member_email):
                        problems["team_members"] = f"Enter a valid name and email for team member {index + 1}."
                        break
            if not isinstance(data.get("team_leader"), str) or not data["team_leader"].strip():
                problems["team_leader"] = "Enter the team leader name."
        elif participation == "Individual":
            team_name, team_size, members = "", None, []

        if not isinstance(data.get("domain"), str) or data.get("domain") not in DOMAINS:
            problems["domain"] = "Choose a hackathon domain."
        project_title = data.get("project_title", "")
        if not isinstance(project_title, str) or len(project_title) > 150:
            problems["project_title"] = "Project title must be 150 characters or fewer."
        github_url = data.get("github_url", "")
        if github_url:
            try:
                parsed = urlparse(github_url) if isinstance(github_url, str) else None
                valid_github_url = parsed is not None and parsed.scheme == "https" and parsed.netloc.lower() in {"github.com", "www.github.com"}
            except ValueError:
                valid_github_url = False
            if not valid_github_url:
                problems["github_url"] = "Enter a valid https://github.com profile URL."
        if data.get("accept_rules") is not True:
            problems["accept_rules"] = "You must accept the hackathon rules and terms."
        if data.get("confirm_information") is not True:
            problems["confirm_information"] = "Please confirm that your information is correct."
        if not EMAIL_PATTERN.fullmatch(account_email):
            problems["email"] = "Your account email is invalid. Please update your account."
        return problems, {
            "full_name": name.strip() if isinstance(name, str) else "",
            "email": account_email,
            "mobile_number": mobile.strip() if isinstance(mobile, str) else "",
            "date_of_birth": dob or None,
            "college_name": data.get("college_name", "").strip() if isinstance(data.get("college_name"), str) else "",
            "degree": data.get("degree", ""),
            "department": data.get("department", "").strip() if isinstance(data.get("department"), str) else "",
            "year_of_study": data.get("year_of_study", "").strip() if isinstance(data.get("year_of_study"), str) else "",
            "college_location": data.get("college_location", "").strip() if isinstance(data.get("college_location"), str) else "",
            "participation_type": participation,
            "team_name": team_name.strip() if isinstance(team_name, str) else "",
            "team_size": team_size if participation == "Team" and isinstance(team_size, int) else None,
            "team_members": members if isinstance(members, list) else [],
            "team_leader": data.get("team_leader", "").strip() if participation == "Team" and isinstance(data.get("team_leader"), str) else "",
            "domain": data.get("domain", ""),
            "technical_skills": data.get("technical_skills", "").strip() if isinstance(data.get("technical_skills"), str) else "",
            "project_title": project_title.strip() if isinstance(project_title, str) else "",
            "project_idea": data.get("project_idea", "").strip() if isinstance(data.get("project_idea"), str) else "",
            "github_url": github_url.strip() if isinstance(github_url, str) else "",
        }

    def send_confirmation(registration):
        host = os.environ.get("SMTP_HOST", "").strip()
        sender = os.environ.get("SMTP_FROM_EMAIL", "").strip()
        if not host or not sender:
            return False, "Email delivery is not configured. Your registration has been saved."
        message = EmailMessage()
        message["Subject"] = "Hackathon Registration Successful!"
        message["From"] = sender
        message["To"] = registration["email"]
        team_line = f"- Team Name: {registration['team_name']}\n" if registration["team_name"] else ""
        message.set_content(
            f"""Dear {registration['full_name']},

Congratulations! You have successfully registered for our hackathon.

Here are your registration details:

- Participant Name: {registration['full_name']}
- College Name: {registration['college_name']}
- Participation Type: {registration['participation_type']}
{team_line}- Hackathon Domain: {registration['domain']}
- Registration ID: {registration['registration_id']}

Thank you for registering. Please keep your registration ID for future reference. Further event updates will be shared through email.

Best regards,
Hackathon Organizing Team
"""
        )
        try:
            port = int(os.environ.get("SMTP_PORT", "587"))
            username = os.environ.get("SMTP_USERNAME", "")
            password = os.environ.get("SMTP_PASSWORD", "")
            if os.environ.get("SMTP_USE_SSL", "false").lower() == "true":
                with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=15) as server:
                    if username:
                        server.login(username, password)
                    server.send_message(message)
            else:
                with smtplib.SMTP(host, port, timeout=15) as server:
                    server.starttls(context=ssl.create_default_context())
                    if username:
                        server.login(username, password)
                    server.send_message(message)
            return True, None
        except (OSError, smtplib.SMTPException, ValueError):
            app.logger.exception("Confirmation email delivery failed for registration %s", registration["registration_id"])
            return False, "Your registration is saved, but the confirmation email could not be delivered."

    @app.route("/api/registration", methods=["GET", "POST"])
    def my_registration():
        user, auth_error = require_user()
        if auth_error:
            return auth_error
        db = get_db()
        if request.method == "GET":
            row = db.execute("SELECT * FROM registrations WHERE user_id = ?", (user["id"],)).fetchone()
            return jsonify({"registration": registration_to_dict(row) if row else None})
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        data = request.get_json(silent=True) or {}
        problems, values = validate_registration(data, user["email"])
        if problems:
            return error("Please correct the highlighted fields.", field_errors=problems)
        registration_id = f"HACK-{secrets.token_hex(5).upper()}"
        columns = [
            "registration_id", "user_id", "full_name", "email", "mobile_number", "date_of_birth",
            "college_name", "degree", "department", "year_of_study", "college_location",
            "participation_type", "team_name", "team_size", "team_members", "team_leader", "domain",
            "technical_skills", "project_title", "project_idea", "github_url",
        ]
        values.update(registration_id=registration_id, user_id=user["id"])
        try:
            db.execute(
                f"INSERT INTO registrations ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                tuple(json.dumps(values[column]) if column == "team_members" else values[column] for column in columns),
            )
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            return error("A registration already exists for this account.", 409)
        row = db.execute("SELECT * FROM registrations WHERE user_id = ?", (user["id"],)).fetchone()
        saved = registration_to_dict(row)
        email_sent, email_message = send_confirmation(saved)
        db.execute(
            "UPDATE registrations SET email_sent = ?, email_notice = ? WHERE user_id = ?",
            (int(email_sent), email_message, user["id"]),
        )
        db.commit()
        return jsonify(
            {
                "registration": saved,
                "email_sent": email_sent,
                "notification": email_message,
            }
        ), 201

    @app.get("/api/admin/registrations")
    def admin_registrations():
        user, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        search = request.args.get("q", "").strip()
        participation = request.args.get("participation_type", "")
        domain = request.args.get("domain", "")
        query = "SELECT * FROM registrations WHERE 1=1"
        params = []
        if search:
            query += " AND (full_name LIKE ? OR email LIKE ? OR college_name LIKE ? OR registration_id LIKE ?)"
            params.extend([f"%{search}%"] * 4)
        if participation in {"Individual", "Team"}:
            query += " AND participation_type = ?"
            params.append(participation)
        if domain in DOMAINS:
            query += " AND domain = ?"
            params.append(domain)
        query += " ORDER BY created_at DESC"
        rows = get_db().execute(query, params).fetchall()
        return jsonify({"registrations": [registration_to_dict(row) for row in rows]})

    @app.get("/api/admin/export.csv")
    def export_registrations():
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        rows = get_db().execute("SELECT * FROM registrations ORDER BY created_at DESC").fetchall()
        output = io.StringIO()
        writer = csv.writer(output)
        columns = [
            "registration_id", "full_name", "email", "mobile_number", "college_name", "degree",
            "department", "year_of_study", "participation_type", "team_name", "team_size", "domain",
            "technical_skills", "project_title", "project_idea", "status", "created_at",
        ]
        writer.writerow(columns)
        for row in rows:
            values = []
            for column in columns:
                value = row[column]
                if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
                    value = "'" + value
                values.append(value)
            writer.writerow(values)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=hackathon-registrations.csv"},
        )

    @app.patch("/api/admin/registrations/<registration_id>")
    def update_registration_status(registration_id):
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        data = request.get_json(silent=True) or {}
        status = data.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            return error("Choose a valid registration status.")
        cursor = get_db().execute(
            "UPDATE registrations SET status = ? WHERE registration_id = ?",
            (status, registration_id),
        )
        get_db().commit()
        if cursor.rowcount == 0:
            return error("Registration not found.", 404)
        return jsonify({"ok": True, "status": status})

    @app.get("/api/config")
    def public_config():
        return jsonify({"hackathon_name": os.environ.get("HACKATHON_NAME", "Hack the Future")})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
