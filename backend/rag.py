import json
import logging
import math
import os
import re
import threading
import time
from collections import OrderedDict
from hashlib import sha256
from pathlib import Path

if __package__:
    from . import embeddings
    from .chatbot import redact_sensitive_content
    from .embeddings import EmbeddingError
    from .hackathon_faq import FAQ_DATASET
    from .hackathon_knowledge import is_hackathon_question
else:
    import embeddings
    from chatbot import redact_sensitive_content
    from embeddings import EmbeddingError
    from hackathon_faq import FAQ_DATASET
    from hackathon_knowledge import is_hackathon_question


BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_BASE_PATH = BASE_DIR / "knowledge" / "hackathon_knowledge_base.md"
SOURCE_TYPES = ("faq", "track", "food", "custom")
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "for",
    "from", "i", "in", "is", "it", "me", "of", "on", "or", "the", "this",
    "to", "with", "you",
}
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[\"'“‘(\[]?[A-Z0-9#*-])")
_WORD_PATTERN = re.compile(r"[a-z0-9]+")
_CACHE_LOCK = threading.RLock()
_TOKENIZED_CHUNKS = None
_VECTOR_CHUNKS = None
_CACHE_SIGNATURE = None
_QUERY_EMBEDDINGS = OrderedDict()
_EMBEDDING_BATCH_SIZE = 20
_EMBEDDING_BATCH_DELAY = 0.1
BM25_MIN_SCORE = 0.1


def _stem(token):
    if token in {"register", "registering", "registration"}:
        return "registr"
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("ing"):
        token = token[:-3]
        if len(token) > 2 and token[-1] == token[-2]:
            token = token[:-1]
        return token
    if len(token) > 3 and token.endswith("ed"):
        token = token[:-2]
        if len(token) > 2 and token[-1] == token[-2]:
            token = token[:-1]
        return token
    if len(token) > 5 and token.endswith("ation"):
        return token[:-5]
    if len(token) > 4 and token.endswith("ion"):
        return token[:-3]
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return _stem(token[:-1])
    return token


def tokenize(text):
    tokens = []
    for token in _WORD_PATTERN.findall(str(text).lower()):
        if token not in STOPWORDS:
            tokens.append(_stem(token))
    return tokens


def _split_sentences(text):
    sentences = []
    for paragraph in re.split(r"\n\s*\n+", text.strip()):
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if not lines:
            continue
        if len(lines) > 1 and all(
            re.match(r"(?:[-*+]\s+|\d+[.)]\s+)", line) for line in lines
        ):
            paragraph_texts = lines
        else:
            paragraph_texts = [" ".join(lines)]
        for paragraph_text in paragraph_texts:
            sentences.extend(
                sentence.strip()
                for sentence in _SENTENCE_BOUNDARY.split(paragraph_text)
                if sentence.strip()
            )
    return sentences


def chunk_text(text, max_words=120, overlap=20, title=None):
    if max_words < 1:
        raise ValueError("max_words must be at least 1.")
    if overlap < 0:
        raise ValueError("overlap cannot be negative.")
    title = str(title or "").strip()
    prefix = f"{title}\n\n" if title else ""
    title_word_count = len(title.split())
    content_limit = max(1, max_words - title_word_count)
    sentences = _split_sentences(str(text))
    if not sentences:
        return []

    sentence_word_counts = [len(sentence.split()) for sentence in sentences]
    chunks = []
    start = 0
    while start < len(sentences):
        end = start
        word_count = 0
        while end < len(sentences):
            next_count = sentence_word_counts[end]
            if end > start and word_count + next_count > content_limit:
                break
            word_count += next_count
            end += 1
            if word_count > content_limit:
                break

        body = " ".join(sentences[start:end])
        chunks.append(prefix + body)
        if end == len(sentences):
            break

        next_start = end
        if overlap:
            overlap_start = end
            overlap_words = 0
            while overlap_start > start and (
                overlap_words + sentence_word_counts[overlap_start - 1] <= overlap
            ):
                overlap_start -= 1
                overlap_words += sentence_word_counts[overlap_start]
            while (
                overlap_start < end
                and overlap_words + sentence_word_counts[end] > content_limit
            ):
                overlap_words -= sentence_word_counts[overlap_start]
                overlap_start += 1
            if overlap_start < end:
                next_start = overlap_start
        start = next_start
    return chunks


