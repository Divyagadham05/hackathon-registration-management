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
import threading
import time
import unicodedata
from collections import deque
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from dotenv import load_dotenv
from flask import Flask, Response, g, jsonify, request, session
from groq import APIError
from werkzeug.security import check_password_hash, generate_password_hash

if __package__:
    from .chatbot import (
        ChatbotNotConfigured,
        ChatbotResponseError,
        get_chatbot_reply,
        get_rag_chatbot_reply,
        get_food_facility_reply,
        get_hackathon_faq_reply,
        redact_sensitive_content,
    )
    from .database import connect_database
    from . import embeddings as embedding_client
    from .hackathon_faq import OUT_OF_SCOPE_REPLY, OUT_OF_SCOPE_TERMS
    from .hackathon_knowledge import (
        UNKNOWN_INFO_REPLY,
        get_chatbot_greeting_reply,
        get_chatbot_refusal_message,
        is_hackathon_question,
        retrieve_hackathon_context,
    )
    from .rag import (
        embed_missing_chunks,
        index_document,
        invalidate_cache,
        reindex_all,
        retrieve as retrieve_knowledge,
        retrieve_hybrid,
        retrieve_semantic,
    )
else:
    from chatbot import (
        ChatbotNotConfigured,
        ChatbotResponseError,
        get_chatbot_reply,
        get_rag_chatbot_reply,
        get_food_facility_reply,
        get_hackathon_faq_reply,
        redact_sensitive_content,
    )
    from database import connect_database
    import embeddings as embedding_client
    from hackathon_faq import OUT_OF_SCOPE_REPLY, OUT_OF_SCOPE_TERMS
    from hackathon_knowledge import (
        UNKNOWN_INFO_REPLY,
        get_chatbot_greeting_reply,
        get_chatbot_refusal_message,
        is_hackathon_question,
        retrieve_hackathon_context,
    )
    from rag import (
        embed_missing_chunks,
        index_document,
        invalidate_cache,
        reindex_all,
        retrieve as retrieve_knowledge,
        retrieve_hybrid,
        retrieve_semantic,
    )


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
logging.basicConfig(level=logging.INFO)

FACTUAL_DATE_PATTERN = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+\d{1,2}(?:\s*(?:-|–|—|to)\s*\d{1,2})?"
    r"(?:,?\s+\d{4})?\b",
    re.IGNORECASE,
)
FACTUAL_TIME_PATTERN = re.compile(
    r"\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b",
    re.IGNORECASE,
)
FACTUAL_NUMBER_PATTERN = re.compile(r"(?<![\w])\d+(?:[.,]\d+)?%?(?![\w])")


def _grounding_facts(text):
    text = re.sub(r"(?m)^\s*\d+[.)]\s+", "", text)
    normalized = text.casefold().replace("–", "-").replace("—", "-")
    facts = set()
    for pattern in (FACTUAL_DATE_PATTERN, FACTUAL_TIME_PATTERN):
        for match in pattern.finditer(normalized):
            facts.add(re.sub(r"\s+", " ", match.group(0)).strip())
    facts.update(match.group(0).replace(",", ".") for match in FACTUAL_NUMBER_PATTERN.finditer(normalized))
    return facts


def _has_grounded_facts(reply, chunks):
    answer_facts = _grounding_facts(reply)
    if not answer_facts:
        return True
    context_facts = _grounding_facts(" ".join(chunk["chunk_text"] for chunk in chunks))
    context_text = " ".join(chunk["chunk_text"] for chunk in chunks).casefold()
    normalized_context = context_text.replace("–", "-").replace("—", "-")
    context_numbers = {
        match.group(0).replace(",", ".")
        for match in FACTUAL_NUMBER_PATTERN.finditer(normalized_context)
    }
    return all(
        fact in context_facts or fact in context_numbers or fact in normalized_context
        for fact in answer_facts
    )

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
FOOD_FACILITY_TYPES = (
    "Breakfast",
    "Lunch",
    "Evening Snacks",
    "Dinner",
    "Tea Stall",
    "Coffee Stall",
    "Other Beverages",
    "Drinking Water",
)
FOOD_AVAILABILITY_OPTIONS = {"Available", "Unavailable", "Not Announced Yet"}
FOOD_PRICE_OPTIONS = {"Free", "Paid", "Not Announced Yet"}
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TRACK_SEED_DATA = (
    {
        "slug": "artificial-intelligence",
        "number": "01",
        "title": "Artificial Intelligence",
        "tagline": "Build intelligent tools that make everyday life better.",
        "description": (
            "Explore how systems can recognize patterns, reason over information, "
            "and support people in their daily work. Focus on useful, understandable "
            "solutions that keep human needs at the center."
        ),
        "color_class": "track-purple",
        "problem_statements": [
            "Help students find trustworthy answers across long course materials.",
            "Make local public services easier to discover and navigate.",
            "Build an assistive tool that makes everyday digital tasks more accessible.",
            "Detect recurring maintenance issues before they disrupt a shared space.",
        ],
        "suggested_tech": ["Python", "scikit-learn", "PyTorch", "FastAPI", "OpenCV"],
        "resources": [
            {"label": "scikit-learn documentation", "url": "https://scikit-learn.org/stable/"},
            {"label": "PyTorch tutorials", "url": "https://pytorch.org/tutorials/"},
        ],
        "sort_order": 1,
        "registration_domain": "Artificial Intelligence",
    },
    {
        "slug": "generative-ai",
        "number": "02",
        "title": "Generative AI",
        "tagline": "Reimagine how we create, learn, and work.",
        "description": (
            "Use generative models to help people turn ideas into useful drafts, "
            "media, or interactive experiences. Design for clear user control, "
            "grounded outputs, and responsible use rather than novelty alone."
        ),
        "color_class": "track-orange",
        "problem_statements": [
            "Create a study companion that turns a learner's notes into practice activities.",
            "Help community groups produce clear, accessible versions of public information.",
            "Build a creative prototyping tool that keeps the user in control of each revision.",
            "Make a grounded assistant that answers from a small, trusted document collection.",
        ],
        "suggested_tech": ["Python", "Transformers", "Hugging Face", "FastAPI", "React"],
        "resources": [
            {"label": "Hugging Face documentation", "url": "https://huggingface.co/docs"},
            {"label": "Transformers quick tour", "url": "https://huggingface.co/docs/transformers/quicktour"},
        ],
        "sort_order": 2,
        "registration_domain": "Generative AI",
    },
    {
        "slug": "web-development",
        "number": "03",
        "title": "Web Development",
        "tagline": "Create digital experiences that bring people together.",
        "description": (
            "Build useful web experiences that make services and ideas easier to "
            "reach. Strong entries combine thoughtful interaction, accessible "
            "interfaces, and reliable foundations across devices."
        ),
        "color_class": "track-blue",
        "problem_statements": [
            "Connect volunteers with nearby community projects that need their skills.",
            "Help campus clubs publish events in one searchable, accessible place.",
            "Make it easier for people to compare and discover local learning opportunities.",
            "Create a collaborative workspace for planning a small community initiative.",
        ],
        "suggested_tech": ["React", "Vite", "Flask", "PostgreSQL", "Web APIs"],
        "resources": [
            {"label": "React documentation", "url": "https://react.dev/learn"},
            {"label": "MDN Web Docs", "url": "https://developer.mozilla.org/en-US/docs/Learn"},
        ],
        "sort_order": 3,
        "registration_domain": "Web Development",
    },
    {
        "slug": "data-science",
        "number": "04",
        "title": "Data Science",
        "tagline": "Find the insight that changes everything.",
        "description": (
            "Turn messy information into evidence people can understand and act "
            "on. Combine careful data preparation, meaningful analysis, and clear "
            "visual storytelling while respecting privacy and context."
        ),
        "color_class": "track-green",
        "problem_statements": [
            "Reveal patterns in public transit data that could improve daily journeys.",
            "Help a campus understand energy use and identify practical opportunities to save.",
            "Turn public health data into a clear view of changing local needs.",
            "Build an interactive guide that explains how a dataset supports its conclusions.",
        ],
        "suggested_tech": ["Python", "pandas", "Jupyter", "scikit-learn", "Plotly"],
        "resources": [
            {"label": "pandas getting started", "url": "https://pandas.pydata.org/docs/getting_started/"},
            {"label": "Jupyter documentation", "url": "https://docs.jupyter.org/en/latest/"},
        ],
        "sort_order": 4,
        "registration_domain": "Data Science",
    },
    {
        "slug": "cybersecurity",
        "number": "05",
        "title": "Cybersecurity",
        "tagline": "Make the connected world a safer place.",
        "description": (
            "Explore practical ways to protect people, information, and connected "
            "systems. Build defensive tools that make safer choices easier and "
            "communicate risk without collecting unnecessary personal data."
        ),
        "color_class": "track-pink",
        "problem_statements": [
            "Help people recognize suspicious messages with clear, explainable guidance.",
            "Build a privacy checklist that helps a small organization review its online presence.",
            "Make account-security concepts easier to understand through an interactive learning tool.",
            "Create a safe dashboard for spotting unusual activity in synthetic system logs.",
        ],
        "suggested_tech": ["Python", "OWASP guidance", "Flask", "SQLite", "Docker"],
        "resources": [
            {"label": "OWASP Top 10", "url": "https://owasp.org/www-project-top-ten/"},
            {"label": "NIST Cybersecurity Framework", "url": "https://www.nist.gov/cyberframework"},
        ],
        "sort_order": 5,
        "registration_domain": "Cybersecurity",
    },
    {
        "slug": "open-innovation",
        "number": "06",
        "title": "Open Innovation",
        "tagline": "Got an idea that doesn't fit a box? This one's yours.",
        "description": (
            "Bring a problem you care about even when it crosses disciplines or "
            "does not fit another track. Shape a focused prototype around the "
            "people it serves, and explain how you would learn whether it helps."
        ),
        "color_class": "track-yellow",
        "problem_statements": [
            "Design a practical tool for a challenge in your community that other tracks do not cover.",
            "Make everyday campus processes easier to understand or complete.",
            "Explore a low-cost way to help people share skills and resources locally.",
            "Prototype an inclusive experience for a group whose needs are often overlooked.",
        ],
        "suggested_tech": ["Choose tools for your idea", "React", "Python", "Figma", "Open data"],
        "resources": [
            {"label": "Human-centered design resources", "url": "https://www.designkit.org/resources"},
            {"label": "Mozilla Web Docs", "url": "https://developer.mozilla.org/en-US/docs/Web"},
        ],
        "sort_order": 6,
        "registration_domain": "Other",
    },
)


