import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import embeddings
import rag
from app import create_app


class EmbeddingClientTests(unittest.TestCase):
    def test_normalization_and_cosine_similarity(self):
        vector = embeddings.normalize_vector([3, 4])
        self.assertAlmostEqual(sum(value * value for value in vector), 1.0)
        self.assertAlmostEqual(rag.cosine_similarity(vector, [0.6, 0.8]), 1.0)
        self.assertEqual(embeddings.normalize_vector([0, 0]), [0, 0])

    def test_request_uses_header_and_embedding_configuration(self):
        response_body = json.dumps({"embedding": {"values": [3, 4]}}).encode()

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return response_body

        with patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "test-key-never-log",
                "EMBEDDING_MODEL": "gemini-embedding-001",
                "EMBEDDING_DIM": "2",
            },
        ), patch("embeddings.urlopen", return_value=FakeResponse()) as urlopen:
            result = embeddings.embed_texts(["A chunk"], "RETRIEVAL_DOCUMENT")

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-embedding-001:embedContent"
        ))
        self.assertEqual(request.get_header("X-goog-api-key"), "test-key-never-log")
        payload = json.loads(request.data)
        self.assertEqual(payload["taskType"], "RETRIEVAL_DOCUMENT")
        self.assertEqual(payload["outputDimensionality"], 2)
        self.assertAlmostEqual(result[0][0], 0.6)
        self.assertAlmostEqual(result[0][1], 0.8)

    def test_api_key_is_not_in_embedding_errors_or_logs(self):
        secret = "sensitive-gemini-api-key"
        failure = HTTPError(
            "https://generativelanguage.googleapis.com/redacted",
            400,
            "bad request",
            {},
            io.BytesIO(b""),
        )
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": secret}),
            patch("embeddings.urlopen", side_effect=failure),
            patch("embeddings.time.sleep"),
            self.assertNoLogs("embeddings", level="DEBUG"),
        ):
            with self.assertRaises(embeddings.EmbeddingError) as raised:
                embeddings.embed_texts(["text"], "RETRIEVAL_QUERY")
        self.assertNotIn(secret, str(raised.exception))

    def test_retryable_http_status_is_retried(self):
        response_body = json.dumps({"embedding": {"values": [1, 0]}}).encode()

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return response_body

        unavailable = HTTPError(
            "https://generativelanguage.googleapis.com/redacted",
            503,
            "unavailable",
            {},
            io.BytesIO(b""),
        )
        with (
            patch.dict(
                os.environ,
                {"GEMINI_API_KEY": "test-key", "EMBEDDING_DIM": "2"},
            ),
            patch("embeddings.urlopen", side_effect=[unavailable, FakeResponse()]) as urlopen,
            patch("embeddings.time.sleep"),
        ):
            result = embeddings.embed_texts(["text"], "RETRIEVAL_QUERY")
        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(result, [[1.0, 0.0]])

    def test_missing_api_key_marks_embeddings_unavailable(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            self.assertFalse(embeddings.embeddings_available())


class RagEmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "embeddings-test.db"
        self.environment = patch.dict(
            os.environ,
            {
                "SECRET_KEY": "embedding-test-secret",
                "DATABASE_URL": "",
                "DATABASE_PATH": str(self.database_path),
                "ADMIN_EMAIL": "embedding-admin@example.invalid",
                "ADMIN_PASSWORD": "embedding-test-admin-password",
                "GEMINI_API_KEY": "",
                "EMBEDDING_MODEL": "fake-model",
                "EMBEDDING_DIM": "2",
                "SEMANTIC_MIN_SCORE": "0.55",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    @staticmethod
    def _fake_vectors(texts, task_type):
        if task_type == "RETRIEVAL_QUERY":
            return [[1.0, 0.0] for _ in texts]
        return [
            [1.0, 0.0] if "first target" in text else [0.0, 1.0]
            for text in texts
        ]

    def _index_one_document(self, content="The first target passage."):
        with (
            patch.object(rag, "load_markdown_sections", return_value=[
                {
                    "source_type": "custom",
                    "source_key": "test:one",
                    "title": "Target",
                    "content": content,
                    "published": True,
                }
            ]),
            patch.object(rag, "_faq_documents", return_value=[]),
            patch.object(rag, "_database_documents", return_value=[]),
        ):
            return rag.reindex_all(self.app.get_db())

    def test_unchanged_chunks_are_skipped_and_changed_chunks_reembedded(self):
        with self.app.app_context():
            db = self.app.get_db()
            with (
                patch.object(rag.embeddings, "embeddings_available", return_value=True),
                patch.object(rag.embeddings, "embedding_model", return_value="fake-model"),
                patch.object(rag.embeddings, "embedding_dimension", return_value=2),
                patch.object(rag.embeddings, "embed_texts", side_effect=self._fake_vectors) as embed,
                patch.object(rag, "_EMBEDDING_BATCH_DELAY", 0),
            ):
                first = self._index_one_document()
                first_call_count = embed.call_count
                self.assertEqual(first["embedding"]["chunks_embedded"], 1)

                second = self._index_one_document()
                self.assertEqual(embed.call_count, first_call_count)
                self.assertEqual(second["embedding"]["chunks_embedded"], 0)
                self.assertEqual(second["embedding"]["chunks_skipped_unchanged"], 1)

                third = self._index_one_document("The changed target passage.")
                self.assertEqual(embed.call_count, first_call_count + 1)
                self.assertEqual(third["embedding"]["chunks_embedded"], 1)

    def test_embed_missing_chunks_uses_batches_of_at_most_twenty(self):
        with self.app.app_context():
            db = self.app.get_db()
            db.execute("DELETE FROM knowledge_documents")
            cursor = db.execute(
                """INSERT INTO knowledge_documents
                   (source_type, source_key, title, content, published)
                   VALUES ('custom', 'many:chunks', 'Many', 'Many chunks', TRUE)
                   RETURNING id"""
            )
            document_id = cursor.fetchone()["id"]
            for index in range(45):
                db.execute(
                    """INSERT INTO knowledge_chunks
                       (document_id, chunk_index, text, token_count)
                       VALUES (?, ?, ?, 1)""",
                    (document_id, index, f"Chunk {index}."),
                )
            db.commit()
            rag._invalidate_cache()
            with (
                patch.object(rag.embeddings, "embeddings_available", return_value=True),
                patch.object(rag.embeddings, "embedding_model", return_value="fake-model"),
                patch.object(rag.embeddings, "embedding_dimension", return_value=2),
                patch.object(rag.embeddings, "embed_texts", side_effect=self._fake_vectors) as embed,
                patch.object(rag, "_EMBEDDING_BATCH_DELAY", 0),
            ):
                result = rag.embed_missing_chunks(db)
            self.assertEqual(result["chunks_embedded"], 45)
            self.assertEqual(
                [len(call.args[0]) for call in embed.call_args_list],
                [20, 20, 5],
            )

    def test_hybrid_reciprocal_rank_fusion_order(self):
        bm25 = [
            {"source_key": "a", "chunk_text": "A", "title": "A", "source_type": "custom", "score": 2.0},
            {"source_key": "b", "chunk_text": "B", "title": "B", "source_type": "custom", "score": 1.0},
        ]
        semantic = [
            {"source_key": "b", "chunk_text": "B", "title": "B", "source_type": "custom", "semantic_score": 0.95},
            {"source_key": "c", "chunk_text": "C", "title": "C", "source_type": "custom", "semantic_score": 0.9},
        ]
        with (
            patch.object(rag, "retrieve", return_value=bm25),
            patch.object(rag, "retrieve_semantic", return_value=semantic),
        ):
            result = rag.retrieve_hybrid(None, "query", k=3)
        self.assertEqual(result["mode"], "hybrid")
        self.assertEqual([item["source_key"] for item in result["results"]], ["b", "a", "c"])
        self.assertGreater(result["results"][0]["fused_score"], result["results"][1]["fused_score"])

    def test_embedding_error_falls_back_to_bm25(self):
        bm25 = [
            {"source_key": "kb:1", "chunk_text": "Matched", "title": "Title", "source_type": "custom", "score": 1.4}
        ]
        with (
            patch.object(rag, "retrieve", return_value=bm25),
            patch.object(rag, "retrieve_semantic", side_effect=embeddings.EmbeddingError("provider unavailable")),
        ):
            result = rag.retrieve_hybrid(None, "question")
        self.assertEqual(result["mode"], "bm25_fallback")
        self.assertEqual(result["results"][0]["bm25_score"], 1.4)

    def test_semantic_question_is_redacted_before_embedding(self):
        with self.app.app_context():
            db = self.app.get_db()
            with (
                patch.object(rag.embeddings, "embedding_model", return_value="fake-model"),
                patch.object(rag.embeddings, "embedding_dimension", return_value=2),
                patch.object(rag.embeddings, "embed_text", return_value=[1.0, 0.0]) as embed,
            ):
                rag._invalidate_cache()
                rag.retrieve_semantic(db, "contact person@example.invalid")
            embed.assert_called_once_with("contact [REDACTED]", task_type="RETRIEVAL_QUERY")

    def test_relevance_gate_rejects_off_topic_results(self):
        semantic = [
            {"source_key": "kb:1", "chunk_text": "weak", "title": "Weak", "source_type": "custom", "semantic_score": 0.2}
        ]
        with (
            patch.object(rag, "retrieve", return_value=[]),
            patch.object(rag, "retrieve_semantic", return_value=semantic),
            patch.dict(os.environ, {"SEMANTIC_MIN_SCORE": "0.55"}),
        ):
            result = rag.retrieve_hybrid(None, "quantum banana recipe")
        self.assertEqual(result, {"mode": "hybrid", "results": []})

    def test_admin_knowledge_endpoints_require_admin_and_csrf(self):
        csrf = self.client.get("/api/csrf").get_json()["csrf_token"]
        login = self.client.post(
            "/api/login",
            json={
                "email": "embedding-admin@example.invalid",
                "password": "embedding-test-admin-password",
            },
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(login.status_code, 200)
        admin_csrf = login.get_json()["csrf_token"]

        self.assertEqual(
            self.client.post("/api/admin/knowledge/reindex").status_code,
            403,
        )
        reindex = self.client.post(
            "/api/admin/knowledge/reindex",
            headers={"X-CSRF-Token": admin_csrf},
        )
        self.assertEqual(reindex.status_code, 200)
        self.assertIn("chunks_embedded", reindex.get_json())
        self.assertFalse(reindex.get_json()["embeddings_available"])

        status = self.client.get("/api/admin/knowledge/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.get_json()["embedded_chunk_count"], 0)
        self.assertNotIn("api_key", status.get_json())

        participant = self.app.test_client()
        participant_csrf = participant.get("/api/csrf").get_json()["csrf_token"]
        signup = participant.post(
            "/api/signup",
            json={
                "full_name": "Embedding Participant",
                "email": "embedding-participant@example.invalid",
                "password": "embedding-participant-password",
            },
            headers={"X-CSRF-Token": participant_csrf},
        )
        self.assertEqual(signup.status_code, 201)
        self.assertEqual(
            participant.get("/api/admin/knowledge/status").status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
