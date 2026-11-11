import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from rag import (
    KNOWLEDGE_BASE_PATH,
    chunk_text,
    load_markdown_sections,
    reindex_all,
    retrieve,
    retrieve_hybrid,
    tokenize,
)


class RagTextProcessingTests(unittest.TestCase):
    def test_chunking_keeps_title_sentence_boundaries_and_word_limit(self):
        sentences = [
            "The first sentence contains exactly seven useful words.",
            "The second sentence also contains exactly seven words.",
            "The third sentence contains a few more useful words.",
            "The fourth sentence makes another complete chunk.",
        ]
        chunks = chunk_text("\n\n".join(sentences), max_words=12, overlap=0, title="Test Title")

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertTrue(chunk.startswith("Test Title\n\n"))
            self.assertLessEqual(len(chunk.split()), 12)
            self.assertTrue(chunk.rstrip().endswith("."))
        self.assertEqual(
            " ".join(chunk.split("\n\n", 1)[1] for chunk in chunks),
            " ".join(sentences),
        )

    def test_short_section_stays_in_one_chunk_and_long_sentence_is_not_split(self):
        short = chunk_text("A short section stays together.", max_words=20, title="Short")
        self.assertEqual(len(short), 1)
        self.assertTrue(short[0].startswith("Short\n\n"))

        long_sentence = " ".join(f"word{index}" for index in range(15)) + "."
        chunks = chunk_text(long_sentence, max_words=5, overlap=0, title="Long")
        self.assertEqual(len(chunks), 1)
        self.assertTrue(chunks[0].endswith(long_sentence))

    def test_tokenizer_matches_registering_and_registration(self):
        self.assertEqual(tokenize("registering"), tokenize("registration"))

    def test_markdown_loader_returns_all_numbered_sections(self):
        sections = load_markdown_sections(KNOWLEDGE_BASE_PATH)

        self.assertEqual(len(sections), 18)
        self.assertEqual(sections[0]["title"], "1. About the Hackathon")
        self.assertEqual(sections[1]["title"], "2. Event Details (When, Where, How Long)")
        self.assertEqual(sections[17]["title"], "18. Information That Has NOT Been Announced")
        self.assertIn("Common questions answered by this section", sections[0]["content"])
        self.assertNotIn("Purpose:", sections[0]["content"])

    def test_missing_markdown_file_logs_warning_and_returns_no_sections(self):
        missing_path = Path(tempfile.gettempdir()) / "missing-rag-knowledge.md"
        with self.assertLogs("rag", level="WARNING"):
            self.assertEqual(load_markdown_sections(missing_path), [])

    def test_hybrid_rejects_out_of_scope_questions_before_retrieval(self):
        with (
            patch("rag.retrieve") as keyword_retrieval,
            patch("rag.retrieve_semantic") as semantic_retrieval,
        ):
            result = retrieve_hybrid(object(), "Tell me a joke")

        self.assertEqual(result, {"mode": "hybrid", "results": []})
        keyword_retrieval.assert_not_called()
        semantic_retrieval.assert_not_called()


class RagDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "rag-test.db"
        self.environment = patch.dict(
            os.environ,
            {
                "SECRET_KEY": "rag-test-secret-key",
                "DATABASE_URL": "",
                "DATABASE_PATH": str(self.database_path),
                "ADMIN_EMAIL": "rag-admin@example.invalid",
                "ADMIN_PASSWORD": "rag-test-admin-password",
                "SMTP_HOST": "",
                "SMTP_FROM_EMAIL": "",
                "RAG_ENABLED": "false",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.assertFalse(self.app.config["RAG_ENABLED"])

    def test_retrieval_returns_expected_markdown_sections_and_rejects_noise(self):
        expected = (
            ("when is the hackathon", "kb:2"),
            ("can I bring my parents", "kb:3"),
            ("what tracks are available", "kb:4"),
            ("is lunch free", "kb:11"),
            ("how many people in a team", "kb:9"),
            ("what are the prizes", "kb:18"),
        )
        with self.app.app_context():
            db = self.app.get_db()
            for question, source_key in expected:
                results = retrieve(db, question, k=4)
                self.assertTrue(results, question)
                self.assertIn(
                    source_key,
                    [result["source_key"] for result in results],
                    question,
                )
                self.assertTrue(all(result["score"] > 0 for result in results))
                self.assertEqual(
                    [result["score"] for result in results],
                    sorted((result["score"] for result in results), reverse=True),
                )
            self.assertEqual(retrieve(db, "quantum banana recipe"), [])

    def test_reindex_is_idempotent_and_unpublished_sources_are_excluded(self):
        with self.app.app_context():
            db = self.app.get_db()
            first_counts = reindex_all(db)
            second_counts = reindex_all(db)
            self.assertEqual(first_counts, second_counts)
            self.assertGreaterEqual(first_counts["custom"]["documents"], 18)
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) AS count FROM knowledge_chunks WHERE embedding IS NOT NULL"
                ).fetchone()["count"],
                0,
            )

            db.execute(
                """INSERT INTO tracks
                   (slug, number, title, tagline, description, color_class,
                    problem_statements, suggested_tech, resources, sort_order,
                    published, registration_domain)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "private-track",
                    "99",
                    "Quasarpublishedonlyxyz",
                    "Private marker tagline",
                    "Private marker description",
                    "track-purple",
                    "[]",
                    "[]",
                    "[]",
                    99,
                    False,
                    "Other",
                ),
            )
            db.execute(
                """INSERT INTO food_facilities
                   (facility_type, items, availability, price_status, published)
                   VALUES (?, ?, ?, ?, FALSE)""",
                (
                    "Unpublished Test Facility",
                    "NeverIndexThisCulinarymarker",
                    "Available",
                    "Free",
                ),
            )
            db.commit()
            reindex_all(db)
            self.assertEqual(retrieve(db, "quasarpublishedonlyxyz"), [])
            self.assertEqual(retrieve(db, "neverindexthisculinarymarker"), [])
            db.execute(
                "UPDATE tracks SET published = TRUE WHERE slug = ?",
                ("private-track",),
            )
            db.execute(
                "UPDATE food_facilities SET published = TRUE WHERE facility_type = ?",
                ("Unpublished Test Facility",),
            )
            db.commit()
            reindex_all(db)
            self.assertEqual(
                retrieve(db, "quasarpublishedonlyxyz")[0]["source_type"],
                "track",
            )
            self.assertEqual(
                retrieve(db, "neverindexthisculinarymarker")[0]["source_type"],
                "food",
            )

    def test_index_never_includes_private_user_or_registration_data(self):
        private_markers = (
            "PrivateParticipantMarker",
            "private-participant@example.invalid",
            "PrivateProjectIdeaMarker",
        )
        with self.app.app_context():
            db = self.app.get_db()
            db.execute(
                "INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
                (private_markers[0], private_markers[1], "PrivatePasswordHashMarker"),
            )
            user_id = db.execute(
                "SELECT id FROM users WHERE email = ?",
                (private_markers[1],),
            ).fetchone()["id"]
            db.execute(
                """INSERT INTO registrations
                   (registration_id, user_id, full_name, email, mobile_number, college_name,
                    degree, department, year_of_study, college_location, participation_type,
                    domain, technical_skills, project_idea)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "PRIVATE-REGISTRATION-MARKER",
                    user_id,
                    private_markers[0],
                    private_markers[1],
                    "9999999999",
                    "Private College",
                    "B.Tech",
                    "Private Department",
                    "3rd year",
                    "Private Location",
                    "Individual",
                    "Other",
                    "Private Skill",
                    private_markers[2],
                ),
            )
            db.commit()
            reindex_all(db)
            indexed_text = " ".join(
                row["text"]
                for row in db.execute("SELECT text FROM knowledge_chunks").fetchall()
            )
            for marker in private_markers + (
                "PRIVATE-REGISTRATION-MARKER",
                "PrivatePasswordHashMarker",
            ):
                self.assertNotIn(marker, indexed_text)

    def test_admin_knowledge_endpoints_enforce_admin_and_csrf(self):
        csrf = self.client.get("/api/csrf").get_json()["csrf_token"]
        login = self.client.post(
            "/api/login",
            json={
                "email": "rag-admin@example.invalid",
                "password": "rag-test-admin-password",
            },
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(login.status_code, 200)
        admin_csrf = login.get_json()["csrf_token"]

        self.assertEqual(
            self.client.post("/api/admin/knowledge/reindex").status_code,
            403,
        )
        reindexed = self.client.post(
            "/api/admin/knowledge/reindex",
            headers={"X-CSRF-Token": admin_csrf},
        )
        self.assertEqual(reindexed.status_code, 200)
        self.assertIn("custom", reindexed.get_json()["counts"])
        self.assertGreaterEqual(reindexed.get_json()["counts"]["custom"]["documents"], 18)
        search = self.client.get("/api/admin/knowledge/search?q=is+lunch+free")
        self.assertEqual(search.status_code, 200)
        self.assertIn(
            "kb:11",
            [result["source_key"] for result in search.get_json()["results"]],
        )

        participant = self.app.test_client()
        participant_csrf = participant.get("/api/csrf").get_json()["csrf_token"]
        signup = participant.post(
            "/api/signup",
            json={
                "full_name": "RAG Test Participant",
                "email": "rag-participant@example.invalid",
                "password": "rag-test-participant-password",
            },
            headers={"X-CSRF-Token": participant_csrf},
        )
        self.assertEqual(signup.status_code, 201)
        self.assertEqual(
            participant.get("/api/admin/knowledge/search?q=lunch").status_code,
            403,
        )
        self.assertEqual(
            participant.post(
                "/api/admin/knowledge/reindex",
                headers={"X-CSRF-Token": signup.get_json()["csrf_token"]},
            ).status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