def create_app():
    app = Flask(__name__)
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("Set SECRET_KEY in backend/.env before starting the application.")
    try:
        chatbot_max_message_length = int(os.environ.get("CHATBOT_MAX_MESSAGE_LENGTH", "500"))
    except ValueError as exc:
        raise RuntimeError("CHATBOT_MAX_MESSAGE_LENGTH must be an integer from 1 to 1200.") from exc
    if not 1 <= chatbot_max_message_length <= 1200:
        raise RuntimeError("CHATBOT_MAX_MESSAGE_LENGTH must be an integer from 1 to 1200.")

    database_url = os.environ.get("DATABASE_URL", "").strip()
    database_path = None
    if not database_url:
        database_path = Path(os.environ.get("DATABASE_PATH", "instance/hackathon.db"))
        if not database_path.is_absolute():
            database_path = BASE_DIR / database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)

    app.config.update(
        SECRET_KEY=secret_key,
        DATABASE=database_path,
        DATABASE_URL=database_url or None,
        DATABASE_TYPE="postgres" if database_url else "sqlite",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
        MAX_CONTENT_LENGTH=1024 * 1024,
        CHATBOT_MAX_MESSAGE_LENGTH=chatbot_max_message_length,
        RAG_ENABLED=os.environ.get("RAG_ENABLED", "false").strip().lower() == "true",
    )
    chat_requests = {}
    chat_requests_lock = threading.Lock()

    def get_db():
        if "db" not in g:
            g.db = connect_database(
                app.config["DATABASE_URL"],
                app.config["DATABASE"],
            )
        return g.db

    app.get_db = get_db

    @app.teardown_appcontext
    def close_db(_error=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    with app.app_context():
        db = get_db()
        schema_name = "schema_postgres.sql" if app.config["DATABASE_TYPE"] == "postgres" else "schema.sql"
        db.executescript((BASE_DIR / schema_name).read_text(encoding="utf-8"))
        document_columns = {
            row["column_name"] if app.config["DATABASE_TYPE"] == "postgres" else row["name"]
            for row in db.execute(
                """SELECT column_name FROM information_schema.columns
                   WHERE table_schema = current_schema() AND table_name = 'knowledge_documents'"""
                if app.config["DATABASE_TYPE"] == "postgres"
                else "PRAGMA table_info(knowledge_documents)"
            ).fetchall()
        }
        document_column_migrations = {
            "source_type": "TEXT NOT NULL DEFAULT 'custom'",
            "source_key": "TEXT NOT NULL DEFAULT ''",
            "title": "TEXT NOT NULL DEFAULT ''",
            "content": "TEXT NOT NULL DEFAULT ''",
            "published": (
                "BOOLEAN NOT NULL DEFAULT TRUE"
                if app.config["DATABASE_TYPE"] == "postgres"
                else "INTEGER NOT NULL DEFAULT 1"
            ),
            "origin": "TEXT NOT NULL DEFAULT 'system'",
            "updated_at": (
                "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
                if app.config["DATABASE_TYPE"] == "postgres"
                else "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ),
        }
        for column, definition in document_column_migrations.items():
            if column not in document_columns:
                db.execute(
                    f"ALTER TABLE knowledge_documents ADD COLUMN {column} {definition}"
                )
        chunk_columns = {
            row["column_name"] if app.config["DATABASE_TYPE"] == "postgres" else row["name"]
            for row in db.execute(
                """SELECT column_name FROM information_schema.columns
                   WHERE table_schema = current_schema() AND table_name = 'knowledge_chunks'"""
                if app.config["DATABASE_TYPE"] == "postgres"
                else "PRAGMA table_info(knowledge_chunks)"
            ).fetchall()
        }
        chunk_column_migrations = {
            "document_id": "INTEGER REFERENCES knowledge_documents(id) ON DELETE CASCADE",
            "chunk_index": "INTEGER NOT NULL DEFAULT 0",
            "text": "TEXT NOT NULL DEFAULT ''",
            "token_count": "INTEGER NOT NULL DEFAULT 0",
            "embedding": "TEXT",
            "content_hash": "TEXT",
            "embedding_model": "TEXT",
            "updated_at": (
                "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
                if app.config["DATABASE_TYPE"] == "postgres"
                else "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ),
        }
        for column, definition in chunk_column_migrations.items():
            if column not in chunk_columns:
                db.execute(
                    f"ALTER TABLE knowledge_chunks ADD COLUMN {column} {definition}"
                )
        if app.config["DATABASE_TYPE"] == "postgres":
            registration_columns = {
                row["column_name"]
                for row in db.execute(
                    """SELECT column_name FROM information_schema.columns
                       WHERE table_schema = current_schema() AND table_name = 'registrations'"""
                ).fetchall()
            }
        else:
            registration_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(registrations)").fetchall()
            }
        if "email_sent" not in registration_columns:
            default = "FALSE" if app.config["DATABASE_TYPE"] == "postgres" else "0"
            db.execute(
                f"ALTER TABLE registrations ADD COLUMN email_sent BOOLEAN NOT NULL DEFAULT {default}"
            )
        if "email_notice" not in registration_columns:
            db.execute("ALTER TABLE registrations ADD COLUMN email_notice TEXT")
        if app.config["DATABASE_TYPE"] == "postgres":
            food_columns = {
                row["column_name"]
                for row in db.execute(
                    """SELECT column_name FROM information_schema.columns
                       WHERE table_schema = current_schema() AND table_name = 'food_facilities'"""
                ).fetchall()
            }
        else:
            food_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(food_facilities)").fetchall()
            }
        for column in ("start_time", "end_time", "items"):
            if column not in food_columns:
                db.execute(f"ALTER TABLE food_facilities ADD COLUMN {column} TEXT")
        if "published" not in food_columns:
            default = "FALSE" if app.config["DATABASE_TYPE"] == "postgres" else "0"
            db.execute(
                f"ALTER TABLE food_facilities ADD COLUMN published BOOLEAN NOT NULL DEFAULT {default}"
            )
        if app.config["DATABASE_TYPE"] == "postgres":
            track_columns = {
                row["column_name"]
                for row in db.execute(
                    """SELECT column_name FROM information_schema.columns
                       WHERE table_schema = current_schema() AND table_name = 'tracks'"""
                ).fetchall()
            }
        else:
            track_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(tracks)").fetchall()
            }
        track_column_migrations = {
            "slug": "TEXT NOT NULL DEFAULT ''",
            "number": "TEXT NOT NULL DEFAULT ''",
            "title": "TEXT NOT NULL DEFAULT ''",
            "tagline": "TEXT NOT NULL DEFAULT ''",
            "description": "TEXT NOT NULL DEFAULT ''",
            "color_class": "TEXT NOT NULL DEFAULT 'track-purple'",
            "problem_statements": "TEXT NOT NULL DEFAULT '[]'",
            "suggested_tech": "TEXT NOT NULL DEFAULT '[]'",
            "resources": "TEXT NOT NULL DEFAULT '[]'",
            "sort_order": "INTEGER NOT NULL DEFAULT 0",
            "published": (
                "BOOLEAN NOT NULL DEFAULT FALSE"
                if app.config["DATABASE_TYPE"] == "postgres"
                else "INTEGER NOT NULL DEFAULT 0"
            ),
            "registration_domain": "TEXT NOT NULL DEFAULT 'Other'",
            "updated_at": (
                "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
                if app.config["DATABASE_TYPE"] == "postgres"
                else "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ),
        }
        for column, definition in track_column_migrations.items():
            if column not in track_columns:
                db.execute(f"ALTER TABLE tracks ADD COLUMN {column} {definition}")
        if db.execute("SELECT COUNT(*) AS count FROM tracks").fetchone()["count"] == 0:
            for track in TRACK_SEED_DATA:
                db.execute(
                    """INSERT INTO tracks
                       (slug, number, title, tagline, description, color_class,
                        problem_statements, suggested_tech, resources, sort_order,
                        published, registration_domain)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        track["slug"],
                        track["number"],
                        track["title"],
                        track["tagline"],
                        track["description"],
                        track["color_class"],
                        json.dumps(track["problem_statements"]),
                        json.dumps(track["suggested_tech"]),
                        json.dumps(track["resources"]),
                        track["sort_order"],
                        True,
                        track["registration_domain"],
                    ),
                )
        admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
        admin_password = os.environ.get("ADMIN_PASSWORD", "")
        if admin_email and admin_password:
            if len(admin_password) < 12:
                raise RuntimeError("ADMIN_PASSWORD must be at least 12 characters.")
            db.execute(
                """INSERT INTO users (full_name, email, password_hash, is_admin)
                   VALUES (?, ?, ?, TRUE)
                   ON CONFLICT(email) DO UPDATE SET
                       is_admin = TRUE,
                       password_hash = excluded.password_hash""",
                (
                    "Hackathon Organizer",
                    admin_email,
                    generate_password_hash(admin_password),
                ),
            )
        db.commit()
        try:
            reindex_all(db, embed=False)
        except Exception:
            app.logger.warning("Knowledge base startup reindex failed.", exc_info=True)
            try:
                db.rollback()
            except Exception:
                app.logger.warning(
                    "Knowledge base startup rollback failed.", exc_info=True
                )
        if embedding_client.embeddings_available():
            def embed_startup_chunks():
                try:
                    with app.app_context():
                        result = embed_missing_chunks(get_db())
                        app.logger.info(
                            "Startup knowledge embeddings complete: %d embedded, %d unchanged.",
                            result["chunks_embedded"],
                            result["chunks_skipped_unchanged"],
                        )
                except Exception:
                    app.logger.warning(
                        "Background knowledge embedding failed; keyword retrieval remains available.",
                        exc_info=True,
                    )

            threading.Thread(
                target=embed_startup_chunks,
                name="knowledge-embeddings",
                daemon=True,
            ).start()

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

    def refresh_knowledge_index():
        try:
            reindex_all(get_db())
        except Exception:
            app.logger.warning("Knowledge base refresh failed.", exc_info=True)
            try:
                get_db().rollback()
            except Exception:
                app.logger.warning(
                    "Knowledge base refresh rollback failed.", exc_info=True
                )

    def strip_control_characters(value):
        return "".join(
            character
            for character in str(value)
            if character in "\n\t" or unicodedata.category(character) != "Cc"
        )

    def record_knowledge_gap(db, question):
        safe_question = strip_control_characters(
            redact_sensitive_content(str(question))
        ).strip()[:200]
        normalized_question = safe_question.lower().strip()
        if not normalized_question:
            return
        try:
            db.execute(
                """INSERT INTO knowledge_gaps
                   (question, normalized_question, times_asked, status)
                   VALUES (?, ?, 1, 'open')
                   ON CONFLICT(normalized_question) DO UPDATE SET
                       question = excluded.question,
                       times_asked = knowledge_gaps.times_asked + 1,
                       last_seen = CURRENT_TIMESTAMP,
                       status = 'open'""",
                (safe_question, normalized_question),
            )
            excess = db.execute(
                "SELECT COUNT(*) AS count FROM knowledge_gaps"
            ).fetchone()["count"] - 500
            if excess > 0:
                db.execute(
                    """DELETE FROM knowledge_gaps WHERE id IN (
                           SELECT id FROM knowledge_gaps
                           ORDER BY CASE status WHEN 'resolved' THEN 0 ELSE 1 END,
                                    first_seen ASC, id ASC
                           LIMIT ?
                       )""",
                    (excess,),
                )
            db.commit()
        except Exception:
            db.rollback()
            app.logger.warning("Knowledge gap logging failed.")

    def refresh_knowledge_document(document_id):
        db = get_db()
        row = db.execute(
            "SELECT * FROM knowledge_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            return False
        result = index_document(
            db,
            {
                "source_type": row["source_type"],
                "source_key": row["source_key"],
                "title": row["title"],
                "content": row["content"],
                "published": bool(row["published"]),
                "origin": row["origin"],
            },
        )
        db.commit()
        embedding_pending = False
        if bool(row["published"]) and result["chunks"]:
            embedding_pending = True
            try:
                embedding_result = embed_missing_chunks(db, document_id=document_id)
                embedding_pending = (
                    not embedding_result.get("embeddings_available", False)
                    or embedding_result.get("embedding_error", False)
                    or embedding_result.get("chunks_embedded", 0)
                    + embedding_result.get("chunks_skipped_unchanged", 0)
                    < result["chunks"]
                )
            except Exception:
                db.rollback()
                app.logger.warning(
                    "Embedding knowledge document %s failed; saved content remains searchable by keyword.",
                    document_id,
                )
        invalidate_cache()
        return embedding_pending

    def consume_chat_request(user_id):
        now = time.monotonic()
        window_start = now - 60
        with chat_requests_lock:
            timestamps = chat_requests.setdefault(user_id, deque())
            while timestamps and timestamps[0] <= window_start:
                timestamps.popleft()
            if len(timestamps) >= 10:
                return False
            timestamps.append(now)
            return True

    def food_facility_dict(row, public=False):
        if row is None:
            result = {
                "id": None,
                "facility_type": None,
                "timing": None,
                "start_time": None,
                "end_time": None,
                "items": None,
                "availability": None,
                "price_status": None,
                "charges": None,
                "location": None,
                "published": False,
                "updated_at": None,
            }
        else:
            result = dict(row)
            result["published"] = bool(result.get("published"))
        if public:
            result["timing"] = result["timing"] or "Not Announced Yet"
            result["start_time"] = result["start_time"] or "Not Announced Yet"
            result["end_time"] = result["end_time"] or "Not Announced Yet"
            result["items"] = result["items"] or "Not Announced Yet"
            result["availability"] = result["availability"] or "Not Announced Yet"
            result["price_status"] = result["price_status"] or "Not Announced Yet"
            result["charges"] = result["charges"] or (
                "Free" if result["price_status"] == "Free" else "Not Announced Yet"
            )
            result["location"] = result["location"] or "Not Announced Yet"
        return result

    def food_facility_is_published(row):
        if not bool(row["published"]):
            return False
        for field in ("timing", "start_time", "end_time", "items", "charges", "location"):
            value = row[field]
            if isinstance(value, str) and value.strip() and value.strip().casefold() != "not announced yet":
                return True
        return row["availability"] in {"Available", "Unavailable"} or row["price_status"] in {"Free", "Paid"}

    def track_to_dict(row):
        result = dict(row)
        for field in ("problem_statements", "suggested_tech", "resources"):
            result[field] = json.loads(result[field] or "[]")
        result["published"] = bool(result["published"])
        return result

    def validate_track(data, existing=None):
        if not isinstance(data, dict):
            return None, {"title": "Provide track details."}
        source = {**(existing or {}), **data}
        errors = {}
        values = {}
        string_fields = {
            "slug": 100,
            "number": 3,
            "title": 100,
            "tagline": 180,
            "description": 2000,
            "color_class": 40,
            "registration_domain": 50,
        }
        for field, max_length in string_fields.items():
            value = source.get(field)
            if not isinstance(value, str) or not value.strip():
                errors[field] = "This field is required."
                continue
            value = value.strip()
            if len(value) > max_length:
                errors[field] = f"Use no more than {max_length} characters."
            values[field] = value
        if "slug" in values and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", values["slug"]):
            errors["slug"] = "Use lowercase letters, numbers, and single hyphens."
        if "number" in values and not re.fullmatch(r"\d{1,3}", values["number"]):
            errors["number"] = "Use a track number containing 1 to 3 digits."
        if "color_class" in values and not re.fullmatch(r"track-[a-z0-9-]+", values["color_class"]):
            errors["color_class"] = "Use a valid track color class."
        if "registration_domain" in values and values["registration_domain"] not in DOMAINS:
            errors["registration_domain"] = "Choose a valid registration domain."

        for field, max_items, item_length in (
            ("problem_statements", 10, 500),
            ("suggested_tech", 20, 100),
        ):
            items = source.get(field)
            if not isinstance(items, list) or not 1 <= len(items) <= max_items:
                errors[field] = f"Provide between 1 and {max_items} items."
                continue
            cleaned = []
            for item in items:
                if not isinstance(item, str) or not item.strip() or len(item.strip()) > item_length:
                    errors[field] = f"Each item must contain 1 to {item_length} characters."
                    break
                cleaned.append(item.strip())
            values[field] = cleaned

        resources = source.get("resources")
        if not isinstance(resources, list) or len(resources) > 20:
            errors["resources"] = "Provide no more than 20 resource links."
        else:
            cleaned_resources = []
            for resource in resources:
                if not isinstance(resource, dict):
                    errors["resources"] = "Each resource needs a label and URL."
                    break
                label, url = resource.get("label"), resource.get("url")
                if (
                    not isinstance(label, str)
                    or not label.strip()
                    or len(label.strip()) > 120
                    or not isinstance(url, str)
                    or len(url.strip()) > 2048
                ):
                    errors["resources"] = "Each resource needs a label and URL."
                    break
                try:
                    parsed = urlparse(url.strip())
                    valid_url = parsed.scheme == "https" and bool(parsed.netloc)
                except ValueError:
                    valid_url = False
                if not valid_url:
                    errors["resources"] = "Resource URLs must use HTTPS."
                    break
                cleaned_resources.append({"label": label.strip(), "url": url.strip()})
            values["resources"] = cleaned_resources

        sort_order = source.get("sort_order")
        if isinstance(sort_order, bool) or not isinstance(sort_order, int) or sort_order < 0:
            errors["sort_order"] = "Sort order must be a non-negative integer."
        else:
            values["sort_order"] = sort_order
        published = source.get("published")
        if type(published) is not bool:
            errors["published"] = "Choose whether to publish this track."
        else:
            values["published"] = published
        if errors:
            return None, errors
        return values, None

    def validate_food_facility(data):
        if not isinstance(data, dict):
            return None, {"facility_type": "Provide food facility details."}
        field_errors = {}
        facility_type = data.get("facility_type")
        if not isinstance(facility_type, str) or facility_type not in FOOD_FACILITY_TYPES:
            field_errors["facility_type"] = "Choose a valid food facility."

        text_fields = {
            "timing": 120,
            "items": 2000,
            "charges": 100,
            "location": 300,
        }
        values = {}
        for field, max_length in text_fields.items():
            value = data.get(field, "")
            if not isinstance(value, str):
                field_errors[field] = "Enter text for this field."
                continue
            value = value.strip()
            if len(value) > max_length:
                field_errors[field] = f"Use no more than {max_length} characters."
            values[field] = value or None

        for field in ("start_time", "end_time"):
            value = data.get(field, "")
            if not isinstance(value, str):
                field_errors[field] = "Enter a valid time."
                continue
            value = value.strip()
            if value and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
                field_errors[field] = "Enter a valid time."
            values[field] = value or None
        if values.get("start_time") or values.get("end_time"):
            values["timing"] = None

        availability = data.get("availability")
        if not isinstance(availability, str) or availability not in FOOD_AVAILABILITY_OPTIONS:
            field_errors["availability"] = "Choose a valid availability."
        price_status = data.get("price_status")
        if not isinstance(price_status, str) or price_status not in FOOD_PRICE_OPTIONS:
            field_errors["price_status"] = "Choose a valid free/paid status."
        published = data.get("published", True)
        if type(published) is not bool:
            field_errors["published"] = "Choose whether to publish this facility."
        charges = values.get("charges")
        if price_status == "Paid" and not charges:
            field_errors["charges"] = "Enter the price for a paid facility."
        if field_errors:
            return None, field_errors
        if price_status == "Free":
            values["charges"] = None
        values.update(
            facility_type=facility_type,
            availability=availability,
            price_status=price_status,
            published=published,
        )
        return values, None

    def registration_to_dict(row):
        result = dict(row)
        result["team_members"] = json.loads(result["team_members"])
        result["team_size"] = int(result["team_size"]) if result["team_size"] is not None else None
        if isinstance(result.get("created_at"), datetime):
            result["created_at"] = result["created_at"].isoformat(sep=" ", timespec="seconds")
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
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return error("Provide valid request details.", 400)
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
            db.execute(
                "INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(password)),
            )
            db.commit()
        except (sqlite3.IntegrityError, psycopg.IntegrityError):
            db.rollback()
            return error("An account with that email already exists.", 409)
        session.clear()
        session["user_id"] = db.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,),
        ).fetchone()["id"]
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
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return error("Provide valid request details.", 400)
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
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return error("Provide valid request details.", 400)
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
        except (sqlite3.IntegrityError, psycopg.IntegrityError):
            db.rollback()
            return error("A registration already exists for this account.", 409)
        row = db.execute("SELECT * FROM registrations WHERE user_id = ?", (user["id"],)).fetchone()
        saved = registration_to_dict(row)
        email_sent, email_message = send_confirmation(saved)
        db.execute(
            "UPDATE registrations SET email_sent = ?, email_notice = ? WHERE user_id = ?",
            (email_sent, email_message, user["id"]),
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
            match_operator = "ILIKE" if app.config["DATABASE_TYPE"] == "postgres" else "LIKE"
            query += (
                f" AND (full_name {match_operator} ? OR email {match_operator} ?"
                f" OR college_name {match_operator} ? OR registration_id {match_operator} ?)"
            )
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

    @app.post("/api/admin/knowledge/reindex")
    def admin_knowledge_reindex():
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        counts = reindex_all(get_db())
        embedding_counts = counts.pop("embedding")
        return jsonify(
            {
                "counts": counts,
                **embedding_counts,
            }
        )

    @app.get("/api/admin/knowledge/search")
    def admin_knowledge_search():
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        question = request.args.get("q", "").strip()
        if not question:
            return error("Provide a search question in q.")
        try:
            k = int(request.args.get("k", "4"))
        except ValueError:
            return error("k must be an integer from 1 to 20.")
        if not 1 <= k <= 20:
            return error("k must be an integer from 1 to 20.")
        mode = request.args.get("mode", "hybrid").strip().lower()
        if mode not in {"bm25", "semantic", "hybrid"}:
            return error("mode must be bm25, semantic, or hybrid.")
        db = get_db()
        if mode == "bm25":
            bm25_results = retrieve_knowledge(db, question, k=k)
            results = [
                {
                    "chunk_text": item["chunk_text"],
                    "title": item["title"],
                    "source_type": item["source_type"],
                    "source_key": item["source_key"],
                    "bm25_score": item["score"],
                    "semantic_score": None,
                    "fused_score": 0.0,
                }
                for item in bm25_results
            ]
            return jsonify({"mode": mode, "results": results})
        if mode == "semantic":
            try:
                semantic_results = retrieve_semantic(db, question, k=k)
            except embedding_client.EmbeddingError as exc:
                return error(str(exc), 503)
            bm25_by_key = {
                item["source_key"] + "\0" + item["chunk_text"]: item["score"]
                for item in retrieve_knowledge(db, question, k=1000)
            }
            results = [
                {
                    **item,
                    "bm25_score": bm25_by_key.get(
                        item["source_key"] + "\0" + item["chunk_text"], 0.0
                    ),
                    "fused_score": 0.0,
                }
                for item in semantic_results
            ]
            return jsonify({"mode": mode, "results": results})
        result = retrieve_hybrid(db, question, k=k)
        return jsonify(result)

    @app.get("/api/admin/knowledge/status")
    def admin_knowledge_status():
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        db = get_db()
        document_count = db.execute(
            "SELECT COUNT(*) AS count FROM knowledge_documents"
        ).fetchone()["count"]
        chunk_count = db.execute(
            """SELECT COUNT(*) AS count FROM knowledge_chunks AS c
               JOIN knowledge_documents AS d ON d.id = c.document_id
               WHERE d.published = TRUE"""
        ).fetchone()["count"]
        embedded_count = db.execute(
            """SELECT COUNT(*) AS count FROM knowledge_chunks AS c
               JOIN knowledge_documents AS d ON d.id = c.document_id
               WHERE d.published = TRUE AND c.embedding IS NOT NULL"""
        ).fetchone()["count"]
        return jsonify(
            {
                "document_count": document_count,
                "chunk_count": chunk_count,
                "embedded_chunk_count": embedded_count,
                "embedding_model": embedding_client.embedding_model(),
                "embedding_dimension": embedding_client.embedding_dimension(),
                "embeddings_available": embedding_client.embeddings_available(),
            }
        )

    @app.get("/api/admin/knowledge/documents")
    def admin_knowledge_documents():
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        search = request.args.get("q", "").strip()
        origin = request.args.get("origin", "").strip().lower()
        if origin and origin not in {"system", "admin"}:
            return error("origin must be system or admin.")
        match_operator = "ILIKE" if app.config["DATABASE_TYPE"] == "postgres" else "LIKE"
        query = """SELECT d.id, d.title, d.source_type, d.origin, d.published,
                          d.updated_at,
                          (SELECT COUNT(*) FROM knowledge_chunks c
                           WHERE c.document_id = d.id) AS chunk_count,
                          (SELECT COUNT(*) FROM knowledge_chunks c
                           WHERE c.document_id = d.id AND c.embedding IS NOT NULL)
                           AS embedded_chunk_count
                   FROM knowledge_documents d WHERE 1=1"""
        params = []
        if search:
            query += (
                f" AND (d.title {match_operator} ? OR d.content {match_operator} ?)"
            )
            params.extend([f"%{search}%", f"%{search}%"])
        if origin:
            query += " AND d.origin = ?"
            params.append(origin)
        query += " ORDER BY d.updated_at DESC, d.id DESC"
        rows = get_db().execute(query, params).fetchall()
        return jsonify(
            {
                "documents": [
                    {
                        "id": row["id"],
                        "title": row["title"],
                        "source_type": row["source_type"],
                        "origin": row["origin"],
                        "published": bool(row["published"]),
                        "chunk_count": row["chunk_count"],
                        "embedded_chunk_count": row["embedded_chunk_count"],
                        "updated_at": str(row["updated_at"]),
                    }
                    for row in rows
                ]
            }
        )

    @app.get("/api/admin/knowledge/documents/<int:document_id>")
    def admin_knowledge_document(document_id):
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        db = get_db()
        row = db.execute(
            "SELECT * FROM knowledge_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            return error("Knowledge document not found.", 404)
        chunks = db.execute(
            """SELECT id, chunk_index, text, token_count, embedding IS NOT NULL AS embedded,
                      updated_at
               FROM knowledge_chunks WHERE document_id = ? ORDER BY chunk_index""",
            (document_id,),
        ).fetchall()
        return jsonify(
            {
                "document": {
                    "id": row["id"],
                    "title": row["title"],
                    "content": row["content"],
                    "source_type": row["source_type"],
                    "source_key": row["source_key"],
                    "origin": row["origin"],
                    "published": bool(row["published"]),
                    "updated_at": str(row["updated_at"]),
                    "chunks": [
                        {
                            "id": chunk["id"],
                            "chunk_index": chunk["chunk_index"],
                            "text": chunk["text"],
                            "token_count": chunk["token_count"],
                            "embedded": bool(chunk["embedded"]),
                            "updated_at": str(chunk["updated_at"]),
                        }
                        for chunk in chunks
                    ],
                }
            }
        )

    def validate_knowledge_document(data, existing=None):
        title = strip_control_characters(data.get("title", "")).strip()
        content = strip_control_characters(data.get("content", "")).strip()
        errors = {}
        if not 3 <= len(title) <= 120:
            errors["title"] = "Title must be between 3 and 120 characters."
        if not 20 <= len(content) <= 4000:
            errors["content"] = "Content must be between 20 and 4000 characters."
        published = data.get(
            "published",
            bool(existing["published"]) if existing is not None else True,
        )
        if not isinstance(published, bool):
            errors["published"] = "Published must be true or false."
        return {"title": title, "content": content, "published": published}, errors

    @app.post("/api/admin/knowledge/documents")
    def admin_knowledge_document_create():
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return error("Provide a JSON document.")
        document, field_errors = validate_knowledge_document(data)
        if field_errors:
            return error("Check the document fields.", field_errors=field_errors)
        db = get_db()
        count = db.execute(
            "SELECT COUNT(*) AS count FROM knowledge_documents WHERE origin = 'admin'"
        ).fetchone()["count"]
        if count >= 200:
            return error("The limit of 200 custom knowledge documents has been reached.", 409)
        temporary_key = f"admin:pending:{secrets.token_hex(16)}"
        db.execute(
            """INSERT INTO knowledge_documents
               (source_type, source_key, title, content, published, origin)
               VALUES ('custom', ?, ?, ?, ?, 'admin')""",
            (
                temporary_key,
                document["title"],
                document["content"],
                document["published"],
            ),
        )
        document_id = db.execute(
            "SELECT id FROM knowledge_documents WHERE source_key = ?",
            (temporary_key,),
        ).fetchone()["id"]
        db.execute(
            "UPDATE knowledge_documents SET source_key = ? WHERE id = ?",
            (f"admin:{document_id}", document_id),
        )
        embedding_pending = refresh_knowledge_document(document_id)
        db = get_db()
        row = db.execute(
            "SELECT * FROM knowledge_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        return jsonify(
            {
                "document": {
                    "id": row["id"],
                    "title": row["title"],
                    "source_type": row["source_type"],
                    "origin": row["origin"],
                    "published": bool(row["published"]),
                    "updated_at": str(row["updated_at"]),
                },
                "embedding_pending": embedding_pending,
            }
        ), 201

    @app.put("/api/admin/knowledge/documents/<int:document_id>")
    def admin_knowledge_document_update(document_id):
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        db = get_db()
        existing = db.execute(
            "SELECT * FROM knowledge_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if existing is None:
            return error("Knowledge document not found.", 404)
        if existing["origin"] != "admin":
            return error("System knowledge documents cannot be edited here.", 403)
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return error("Provide a JSON document.")
        document, field_errors = validate_knowledge_document(data, existing)
        if field_errors:
            return error("Check the document fields.", field_errors=field_errors)
        db.execute(
            """UPDATE knowledge_documents SET title = ?, content = ?, published = ?,
               updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (
                document["title"],
                document["content"],
                document["published"],
                document_id,
            ),
        )
        embedding_pending = refresh_knowledge_document(document_id)
        return jsonify({"ok": True, "embedding_pending": embedding_pending})

    @app.patch("/api/admin/knowledge/documents/<int:document_id>/publish")
    def admin_knowledge_document_publish(document_id):
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        db = get_db()
        existing = db.execute(
            "SELECT * FROM knowledge_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if existing is None:
            return error("Knowledge document not found.", 404)
        data = request.get_json(silent=True)
        if data is not None and not isinstance(data, dict):
            return error("Provide a JSON publication setting.")
        published = data.get("published") if isinstance(data, dict) else None
        if published is None:
            published = not bool(existing["published"])
        elif not isinstance(published, bool):
            return error(
                "Published must be true or false.",
                field_errors={"published": "Published must be true or false."},
            )
        db.execute(
            """UPDATE knowledge_documents SET published = ?,
               updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (published, document_id),
        )
        embedding_pending = refresh_knowledge_document(document_id)
        return jsonify(
            {"ok": True, "published": published, "embedding_pending": embedding_pending}
        )

    @app.delete("/api/admin/knowledge/documents/<int:document_id>")
    def admin_knowledge_document_delete(document_id):
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        db = get_db()
        existing = db.execute(
            "SELECT origin FROM knowledge_documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if existing is None:
            return error("Knowledge document not found.", 404)
        if existing["origin"] != "admin":
            return error("System knowledge documents cannot be deleted here.", 403)
        db.execute("DELETE FROM knowledge_chunks WHERE document_id = ?", (document_id,))
        db.execute("DELETE FROM knowledge_documents WHERE id = ?", (document_id,))
        db.commit()
        invalidate_cache()
        return jsonify({"ok": True})

    @app.get("/api/admin/knowledge/gaps")
    def admin_knowledge_gaps():
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        rows = get_db().execute(
            """SELECT id, question, times_asked, first_seen, last_seen, status
               FROM knowledge_gaps
               ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END,
                        times_asked DESC, last_seen DESC"""
        ).fetchall()
        return jsonify(
            {
                "gaps": [
                    {
                        "id": row["id"],
                        "question": row["question"],
                        "times_asked": row["times_asked"],
                        "first_seen": str(row["first_seen"]),
                        "last_seen": str(row["last_seen"]),
                        "status": row["status"],
                    }
                    for row in rows
                ]
            }
        )

    @app.patch("/api/admin/knowledge/gaps/<int:gap_id>")
    def admin_knowledge_gap_update(gap_id):
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        data = request.get_json(silent=True)
        status = data.get("status") if isinstance(data, dict) else None
        if status not in {"open", "resolved"}:
            return error(
                "status must be open or resolved.",
                field_errors={"status": "Choose open or resolved."},
            )
        db = get_db()
        cursor = db.execute(
            "UPDATE knowledge_gaps SET status = ? WHERE id = ?",
            (status, gap_id),
        )
        if cursor.rowcount == 0:
            return error("Knowledge gap not found.", 404)
        db.commit()
        return jsonify({"ok": True, "status": status})

    @app.delete("/api/admin/knowledge/gaps/<int:gap_id>")
    def admin_knowledge_gap_delete(gap_id):
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        db = get_db()
        cursor = db.execute("DELETE FROM knowledge_gaps WHERE id = ?", (gap_id,))
        if cursor.rowcount == 0:
            return error("Knowledge gap not found.", 404)
        db.commit()
        return jsonify({"ok": True})

    @app.get("/api/tracks")
    def public_tracks():
        rows = get_db().execute(
            "SELECT * FROM tracks WHERE published = TRUE ORDER BY sort_order, id"
        ).fetchall()
        return jsonify({"tracks": [track_to_dict(row) for row in rows]})

    @app.get("/api/tracks/<slug>")
    def public_track(slug):
        row = get_db().execute(
            "SELECT * FROM tracks WHERE slug = ? AND published = TRUE",
            (slug,),
        ).fetchone()
        if row is None:
            return error("Track not found.", 404)
        return jsonify({"track": track_to_dict(row)})

    @app.get("/api/admin/tracks")
    def admin_tracks():
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        rows = get_db().execute("SELECT * FROM tracks ORDER BY sort_order, id").fetchall()
        return jsonify({"tracks": [track_to_dict(row) for row in rows]})

    @app.post("/api/admin/tracks")
    def create_track():
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        values, field_errors = validate_track(request.get_json(silent=True))
        if field_errors:
            return error("Check the track details.", field_errors=field_errors)
        db = get_db()
        try:
            cursor = db.execute(
                """INSERT INTO tracks
                   (slug, number, title, tagline, description, color_class,
                    problem_statements, suggested_tech, resources, sort_order,
                    published, registration_domain)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                (
                    values["slug"],
                    values["number"],
                    values["title"],
                    values["tagline"],
                    values["description"],
                    values["color_class"],
                    json.dumps(values["problem_statements"]),
                    json.dumps(values["suggested_tech"]),
                    json.dumps(values["resources"]),
                    values["sort_order"],
                    values["published"],
                    values["registration_domain"],
                ),
            )
            track_id = cursor.fetchone()["id"]
            db.commit()
        except (sqlite3.IntegrityError, psycopg.IntegrityError):
            db.rollback()
            return error("A track with that slug or title already exists.", 409)
        row = db.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
        refresh_knowledge_index()
        return jsonify({"track": track_to_dict(row)}), 201

    @app.patch("/api/admin/tracks/<int:track_id>")
    def update_track(track_id):
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        db = get_db()
        current = db.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
        if current is None:
            return error("Track not found.", 404)
        values, field_errors = validate_track(
            request.get_json(silent=True),
            track_to_dict(current),
        )
        if field_errors:
            return error("Check the track details.", field_errors=field_errors)
        try:
            db.execute(
                """UPDATE tracks
                   SET slug = ?, number = ?, title = ?, tagline = ?, description = ?,
                       color_class = ?, problem_statements = ?, suggested_tech = ?,
                       resources = ?, sort_order = ?, published = ?,
                       registration_domain = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (
                    values["slug"],
                    values["number"],
                    values["title"],
                    values["tagline"],
                    values["description"],
                    values["color_class"],
                    json.dumps(values["problem_statements"]),
                    json.dumps(values["suggested_tech"]),
                    json.dumps(values["resources"]),
                    values["sort_order"],
                    values["published"],
                    values["registration_domain"],
                    track_id,
                ),
            )
            db.commit()
        except (sqlite3.IntegrityError, psycopg.IntegrityError):
            db.rollback()
            return error("A track with that slug or title already exists.", 409)
        row = db.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
        refresh_knowledge_index()
        return jsonify({"track": track_to_dict(row)})

    @app.delete("/api/admin/tracks/<int:track_id>")
    def delete_track(track_id):
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        db = get_db()
        cursor = db.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
        if cursor.rowcount == 0:
            return error("Track not found.", 404)
        db.commit()
        refresh_knowledge_index()
        return jsonify({"ok": True})

    @app.get("/api/food-facilities")
    def public_food_facilities():
        rows = get_db().execute(
            "SELECT * FROM food_facilities ORDER BY id"
        ).fetchall()
        facilities = [
            food_facility_dict(row, public=True)
            for row in rows
            if food_facility_is_published(row)
        ]
        return jsonify({"food_facilities": facilities})

    @app.get("/api/admin/food-facilities")
    def admin_food_facilities():
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        rows = get_db().execute(
            "SELECT * FROM food_facilities ORDER BY id"
        ).fetchall()
        return jsonify({"food_facilities": [food_facility_dict(row) for row in rows]})

    @app.post("/api/admin/food-facilities")
    def create_food_facility():
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        values, field_errors = validate_food_facility(request.get_json(silent=True))
        if field_errors:
            return error("Check the food facility details.", field_errors=field_errors)
        db = get_db()
        try:
            cursor = db.execute(
                """INSERT INTO food_facilities
                   (facility_type, timing, start_time, end_time, items, availability,
                    price_status, charges, location, published)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                (
                    values["facility_type"],
                    values["timing"],
                    values["start_time"],
                    values["end_time"],
                    values["items"],
                    values["availability"],
                    values["price_status"],
                    values["charges"],
                    values["location"],
                    values["published"],
                ),
            )
            facility_id = cursor.fetchone()["id"]
            db.commit()
        except (sqlite3.IntegrityError, psycopg.IntegrityError):
            db.rollback()
            return error("This food facility already exists. Edit the existing entry.", 409)
        row = db.execute(
            "SELECT * FROM food_facilities WHERE id = ?",
            (facility_id,),
        ).fetchone()
        refresh_knowledge_index()
        return jsonify({"food_facility": food_facility_dict(row)}), 201

    @app.put("/api/admin/food-facilities/<int:facility_id>")
    def update_food_facility(facility_id):
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        values, field_errors = validate_food_facility(request.get_json(silent=True))
        if field_errors:
            return error("Check the food facility details.", field_errors=field_errors)
        db = get_db()
        try:
            cursor = db.execute(
                """UPDATE food_facilities
                   SET facility_type = ?, timing = ?, start_time = ?, end_time = ?, items = ?,
                       availability = ?, price_status = ?, charges = ?, location = ?,
                       published = ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (
                    values["facility_type"],
                    values["timing"],
                    values["start_time"],
                    values["end_time"],
                    values["items"],
                    values["availability"],
                    values["price_status"],
                    values["charges"],
                    values["location"],
                    values["published"],
                    facility_id,
                ),
            )
        except (sqlite3.IntegrityError, psycopg.IntegrityError):
            db.rollback()
            return error("This food facility already exists. Edit the existing entry.", 409)
        if cursor.rowcount == 0:
            return error("Food facility not found.", 404)
        db.commit()
        row = db.execute(
            "SELECT * FROM food_facilities WHERE id = ?",
            (facility_id,),
        ).fetchone()
        refresh_knowledge_index()
        return jsonify({"food_facility": food_facility_dict(row)})

    @app.delete("/api/admin/food-facilities/<int:facility_id>")
    def delete_food_facility(facility_id):
        _, auth_error = require_user(admin=True)
        if auth_error:
            return auth_error
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error
        db = get_db()
        cursor = db.execute(
            "DELETE FROM food_facilities WHERE id = ?",
            (facility_id,),
        )
        if cursor.rowcount == 0:
            return error("Food facility not found.", 404)
        db.commit()
        refresh_knowledge_index()
        return jsonify({"ok": True})

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
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return error("Provide valid request details.", 400)
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

    def handle_rag_chat(validated_messages, question):
        started_at = time.perf_counter()
        redacted_question = redact_sensitive_content(question)
        retrieval_mode = None
        retrieval_results = []

        def log_path(path, warning=None):
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            log_data = {
                "path": path,
                "retrieval_mode": retrieval_mode,
                "top_sources": [
                    {
                        "source_key": item["source_key"],
                        "score": item.get("fused_score", item.get("score")),
                    }
                    for item in retrieval_results[:3]
                ],
                "latency_ms": elapsed_ms,
                "question": redacted_question[:200],
            }
            if warning:
                log_data["warning"] = warning
            app.logger.info("chatbot_rag %s", json.dumps(log_data, ensure_ascii=True))

        if OUT_OF_SCOPE_TERMS.search(question):
            log_path("out_of_scope")
            return jsonify({"reply": OUT_OF_SCOPE_REPLY, "sources": []})

        greeting_reply = get_chatbot_greeting_reply(question)
        if greeting_reply:
            log_path("faq")
            return jsonify({"reply": greeting_reply, "sources": []})

        db = get_db()
        food_rows = db.execute(
            "SELECT * FROM food_facilities ORDER BY id"
        ).fetchall()
        food_facilities = [
            food_facility_dict(row, public=True)
            for row in food_rows
            if food_facility_is_published(row)
        ]
        track_rows = db.execute(
            "SELECT * FROM tracks WHERE published = TRUE ORDER BY sort_order, id"
        ).fetchall()
        tracks = [track_to_dict(row) for row in track_rows]

        faq_reply = get_hackathon_faq_reply(question, food_facilities, tracks)
        if faq_reply is not None:
            log_path("faq")
            return jsonify({"reply": faq_reply, "sources": []})

        food_reply = get_food_facility_reply(validated_messages, food_facilities)
        if food_reply is not None:
            log_path("food")
            return jsonify({"reply": food_reply, "sources": []})

        retrieval_question = question
        if len(question.split()) < 5:
            previous_user = next(
                (
                    message["content"]
                    for message in reversed(validated_messages[:-1])
                    if message["role"] == "user"
                ),
                None,
            )
            if previous_user:
                retrieval_question = f"{previous_user}\n{question}"
        retrieval_question = redact_sensitive_content(retrieval_question)
        retrieval = retrieve_hybrid(db, retrieval_question, k=4)
        retrieval_mode = retrieval.get("mode", "hybrid")
        retrieval_results = retrieval.get("results", [])

        if not retrieval_results:
            path = (
                "out_of_scope"
                if not is_hackathon_question(question)
                else "unknown"
            )
            reply = OUT_OF_SCOPE_REPLY if path == "out_of_scope" else UNKNOWN_INFO_REPLY
            if path == "unknown":
                record_knowledge_gap(db, redacted_question)
            log_path(path)
            return jsonify({"reply": reply, "sources": []})

        sources = []
        seen_sources = set()
        for item in retrieval_results:
            source = (item["title"], item["source_type"])
            if source in seen_sources:
                continue
            seen_sources.add(source)
            sources.append({"title": item["title"], "source_type": item["source_type"]})
            if len(sources) == 3:
                break

        fallback = (
            f"{retrieval_results[0]['title']}\n"
            f"{retrieval_results[0]['chunk_text']}"
        )
        rag_messages = [
            {
                "role": message["role"],
                "content": redact_sensitive_content(message["content"]),
            }
            for message in validated_messages[-8:]
        ]
        try:
            reply = get_rag_chatbot_reply(
                rag_messages,
                os.environ.get("HACKATHON_NAME", "Hack the Future"),
                retrieval_results,
            )
        except (ChatbotNotConfigured, ChatbotResponseError, APIError, TimeoutError):
            app.logger.warning(
                "chatbot_rag Groq response failed; using extractive fallback."
            )
            log_path("rag_fallback", warning="groq_failure")
            return jsonify({"reply": fallback, "sources": sources})

        if not _has_grounded_facts(reply, retrieval_results):
            app.logger.warning("chatbot_rag ungrounded_number")
            log_path("rag_fallback", warning="ungrounded_number")
            return jsonify({"reply": fallback, "sources": sources})

        log_path("rag")
        return jsonify({"reply": reply, "sources": sources})

    @app.post("/api/chat")
    def chat():
        user, auth_error = require_user()
        if auth_error:
            return auth_error
        csrf_error = require_csrf()
        if csrf_error:
            return csrf_error

        data = request.get_json(silent=True)
        messages = data.get("messages") if isinstance(data, dict) else None
        if not isinstance(messages, list) or not 1 <= len(messages) <= 12:
            return error("Send up to 12 chat messages.", 400)

        validated_messages = []
        total_characters = 0
        for message in messages:
            if not isinstance(message, dict):
                return error("Check the chat message format.", 400)
            role = message.get("role")
            content = message.get("content")
            if not isinstance(role, str) or role not in {"user", "assistant"} or not isinstance(content, str):
                return error("Check the chat message format.", 400)
            content = content.strip()
            if not content or len(content) > app.config["CHATBOT_MAX_MESSAGE_LENGTH"]:
                return error(
                    "Each chat message must contain 1–{} characters.".format(
                        app.config["CHATBOT_MAX_MESSAGE_LENGTH"]
                    ),
                    400,
                )
            total_characters += len(content)
            if total_characters > 6000:
                return error("The recent chat history is too long. Start a new conversation.", 400)
            validated_messages.append({"role": role, "content": content})

        if validated_messages[-1]["role"] != "user":
            return error("Your latest chat message must be from you.", 400)
        if not consume_chat_request(user["id"]):
            response, status = error(
                "You have reached the chat limit. Please wait a minute and try again.",
                429,
            )
            response.headers["Retry-After"] = "60"
            return response, status

        question = validated_messages[-1]["content"]
        if app.config["RAG_ENABLED"]:
            return handle_rag_chat(validated_messages, question)

        greeting_reply = get_chatbot_greeting_reply(question)
        if greeting_reply:
            return jsonify({"reply": greeting_reply})
        # The existing FAQ/topic allow-list avoids an extra classifier call; uncertain input fails closed.
        if is_hackathon_question(question) is not True:
            return jsonify({"reply": get_chatbot_refusal_message()})

        food_rows = get_db().execute(
            "SELECT * FROM food_facilities ORDER BY id"
        ).fetchall()
        food_facilities = [
            food_facility_dict(row, public=True)
            for row in food_rows
            if food_facility_is_published(row)
        ]
        track_rows = get_db().execute(
            "SELECT * FROM tracks WHERE published = TRUE ORDER BY sort_order, id"
        ).fetchall()
        tracks = [track_to_dict(row) for row in track_rows]
        faq_reply = get_hackathon_faq_reply(question, food_facilities, tracks)
        if faq_reply is not None:
            return jsonify({"reply": faq_reply})

        food_reply = get_food_facility_reply(validated_messages, food_facilities)
        if food_reply is not None:
            return jsonify({"reply": food_reply})
        knowledge_context = retrieve_hackathon_context(question, food_facilities, tracks)
        if not knowledge_context or "Relevant FAQ entries:" not in knowledge_context:
            return jsonify({"reply": UNKNOWN_INFO_REPLY})

        try:
            reply = get_chatbot_reply(
                validated_messages,
                os.environ.get("HACKATHON_NAME", "Hack the Future"),
                knowledge_context,
            )
        except ChatbotNotConfigured:
            app.logger.error("Groq chatbot is unavailable because GROQ_API_KEY is not configured.")
            return error("The chat assistant is not configured yet. Please contact the organizer.", 503)
        except ChatbotResponseError:
            app.logger.error("Groq chatbot returned an empty or invalid response.")
            return error("The chat assistant could not create a reply. Please try again.", 502)
        except (APIError, TimeoutError):
            app.logger.exception("Groq chatbot request failed.")
            return error("The chat assistant is temporarily unavailable. Please try again.", 502)

        return jsonify({"reply": reply})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true",
    )
