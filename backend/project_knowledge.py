import math
import re
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    "README.md",
    "backend/app.py",
    "backend/chatbot.py",
    "backend/database.py",
    "backend/requirements.txt",
    "backend/schema.sql",
    "backend/schema_postgres.sql",
    "render.yaml",
    "frontend/vercel.json",
    "frontend/package.json",
    "frontend/src/App.jsx",
    "frontend/src/Chatbot.jsx",
    "frontend/src/main.jsx",
    "frontend/src/styles.css",
    "frontend/vite.config.js",
)
WORD_PATTERN = re.compile(r"[a-z][a-z0-9_]{1,}", re.IGNORECASE)
STOP_WORDS = {
    "about", "after", "also", "and", "are", "can", "does", "for", "from",
    "have", "how", "into", "its", "not", "our", "please", "that", "the",
    "their", "this", "what", "when", "where", "which", "who", "with", "you",
}
QUERY_SYNONYMS = {
    "about": ("overview", "purpose", "objective"),
    "admin": ("administrator", "organizer", "dashboard", "export"),
    "authentication": ("auth", "login", "session", "csrf", "password"),
    "backend": ("flask", "route", "api"),
    "communicate": ("proxy", "fetch", "api", "request"),
    "database": ("sqlite", "schema", "table", "users", "registrations"),
    "frontend": ("react", "vite", "jsx"),
    "login": ("auth", "session", "csrf", "password", "signup"),
    "project": ("hackathon", "website", "management", "registration"),
    "registration": ("signup", "form", "validate", "confirmation", "email"),
    "tables": ("schema", "sqlite", "users", "registrations"),
    "technologies": ("technology", "stack", "react", "vite", "flask", "python"),
    "technology": ("technologies", "stack", "react", "vite", "flask", "python"),
}
SOURCE_PREFERENCES = {
    "admin": ("backend/app.py", "frontend/src/App.jsx"),
    "authentication": ("backend/app.py", "README.md"),
    "database": ("backend/schema.sql", "backend/app.py"),
    "frontend": ("frontend/package.json", "frontend/vite.config.js"),
    "login": ("backend/app.py", "README.md"),
    "registration": ("backend/app.py", "README.md"),
    "tables": ("backend/schema.sql",),
    "technologies": ("frontend/package.json", "backend/requirements.txt"),
}
CHUNK_SIZE = 1800
CHUNK_OVERLAP = 250


class ProjectKnowledgeUnavailable(Exception):
    pass


def _words(text):
    return [
        word.lower()
        for word in WORD_PATTERN.findall(text)
        if word.lower() not in STOP_WORDS
    ]


def _split_text(text):
    if len(text) <= CHUNK_SIZE:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + CHUNK_SIZE // 2, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - CHUNK_OVERLAP)
    return chunks


def _load_chunks(project_root):
    chunks = []
    for relative_path in SOURCE_FILES:
        path = project_root / relative_path
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ProjectKnowledgeUnavailable(
                f"Could not read the project knowledge source {relative_path}."
            ) from exc
        except UnicodeError as exc:
            raise ProjectKnowledgeUnavailable(
                f"The project knowledge source {relative_path} is not valid UTF-8."
            ) from exc

        for text in _split_text(content):
            terms = Counter(_words(text))
            terms.update(_words(relative_path.replace("/", " ")))
            chunks.append(
                {
                    "source": relative_path,
                    "text": text,
                    "terms": terms,
                }
            )
    return chunks


def retrieve_project_context(messages, project_root=PROJECT_ROOT, limit=5):
    query = " ".join(
        message["content"]
        for message in messages[-6:]
        if isinstance(message.get("content"), str)
    )
    raw_query_terms = Counter(_words(query))
    if not raw_query_terms:
        return ""
    query_terms = dict(raw_query_terms)
    for term in raw_query_terms:
        for synonym in QUERY_SYNONYMS.get(term, ()):
            query_terms.setdefault(synonym, 0.45)

    chunks = _load_chunks(Path(project_root))
    document_frequencies = Counter()
    for chunk in chunks:
        document_frequencies.update(chunk["terms"].keys())

    scored_chunks = []
    total_chunks = len(chunks)
    average_length = (
        sum(sum(chunk["terms"].values()) for chunk in chunks) / total_chunks
        if total_chunks
        else 1
    )
    for chunk in chunks:
        document_length = sum(chunk["terms"].values())
        score = 0.0
        for term, query_weight in query_terms.items():
            frequency = chunk["terms"].get(term, 0)
            if frequency:
                inverse_frequency = math.log(
                    1
                    + (total_chunks - document_frequencies[term] + 0.5)
                    / (document_frequencies[term] + 0.5)
                )
                normalized_frequency = (
                    frequency * 2.5
                    / (
                        frequency
                        + 1.5
                        * (0.25 + 0.75 * document_length / average_length)
                    )
                )
                score += inverse_frequency * normalized_frequency * query_weight
        preferred_sources = {
            source
            for term in raw_query_terms
            for source in SOURCE_PREFERENCES.get(term, ())
        }
        if chunk["source"] in preferred_sources:
            score += 1.5
        if score:
            scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda result: result[0], reverse=True)
    selected_chunks = []
    source_counts = Counter()
    for _, chunk in scored_chunks:
        if source_counts[chunk["source"]] >= 2:
            continue
        selected_chunks.append(chunk)
        source_counts[chunk["source"]] += 1
        if len(selected_chunks) >= limit:
            break
    return "\n\n".join(
        f"Source: {chunk['source']}\n{chunk['text']}"
        for chunk in selected_chunks
    )