def load_markdown_sections(path):
    path = Path(path)
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logging.getLogger(__name__).warning(
            "Knowledge base file is missing: %s", path
        )
        return []

    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", content))
    sections = []
    for index, match in enumerate(matches, start=1):
        end = matches[index].start() if index < len(matches) else len(content)
        body = content[match.end():end]
        body = re.sub(r"(?m)^\s*---\s*$", "", body).strip()
        sections.append(
            {
                "source_type": "custom",
                "source_key": f"kb:{index}",
                "title": match.group(1).strip(),
                "content": body,
                "published": True,
            }
        )
    return sections


def _faq_documents():
    documents = []
    for entry in FAQ_DATASET:
        questions = "\n".join(f"- {question}" for question in entry["questions"])
        documents.append(
            {
                "source_type": "faq",
                "source_key": f"faq:{entry['id']}",
                "title": entry["category"],
                "content": f"Common questions:\n{questions}\n\nOfficial answer:\n{entry['answer']}",
                "published": True,
            }
        )
    return documents


def _row_value(row, key, default=""):
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def _json_list(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return value if isinstance(value, list) else []


def _database_documents(db):
    documents = []
    tracks = db.execute(
        "SELECT * FROM tracks WHERE published = TRUE ORDER BY id"
    ).fetchall()
    for row in tracks:
        title = str(_row_value(row, "title")).strip()
        problem_statements = _json_list(_row_value(row, "problem_statements", "[]"))
        suggested_tech = _json_list(_row_value(row, "suggested_tech", "[]"))
        content = "\n".join(
            (
                f"Track: {title}",
                f"Tagline: {_row_value(row, 'tagline')}",
                f"Description: {_row_value(row, 'description')}",
                "Problem statements: " + "; ".join(map(str, problem_statements)),
                "Suggested technology: " + "; ".join(map(str, suggested_tech)),
            )
        )
        documents.append(
            {
                "source_type": "track",
                "source_key": f"track:{_row_value(row, 'slug')}",
                "title": title,
                "content": content,
                "published": True,
            }
        )

    facilities = db.execute(
        "SELECT * FROM food_facilities WHERE published = TRUE ORDER BY id"
    ).fetchall()
    for row in facilities:
        title = str(_row_value(row, "facility_type")).strip()
        content = "\n".join(
            f"{field.replace('_', ' ').title()}: {_row_value(row, field)}"
            for field in (
                "timing",
                "start_time",
                "end_time",
                "items",
                "availability",
                "price_status",
                "charges",
                "location",
            )
        )
        documents.append(
            {
                "source_type": "food",
                "source_key": f"food:{_row_value(row, 'facility_type')}",
                "title": title,
                "content": content,
                "published": True,
            }
        )
    return documents


def index_document(db, document):
    if document.get("source_type") not in SOURCE_TYPES:
        raise ValueError("Unsupported knowledge document source_type.")
    source_key = str(document["source_key"])
    origin = document.get("origin", "system")
    if origin not in {"system", "admin"}:
        raise ValueError("Unsupported knowledge document origin.")
    title = str(document["title"])
    content = str(document["content"])
    published = bool(document.get("published", True))
    existing_document = db.execute(
        "SELECT id, origin FROM knowledge_documents WHERE source_key = ?",
        (source_key,),
    ).fetchone()
    if existing_document is not None and existing_document["origin"] != origin:
        raise ValueError("Knowledge document source_key belongs to a different origin.")
    db.execute(
        """INSERT INTO knowledge_documents
           (source_type, source_key, title, content, published, origin)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(source_key) DO UPDATE SET
               source_type = excluded.source_type,
               title = excluded.title,
               content = excluded.content,
               published = excluded.published,
               updated_at = CURRENT_TIMESTAMP""",
        (document["source_type"], source_key, title, content, published, origin),
    )
    document_id = db.execute(
        "SELECT id FROM knowledge_documents WHERE source_key = ?",
        (source_key,),
    ).fetchone()["id"]
    chunks = chunk_text(content, title=title)
    existing_chunks = {
        row["chunk_index"]: row
        for row in db.execute(
            """SELECT chunk_index, text FROM knowledge_chunks
               WHERE document_id = ?""",
            (document_id,),
        ).fetchall()
    }
    for chunk_index, chunk in enumerate(chunks):
        existing = existing_chunks.get(chunk_index)
        if existing is None:
            db.execute(
                """INSERT INTO knowledge_chunks
                   (document_id, chunk_index, text, token_count, embedding,
                    content_hash, embedding_model)
                   VALUES (?, ?, ?, ?, NULL, NULL, NULL)""",
                (document_id, chunk_index, chunk, len(tokenize(chunk))),
            )
        elif existing["text"] != chunk:
            db.execute(
                """UPDATE knowledge_chunks
                   SET text = ?, token_count = ?, embedding = NULL,
                       content_hash = NULL, embedding_model = NULL,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE document_id = ? AND chunk_index = ?""",
                (chunk, len(tokenize(chunk)), document_id, chunk_index),
            )
        else:
            db.execute(
                """UPDATE knowledge_chunks SET token_count = ?
                   WHERE document_id = ? AND chunk_index = ?""",
                (len(tokenize(chunk)), document_id, chunk_index),
            )
    if len(chunks) < len(existing_chunks):
        db.execute(
            "DELETE FROM knowledge_chunks WHERE document_id = ? AND chunk_index >= ?",
            (document_id, len(chunks)),
        )
    invalidate_cache()
    return {"documents": 1, "chunks": len(chunks)}


def invalidate_cache():
    global _TOKENIZED_CHUNKS, _VECTOR_CHUNKS, _CACHE_SIGNATURE
    with _CACHE_LOCK:
        _TOKENIZED_CHUNKS = None
        _VECTOR_CHUNKS = None
        _CACHE_SIGNATURE = None


_invalidate_cache = invalidate_cache


def embed_missing_chunks(db, document_id=None, origin=None):
    if not embeddings.embeddings_available():
        return {
            "chunks_embedded": 0,
            "chunks_skipped_unchanged": 0,
            "embeddings_available": False,
        }

    model = embeddings.embedding_model()
    dimension = embeddings.embedding_dimension()
    query = """SELECT c.id, c.text, c.content_hash, c.embedding_model, c.embedding
           FROM knowledge_chunks AS c
           JOIN knowledge_documents AS d ON d.id = c.document_id
           WHERE d.published = TRUE"""
    params = []
    if document_id is not None:
        query += " AND d.id = ?"
        params.append(document_id)
    if origin is not None:
        query += " AND d.origin = ?"
        params.append(origin)
    query += " ORDER BY c.id"
    rows = db.execute(query, params).fetchall()
    pending = []
    skipped = 0
    for row in rows:
        content_hash = sha256(row["text"].encode("utf-8")).hexdigest()
        try:
            stored_dimension = len(json.loads(row["embedding"])) if row["embedding"] else 0
        except (TypeError, ValueError):
            stored_dimension = 0
        if (
            row["embedding"] is not None
            and row["content_hash"] == content_hash
            and row["embedding_model"] == model
            and stored_dimension == dimension
        ):
            skipped += 1
            continue
        pending.append((row["id"], row["text"], content_hash))

    embedded = 0
    try:
        for start in range(0, len(pending), _EMBEDDING_BATCH_SIZE):
            batch = pending[start:start + _EMBEDDING_BATCH_SIZE]
            vectors = embeddings.embed_texts(
                [text for _, text, _ in batch],
                task_type="RETRIEVAL_DOCUMENT",
            )
            if len(vectors) != len(batch):
                raise EmbeddingError("Embedding provider returned an unexpected batch size.")
            for (chunk_id, _text, content_hash), vector in zip(batch, vectors):
                if len(vector) != dimension:
                    raise EmbeddingError(
                        "Embedding provider returned a vector with an unexpected dimension."
                    )
                db.execute(
                    """UPDATE knowledge_chunks SET embedding = ?, content_hash = ?,
                       embedding_model = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (json.dumps(vector), content_hash, model, chunk_id),
                )
            db.commit()
            embedded += len(batch)
            invalidate_cache()
            if start + _EMBEDDING_BATCH_SIZE < len(pending):
                time.sleep(_EMBEDDING_BATCH_DELAY)
    except EmbeddingError:
        db.commit()
        logging.getLogger(__name__).warning(
            "Knowledge chunk embedding stopped after %d chunks; keyword retrieval remains available.",
            embedded,
        )
        return {
            "chunks_embedded": embedded,
            "chunks_skipped_unchanged": skipped,
            "embeddings_available": True,
            "embedding_error": True,
        }
    return {
        "chunks_embedded": embedded,
        "chunks_skipped_unchanged": skipped,
        "embeddings_available": True,
    }


def reindex_all(db, embed=True):
    documents = load_markdown_sections(KNOWLEDGE_BASE_PATH)
    documents.extend(_faq_documents())
    documents.extend(_database_documents(db))
    source_keys = [document["source_key"] for document in documents]
    if source_keys:
        placeholders = ", ".join("?" for _ in source_keys)
        db.execute(
            f"""DELETE FROM knowledge_documents
                WHERE origin = 'system' AND source_key NOT IN ({placeholders})""",
            source_keys,
        )
    else:
        db.execute("DELETE FROM knowledge_documents WHERE origin = 'system'")

    totals = {source_type: {"documents": 0, "chunks": 0} for source_type in SOURCE_TYPES}
    for document in documents:
        existing = db.execute(
            "SELECT published FROM knowledge_documents WHERE source_key = ? AND origin = 'system'",
            (document["source_key"],),
        ).fetchone()
        if existing is not None:
            document["published"] = bool(existing["published"])
        result = index_document(db, document)
        totals[document["source_type"]]["documents"] += result["documents"]
        totals[document["source_type"]]["chunks"] += result["chunks"]
    db.commit()
    invalidate_cache()
    totals["embedding"] = {
        "chunks_embedded": 0,
        "chunks_skipped_unchanged": 0,
        "embeddings_available": embeddings.embeddings_available(),
    }
    if embed:
        try:
            totals["embedding"] = embed_missing_chunks(db, origin="system")
        except EmbeddingError:
            logging.getLogger(__name__).warning(
                "Knowledge base embedding failed; keyword retrieval remains available.",
                exc_info=True,
            )
    return totals


def _published_chunks(db):
    rows = db.execute(
        """SELECT c.text AS chunk_text, c.token_count, c.embedding, c.content_hash,
                  c.embedding_model, d.title, d.source_type, d.source_key
           FROM knowledge_chunks AS c
           JOIN knowledge_documents AS d ON d.id = c.document_id
           WHERE d.published = TRUE
           ORDER BY d.id, c.chunk_index"""
    ).fetchall()
    chunks = []
    current_model = embeddings.embedding_model()
    try:
        current_dimension = embeddings.embedding_dimension()
    except EmbeddingError:
        current_dimension = None
    for row in rows:
        chunk = {
            "chunk_text": row["chunk_text"],
            "title": row["title"],
            "source_type": row["source_type"],
            "source_key": row["source_key"],
            "tokens": tokenize(row["chunk_text"]),
            "length": int(row["token_count"]),
        }
        if row["embedding"] and row["embedding_model"] == current_model:
            content_hash = sha256(row["chunk_text"].encode("utf-8")).hexdigest()
            if row["content_hash"] == content_hash:
                try:
                    vector = json.loads(row["embedding"])
                    if len(vector) == current_dimension:
                        chunk["vector"] = vector
                except (TypeError, ValueError):
                    pass
        chunks.append(chunk)
    return chunks


def retrieve(db, question, k=4):
    if k < 1:
        return []
    query_tokens = tokenize(question)
    if not query_tokens:
        return []

    chunks, _vectors = _cached_chunks(db)

    if not chunks:
        return []
    document_frequency = {}
    for term in set(query_tokens):
        document_frequency[term] = sum(term in chunk["token_set"] for chunk in chunks)
    average_length = sum(chunk["length"] for chunk in chunks) / len(chunks) or 1.0
    scores = []
    for chunk in chunks:
        term_frequencies = {}
        for term in chunk["tokens"]:
            term_frequencies[term] = term_frequencies.get(term, 0) + 1
        score = 0.0
        for term in set(query_tokens):
            frequency = term_frequencies.get(term, 0)
            if not frequency:
                continue
            df = document_frequency[term]
            inverse_document_frequency = math.log(
                1 + (len(chunks) - df + 0.5) / (df + 0.5)
            )
            denominator = frequency + 1.5 * (
                1 - 0.75 + 0.75 * chunk["length"] / average_length
            )
            score += inverse_document_frequency * frequency * 2.5 / denominator
        if score >= BM25_MIN_SCORE:
            scores.append(
                {
                    "chunk_text": chunk["chunk_text"],
                    "title": chunk["title"],
                    "source_type": chunk["source_type"],
                    "source_key": chunk["source_key"],
                    "score": score,
                }
            )
    scores.sort(key=lambda result: result["score"], reverse=True)
    return scores[:k]


def cosine_similarity(a, b):
    if len(a) != len(b):
        raise ValueError("Embedding vectors must have the same dimension.")
    return sum(float(left) * float(right) for left, right in zip(a, b))


def _cached_chunks(db):
    global _TOKENIZED_CHUNKS, _VECTOR_CHUNKS, _CACHE_SIGNATURE
    try:
        dimension = embeddings.embedding_dimension()
    except EmbeddingError:
        dimension = None
    signature = (embeddings.embedding_model(), dimension)
    with _CACHE_LOCK:
        if _TOKENIZED_CHUNKS is None or _CACHE_SIGNATURE != signature:
            chunks = _published_chunks(db)
            for chunk in chunks:
                chunk["token_set"] = set(chunk["tokens"])
            _TOKENIZED_CHUNKS = chunks
            _VECTOR_CHUNKS = [
                chunk for chunk in chunks if "vector" in chunk
            ]
            _CACHE_SIGNATURE = signature
        return _TOKENIZED_CHUNKS, _VECTOR_CHUNKS


def _cached_query_embedding(question):
    safe_question = redact_sensitive_content(question)
    cache_key = (
        embeddings.embedding_model(),
        embeddings.embedding_dimension(),
        safe_question,
    )
    with _CACHE_LOCK:
        if cache_key in _QUERY_EMBEDDINGS:
            _QUERY_EMBEDDINGS.move_to_end(cache_key)
            return _QUERY_EMBEDDINGS[cache_key]
    vector = embeddings.embed_text(safe_question, task_type="RETRIEVAL_QUERY")
    with _CACHE_LOCK:
        _QUERY_EMBEDDINGS[cache_key] = vector
        _QUERY_EMBEDDINGS.move_to_end(cache_key)
        while len(_QUERY_EMBEDDINGS) > 200:
            _QUERY_EMBEDDINGS.popitem(last=False)
    return vector


def retrieve_semantic(db, question, k=4):
    if k < 1:
        return []
    query_vector = _cached_query_embedding(question)
    _chunks, vector_chunks = _cached_chunks(db)
    results = []
    for chunk in vector_chunks:
        score = cosine_similarity(query_vector, chunk["vector"])
        results.append(
            {
                "chunk_text": chunk["chunk_text"],
                "title": chunk["title"],
                "source_type": chunk["source_type"],
                "source_key": chunk["source_key"],
                "semantic_score": score,
            }
        )
    results.sort(key=lambda result: result["semantic_score"], reverse=True)
    return results[:k]


def retrieve_hybrid(db, question, k=4):
    if k < 1:
        return {"mode": "hybrid", "results": []}
    if not is_hackathon_question(question):
        return {"mode": "hybrid", "results": []}
    bm25_results = retrieve(db, question, k=max(k, 20))
    try:
        semantic_results = retrieve_semantic(db, question, k=max(k, 20))
    except EmbeddingError:
        return {
            "mode": "bm25_fallback",
            "results": [
                {
                    "chunk_text": result["chunk_text"],
                    "title": result["title"],
                    "source_type": result["source_type"],
                    "source_key": result["source_key"],
                    "bm25_score": result["score"],
                    "semantic_score": None,
                    "fused_score": 1 / (60 + rank),
                }
                for rank, result in enumerate(bm25_results, start=1)
            ][:k],
        }

    try:
        semantic_min_score = float(os.environ.get("SEMANTIC_MIN_SCORE", "0.55"))
    except ValueError as exc:
        raise EmbeddingError("SEMANTIC_MIN_SCORE must be a number.") from exc
    best_semantic_score = (
        semantic_results[0]["semantic_score"] if semantic_results else 0.0
    )
    if best_semantic_score < semantic_min_score and not bm25_results:
        return {"mode": "hybrid", "results": []}

    bm25_by_key = {
        result["source_key"] + "\0" + result["chunk_text"]: result
        for result in bm25_results
    }
    semantic_by_key = {
        result["source_key"] + "\0" + result["chunk_text"]: result
        for result in semantic_results
    }
    fused_scores = {}
    for rank, result in enumerate(bm25_results, start=1):
        key = result["source_key"] + "\0" + result["chunk_text"]
        fused_scores[key] = fused_scores.get(key, 0.0) + 1 / (60 + rank)
    for rank, result in enumerate(semantic_results, start=1):
        key = result["source_key"] + "\0" + result["chunk_text"]
        fused_scores[key] = fused_scores.get(key, 0.0) + 1 / (60 + rank)

    results = []
    for key, fused_score in fused_scores.items():
        bm25_result = bm25_by_key.get(key)
        semantic_result = semantic_by_key.get(key)
        source = bm25_result or semantic_result
        results.append(
            {
                "chunk_text": source["chunk_text"],
                "title": source["title"],
                "source_type": source["source_type"],
                "source_key": source["source_key"],
                "bm25_score": bm25_result["score"] if bm25_result else 0.0,
                "semantic_score": (
                    semantic_result["semantic_score"] if semantic_result else None
                ),
                "fused_score": fused_score,
            }
        )
    results.sort(key=lambda result: result["fused_score"], reverse=True)
    return {"mode": "hybrid", "results": results[:k]}
