import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from embeddings import EmbeddingError
from rag import retrieve_hybrid


class KnowledgeAdminTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.environment = patch.dict(
            os.environ,
            {
                "SECRET_KEY": "knowledge-admin-test-secret",
                "DATABASE_URL": "",
                "DATABASE_PATH": str(Path(self.temp_dir.name) / "knowledge-admin.db"),
                "ADMIN_EMAIL": "knowledge-admin@example.invalid",
                "ADMIN_PASSWORD": "knowledge-admin-test-password",
                "RAG_ENABLED": "true",
                "GEMINI_API_KEY": "",
                "EMBEDDING_DIM": "2",
                "SEMANTIC_MIN_SCORE": "0.1",
                "GROQ_API_KEY": "knowledge-test-groq",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        csrf = self.client.get("/api/csrf").get_json()["csrf_token"]
        login = self.client.post(
            "/api/login",
            json={
                "email": "knowledge-admin@example.invalid",
                "password": "knowledge-admin-test-password",
            },
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(login.status_code, 200)
        self.csrf = login.get_json()["csrf_token"]
        self.headers = {"X-CSRF-Token": self.csrf}

    def _create_document(
        self,
        title="Custom document title",
        content="This is a custom answer with enough detail for a useful response.",
        published=True,
    ):
        return self.client.post(
            "/api/admin/knowledge/documents",
            json={"title": title, "content": content, "published": published},
            headers=self.headers,
        )

    def _unknown_chat(self, question):
        return self.client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": question}]},
            headers=self.headers,
        )

    def test_admin_document_crud_and_document_chunks(self):
        created = self._create_document()
        self.assertEqual(created.status_code, 201)
        document_id = created.get_json()["document"]["id"]
        listed = self.client.get("/api/admin/knowledge/documents?origin=admin")
        self.assertEqual(listed.status_code, 200)
        item = next(
            document
            for document in listed.get_json()["documents"]
            if document["id"] == document_id
        )
        self.assertEqual(item["origin"], "admin")
        self.assertGreaterEqual(item["chunk_count"], 1)

        details = self.client.get(f"/api/admin/knowledge/documents/{document_id}")
        self.assertEqual(details.status_code, 200)
        self.assertEqual(details.get_json()["document"]["content"], "This is a custom answer with enough detail for a useful response.")
        self.assertTrue(details.get_json()["document"]["chunks"])

        updated = self.client.put(
            f"/api/admin/knowledge/documents/{document_id}",
            json={
                "title": "Updated custom answer",
                "content": "The updated answer contains fresh official information for organizers.",
                "published": False,
            },
            headers=self.headers,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertFalse(updated.get_json()["embedding_pending"])
        self.assertEqual(
            self.client.get(f"/api/admin/knowledge/documents/{document_id}")
            .get_json()["document"]["title"],
            "Updated custom answer",
        )

        published = self.client.patch(
            f"/api/admin/knowledge/documents/{document_id}/publish",
            json={"published": True},
            headers=self.headers,
        )
        self.assertEqual(published.status_code, 200)
        self.assertTrue(published.get_json()["published"])

        deleted = self.client.delete(
            f"/api/admin/knowledge/documents/{document_id}",
            headers=self.headers,
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/admin/knowledge/documents/{document_id}").status_code,
            404,
        )

    def test_title_content_validation_and_admin_document_limit(self):
        invalid = self._create_document(title="ab", content="short")
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("title", invalid.get_json()["field_errors"])
        self.assertIn("content", invalid.get_json()["field_errors"])

        oversized = self._create_document(
            title="T" * 121,
            content="C" * 4001,
        )
        self.assertEqual(oversized.status_code, 400)
        self.assertIn("title", oversized.get_json()["field_errors"])
        self.assertIn("content", oversized.get_json()["field_errors"])

        with self.app.app_context():
            db = self.app.get_db()
            for index in range(200):
                temporary_key = f"admin:limit-seed:{index}"
                db.execute(
                    """INSERT INTO knowledge_documents
                       (source_type, source_key, title, content, origin)
                       VALUES ('custom', ?, ?, ?, 'admin')""",
                    (temporary_key, f"Seed {index}", "Seed content for max-count testing."),
                )
                document_id = db.execute(
                    "SELECT id FROM knowledge_documents WHERE source_key = ?",
                    (temporary_key,),
                ).fetchone()["id"]
                db.execute(
                    "UPDATE knowledge_documents SET source_key = ? WHERE id = ?",
                    (f"admin:{document_id}", document_id),
                )
            db.commit()
        limited = self._create_document()
        self.assertEqual(limited.status_code, 409)

    def test_document_fields_strip_control_characters(self):
        created = self._create_document(
            title="Custom\x01 document",
            content="This answer\x02 contains control characters that should be removed.",
        )
        self.assertEqual(created.status_code, 201)
        document_id = created.get_json()["document"]["id"]
        details = self.client.get(f"/api/admin/knowledge/documents/{document_id}")
        self.assertEqual(details.get_json()["document"]["title"], "Custom document")
        self.assertNotIn(
            "\x02",
            details.get_json()["document"]["content"],
        )

    def test_system_documents_cannot_be_edited_or_deleted_but_can_be_hidden(self):
        with self.app.app_context():
            document_id = self.app.get_db().execute(
                "SELECT id FROM knowledge_documents WHERE source_key = 'kb:2'"
            ).fetchone()["id"]
        update = self.client.put(
            f"/api/admin/knowledge/documents/{document_id}",
            json={
                "title": "System event",
                "content": "This update should not be allowed for a system document.",
            },
            headers=self.headers,
        )
        delete = self.client.delete(
            f"/api/admin/knowledge/documents/{document_id}",
            headers=self.headers,
        )
        self.assertEqual(update.status_code, 403)
        self.assertEqual(delete.status_code, 403)

        hidden = self.client.patch(
            f"/api/admin/knowledge/documents/{document_id}/publish",
            json={"published": False},
            headers=self.headers,
        )
        self.assertEqual(hidden.status_code, 200)
        self.client.post("/api/admin/knowledge/reindex", headers=self.headers)
        with self.app.app_context():
            self.assertFalse(
                self.app.get_db().execute(
                    "SELECT published FROM knowledge_documents WHERE id = ?",
                    (document_id,),
                ).fetchone()["published"]
            )

    def test_admin_document_survives_reindex_with_its_embedding_unchanged(self):
        created = self._create_document()
        document_id = created.get_json()["document"]["id"]
        with self.app.app_context():
            db = self.app.get_db()
            chunk = db.execute(
                "SELECT id, text FROM knowledge_chunks WHERE document_id = ?",
                (document_id,),
            ).fetchone()
            embedding = "[0.25, 0.75]"
            content_hash = hashlib.sha256(chunk["text"].encode("utf-8")).hexdigest()
            db.execute(
                """UPDATE knowledge_chunks SET embedding = ?, content_hash = ?,
                   embedding_model = 'test-model' WHERE id = ?""",
                (embedding, content_hash, chunk["id"]),
            )
            db.commit()
            self.client.post("/api/admin/knowledge/reindex", headers=self.headers)
            saved = db.execute(
                """SELECT d.origin, d.content, c.embedding, c.content_hash,
                          c.embedding_model
                   FROM knowledge_documents d JOIN knowledge_chunks c
                     ON c.document_id = d.id WHERE d.id = ?""",
                (document_id,),
            ).fetchone()
        self.assertEqual(saved["origin"], "admin")
        self.assertEqual(saved["embedding"], embedding)
        self.assertEqual(saved["content_hash"], content_hash)
        self.assertEqual(saved["embedding_model"], "test-model")

    def test_unpublished_admin_document_is_not_retrievable(self):
        self._create_document(
            title="Hidden mango telescope",
            content="Never published mango telescope information stays hidden.",
            published=False,
        )
        with self.app.app_context():
            results = retrieve_hybrid(
                self.app.get_db(),
                "mango telescope",
                k=4,
            )["results"]
        self.assertFalse(any("mango" in result["chunk_text"].lower() for result in results))

    def test_created_admin_document_is_retrievable_with_fake_embeddings(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
            with patch(
                "rag.embeddings.embed_texts",
                side_effect=lambda texts, task_type: [[1.0, 0.0] for _ in texts],
            ):
                created = self._create_document(
                    title="Quasar telescope support",
                    content="Quasar telescope applications are accepted through the official organizer form.",
                )
                self.assertEqual(created.status_code, 201)
                self.assertFalse(created.get_json()["embedding_pending"])
                with self.app.app_context():
                    result = retrieve_hybrid(
                        self.app.get_db(),
                        "quasar telescope applications",
                        k=4,
                    )
        self.assertEqual(result["mode"], "hybrid")
        self.assertTrue(result["results"])
        self.assertTrue(
            any(item["source_key"] == f"admin:{created.get_json()['document']['id']}" for item in result["results"])
        )

    def test_embedding_failure_does_not_fail_save_and_sets_pending_flag(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
            with patch("app.embed_missing_chunks", side_effect=EmbeddingError("provider unavailable")):
                created = self._create_document()
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.get_json()["embedding_pending"])

    def test_new_endpoints_enforce_admin_and_csrf(self):
        unauthenticated = self.app.test_client()
        get_paths = (
            "/api/admin/knowledge/documents",
            "/api/admin/knowledge/documents/1",
            "/api/admin/knowledge/gaps",
        )
        for path in get_paths:
            with self.subTest(path=path):
                self.assertIn(unauthenticated.get(path).status_code, {401, 403})

        participant = self.app.test_client()
        participant_csrf = participant.get("/api/csrf").get_json()["csrf_token"]
        signup = participant.post(
            "/api/signup",
            json={
                "full_name": "Knowledge Participant",
                "email": "knowledge-participant@example.invalid",
                "password": "knowledge-participant-password",
            },
            headers={"X-CSRF-Token": participant_csrf},
        )
        self.assertEqual(signup.status_code, 201)
        participant_headers = {"X-CSRF-Token": signup.get_json()["csrf_token"]}
        for path in get_paths:
            with self.subTest(path=path):
                self.assertEqual(participant.get(path).status_code, 403)

        document_id = self._create_document().get_json()["document"]["id"]
        with self.app.app_context():
            db = self.app.get_db()
            db.execute(
                """INSERT INTO knowledge_gaps (question, normalized_question)
                   VALUES ('Test gap question', 'test gap question')"""
            )
            gap_id = db.execute(
                "SELECT id FROM knowledge_gaps WHERE normalized_question = 'test gap question'"
            ).fetchone()["id"]
            db.commit()
        mutation_requests = (
            ("POST", "/api/admin/knowledge/documents", {"title": "Valid title", "content": "This is enough text to validate a new answer."}),
            ("PUT", f"/api/admin/knowledge/documents/{document_id}", {"title": "Updated title", "content": "This is enough text to validate an edited answer."}),
            ("PATCH", f"/api/admin/knowledge/documents/{document_id}/publish", {"published": False}),
            ("DELETE", f"/api/admin/knowledge/documents/{document_id}", None),
            ("PATCH", f"/api/admin/knowledge/gaps/{gap_id}", {"status": "resolved"}),
            ("DELETE", f"/api/admin/knowledge/gaps/{gap_id}", None),
            ("POST", "/api/admin/knowledge/reindex", None),
        )
        for method, path, body in mutation_requests:
            with self.subTest(method=method, path=path):
                response = self.client.open(path, method=method, json=body)
                self.assertEqual(response.status_code, 403)
                response = participant.open(
                    path,
                    method=method,
                    json=body,
                    headers=participant_headers,
                )
                self.assertEqual(response.status_code, 403)

    def test_gap_logger_redacts_deduplicates_and_ignores_faq_and_out_of_scope(self):
        unknown = "What organizer contact is available? person@example.invalid"
        with (
            patch("app.retrieve_hybrid", return_value={"mode": "hybrid", "results": []}),
            patch("app.is_hackathon_question", return_value=True),
            patch("app.get_hackathon_faq_reply", return_value=None),
            patch("app.get_food_facility_reply", return_value=None),
        ):
            self.assertEqual(self._unknown_chat(unknown).status_code, 200)
            self.assertEqual(self._unknown_chat(unknown).status_code, 200)
        with self.app.app_context():
            gaps = self.app.get_db().execute(
                "SELECT question, normalized_question, times_asked FROM knowledge_gaps"
            ).fetchall()
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["times_asked"], 2)
        self.assertNotIn("person@example.invalid", gaps[0]["question"])

        with self.app.app_context():
            initial_gap_count = self.app.get_db().execute(
                "SELECT COUNT(*) AS count FROM knowledge_gaps"
            ).fetchone()["count"]
        with patch("app.get_hackathon_faq_reply", return_value="Known answer."):
            self.assertEqual(
                self._unknown_chat("When is the event?").get_json()["reply"],
                "Known answer.",
            )
        with self.app.app_context():
            self.assertEqual(
                self.app.get_db().execute(
                    "SELECT COUNT(*) AS count FROM knowledge_gaps"
                ).fetchone()["count"],
                initial_gap_count,
            )
        with patch("app.retrieve_hybrid", side_effect=AssertionError("out-of-scope retrieval ran")):
            response = self._unknown_chat("write me a python function")
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            self.assertEqual(
                self.app.get_db().execute(
                    "SELECT COUNT(*) AS count FROM knowledge_gaps"
                ).fetchone()["count"],
                initial_gap_count,
            )

    def test_gap_database_error_does_not_break_chat_and_gap_endpoints_work(self):
        with self.app.app_context():
            db = self.app.get_db()
            db.execute(
                """INSERT INTO knowledge_gaps
                   (question, normalized_question, times_asked, status, first_seen, last_seen)
                   VALUES ('Older resolved gap', 'older resolved gap', 1, 'resolved',
                           '2000-01-01 00:00:00', '2000-01-01 00:00:00')"""
            )
            db.execute(
                """CREATE TRIGGER fail_knowledge_gap_insert
                   BEFORE INSERT ON knowledge_gaps
                   BEGIN SELECT RAISE(FAIL, 'test failure'); END"""
            )
            db.commit()
        with (
            patch("app.retrieve_hybrid", return_value={"mode": "hybrid", "results": []}),
            patch("app.is_hackathon_question", return_value=True),
            patch("app.get_hackathon_faq_reply", return_value=None),
            patch("app.get_food_facility_reply", return_value=None),
        ):
            self.assertEqual(self._unknown_chat("What is the organizer contact?").status_code, 200)
        with self.app.app_context():
            db = self.app.get_db()
            db.execute("DROP TRIGGER fail_knowledge_gap_insert")
            for index in range(500):
                db.execute(
                    """INSERT INTO knowledge_gaps
                       (question, normalized_question, times_asked, status, first_seen, last_seen)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        f"Gap {index}",
                        f"gap {index}",
                        index + 1,
                        "resolved" if index < 3 else "open",
                        f"2000-01-{index + 1:02d} 00:00:00",
                        f"2000-01-{index + 1:02d} 00:00:00",
                    ),
                )
            db.commit()

        with (
            patch("app.retrieve_hybrid", return_value={"mode": "hybrid", "results": []}),
            patch("app.is_hackathon_question", return_value=True),
            patch("app.get_hackathon_faq_reply", return_value=None),
            patch("app.get_food_facility_reply", return_value=None),
        ):
            self.assertEqual(self._unknown_chat("What is the final organizer contact?").status_code, 200)
        gaps_response = self.client.get("/api/admin/knowledge/gaps")
        gaps = gaps_response.get_json()["gaps"]
        self.assertEqual(gaps_response.status_code, 200)
        self.assertEqual(len(gaps), 500)
        self.assertEqual(gaps[0]["status"], "open")
        self.assertNotIn("Gap 0", [gap["question"] for gap in gaps])

        gap_id = next(gap["id"] for gap in gaps if gap["status"] == "open")
        resolved = self.client.patch(
            f"/api/admin/knowledge/gaps/{gap_id}",
            json={"status": "resolved"},
            headers=self.headers,
        )
        self.assertEqual(resolved.status_code, 200)
        removed = self.client.delete(
            f"/api/admin/knowledge/gaps/{gap_id}",
            headers=self.headers,
        )
        self.assertEqual(removed.status_code, 200)


if __name__ == "__main__":
    unittest.main()
