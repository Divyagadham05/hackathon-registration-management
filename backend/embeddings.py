import json
import math
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
REQUEST_TIMEOUT_SECONDS = 10
MAX_RETRIES = 3


class EmbeddingError(Exception):
    pass


def embeddings_available():
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def embedding_model():
    return (
        os.environ.get("EMBEDDING_MODEL", "gemini-embedding-001").strip()
        or "gemini-embedding-001"
    )


def embedding_dimension():
    try:
        dimension = int(os.environ.get("EMBEDDING_DIM", "768"))
    except ValueError:
        raise EmbeddingError("EMBEDDING_DIM must be a positive integer.") from None
    if dimension < 1:
        raise EmbeddingError("EMBEDDING_DIM must be a positive integer.")
    return dimension


def normalize_vector(values):
    try:
        vector = [float(value) for value in values]
    except (TypeError, ValueError):
        raise EmbeddingError("Gemini returned an invalid embedding vector.") from None
    if not vector or any(not math.isfinite(value) for value in vector):
        raise EmbeddingError("Gemini returned an invalid embedding vector.")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _request_json(url, payload, api_key):
    body = json.dumps(payload).encode("utf-8")
    for attempt in range(MAX_RETRIES + 1):
        try:
            request = Request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                },
                method="POST",
            )
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                try:
                    return json.loads(response.read().decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    raise EmbeddingError("Gemini returned an invalid JSON response.") from None
        except HTTPError as exc:
            if exc.code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                time.sleep(0.25 * (2 ** attempt))
                continue
            raise EmbeddingError(
                f"Gemini embedding request failed with HTTP {exc.code}."
            ) from None
        except EmbeddingError:
            raise
        except (URLError, TimeoutError, OSError, ValueError):
            if attempt < MAX_RETRIES:
                time.sleep(0.25 * (2 ** attempt))
                continue
            raise EmbeddingError("Gemini embedding request failed after retries.") from None
    raise EmbeddingError("Gemini embedding request failed after retries.")


def _request_content(text, task_type):
    if not isinstance(text, str):
        raise EmbeddingError("Embedding input must be text.")
    return {
        "model": f"models/{embedding_model()}",
        "content": {"parts": [{"text": text}]},
        "taskType": task_type,
        "outputDimensionality": embedding_dimension(),
    }


def embed_texts(texts, task_type):
    if not embeddings_available():
        raise EmbeddingError("GEMINI_API_KEY is not configured.")
    if task_type not in {"RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"}:
        raise EmbeddingError("Unsupported embedding task type.")
    if not texts:
        return []

    api_key = os.environ["GEMINI_API_KEY"].strip()
    model_path = quote(embedding_model(), safe="-_.")
    if len(texts) == 1:
        url = f"{API_BASE_URL}/{model_path}:embedContent"
        response = _request_json(
            url,
            _request_content(texts[0], task_type),
            api_key,
        )
        try:
            values = response["embedding"]["values"]
        except (KeyError, TypeError):
            raise EmbeddingError("Gemini response did not contain an embedding.") from None
        vectors = [normalize_vector(values)]
    else:
        url = f"{API_BASE_URL}/{model_path}:batchEmbedContents"
        response = _request_json(
            url,
            {"requests": [_request_content(text, task_type) for text in texts]},
            api_key,
        )
        try:
            embeddings = response["embeddings"]
            if len(embeddings) != len(texts):
                raise EmbeddingError("Gemini returned an unexpected number of embeddings.")
            vectors = [normalize_vector(item["values"]) for item in embeddings]
        except (KeyError, TypeError):
            raise EmbeddingError("Gemini response did not contain valid embeddings.") from None

    expected_dimension = embedding_dimension()
    if any(len(vector) != expected_dimension for vector in vectors):
        raise EmbeddingError("Gemini returned an embedding with an unexpected dimension.")
    return vectors


def embed_text(text, task_type):
    return embed_texts([text], task_type)[0]
