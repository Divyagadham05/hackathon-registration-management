import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import eval_rag
from app import create_app


class RagEvaluationTests(unittest.TestCase):
    def test_dataset_has_36_well_formed_unique_cases_and_real_source_keys(self):
        dataset = eval_rag.load_dataset()
        cases = dataset["cases"]
        self.assertEqual(len(cases), 36)
        self.assertIn("update cases 28-29", dataset["notes"])
        self.assertEqual(len({case["id"] for case in cases}), 36)
        required = {
            "id",
            "category",
            "question",
            "expected_any",
            "expect_no_retrieval",
            "must_contain",
            "must_not_contain",
        }
        for case in cases:
            self.assertTrue(required <= case.keys())
        self.assertIn("faq:event_date", cases[0]["expected_any"])
        self.assertIn("kb:2", cases[0]["expected_any"])
        self.assertIn("faq:meal_prices", cases[13]["expected_any"])

    def test_hit_at_k_mrr_and_rejection_rate_calculations(self):
        cases = [
            {
                "id": "first",
                "expected_any": ["faq:a"],
                "expect_no_retrieval": False,
            },
            {
                "id": "second",
                "expected_any": ["kb:b"],
                "expect_no_retrieval": False,
            },
            {
                "id": "negative-1",
                "expected_any": [],
                "expect_no_retrieval": True,
            },
            {
                "id": "negative-2",
                "expected_any": [],
                "expect_no_retrieval": True,
            },
        ]
        results = {
            "first": {"results": [{"source_key": "faq:a"}]},
            "second": {
                "results": [
                    {"source_key": "other"},
                    {"source_key": "kb:b"},
                ]
            },
            "negative-1": {"results": []},
            "negative-2": {"results": [{"source_key": "faq:wrong"}]},
        }
        metrics = eval_rag.retrieval_metrics(cases, results, k=3)
        self.assertEqual(metrics["hit_at_1"], 0.5)
        self.assertEqual(metrics["hit_at_3"], 1.0)
        self.assertEqual(metrics["mrr"], 0.75)
        self.assertEqual(metrics["rejection_rate"], 0.5)

    def test_quality_gates_return_failing_and_passing_codes(self):
        failing = eval_rag.quality_gate_failures(
            {"bm25": {"hit_at_3": 0.5, "rejection_rate": 0.4}},
            min_hit3=0.9,
            min_reject=0.9,
        )
        self.assertEqual(len(failing), 2)
        self.assertEqual(eval_rag.quality_gate_exit_code(failing), 1)
        passing = eval_rag.quality_gate_failures(
            {"hybrid": {"hit_at_3": 0.95, "rejection_rate": 1.0}},
            min_hit3=0.9,
            min_reject=0.9,
        )
        self.assertEqual(passing, [])
        self.assertEqual(eval_rag.quality_gate_exit_code(passing), 0)
        self.assertTrue(
            eval_rag.quality_gate_failures(
                {},
                min_answer=0.9,
                answer_rate=0.5,
            )
        )

    def test_threshold_sweep_recommends_threshold_maximizing_lower_metric(self):
        cases = [
            {
                "id": "positive",
                "question": "positive",
                "expected_any": ["kb:expected"],
                "expect_no_retrieval": False,
            },
            {
                "id": "negative",
                "question": "negative",
                "expected_any": [],
                "expect_no_retrieval": True,
            },
        ]

        def fake_hybrid(_db, question, k):
            threshold = float(os.environ["SEMANTIC_MIN_SCORE"])
            include = (
                threshold <= 0.55
                if question == "positive"
                else threshold < 0.55
            )
            hits = (
                [{"source_key": "kb:expected", "fused_score": 0.01}]
                if include and question == "positive"
                else [{"source_key": "faq:wrong", "fused_score": 0.01}]
                if include
                else []
            )
            return {"mode": "hybrid", "results": hits[:k]}

        with (
            patch("eval_rag.embeddings.embeddings_available", return_value=True),
            patch("eval_rag.retrieve_hybrid", side_effect=fake_hybrid),
        ):
            result = eval_rag.threshold_sweep(
                object(),
                cases,
                thresholds=[0.4, 0.55, 0.7],
            )
        self.assertEqual(result["recommended_threshold"], 0.55)
        middle = result["thresholds"][1]
        self.assertEqual(middle["hit_at_3"], 1.0)
        self.assertEqual(middle["rejection_rate"], 1.0)

    def test_missing_gemini_key_skips_semantic_and_hybrid(self):
        cases = eval_rag.load_dataset()["cases"][:1]
        with (
            patch("eval_rag.embeddings.embeddings_available", return_value=False),
            patch("eval_rag.retrieve", return_value=[]),
        ):
            result = eval_rag.evaluate_retrieval(object(), cases, mode="all")
        self.assertIn("bm25", result["modes"])
        self.assertIn("semantic", result["skipped"])
        self.assertIn("hybrid", result["skipped"])
        self.assertIn("GEMINI_API_KEY", result["skipped"]["semantic"])

    def test_baseline_comparison_lists_both_flip_directions(self):
        current = {
            "case_results": {
                "bm25": {
                    "a": {"pass": False, "question": "question a"},
                    "b": {"pass": True, "question": "question b"},
                }
            },
            "chat_case_results": {
                "chat": {"c": {"pass": True, "question": "question c"}}
            },
        }
        baseline = {
            "case_results": {
                "bm25": {
                    "a": {"pass": True},
                    "b": {"pass": False},
                }
            },
            "chat_case_results": {
                "chat": {"c": {"pass": False}}
            },
        }
        flips = eval_rag.compare_baseline(current, baseline)
        self.assertEqual(len(flips), 3)
        self.assertEqual(
            {(item["id"], item["previous_pass"], item["current_pass"]) for item in flips},
            {("a", True, False), ("b", False, True), ("c", False, True)},
        )

    def test_chat_evaluation_uses_mocked_groq_and_records_path(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {
                "SECRET_KEY": "eval-chat-test-secret",
                "DATABASE_URL": "",
                "DATABASE_PATH": str(Path(temp_dir) / "eval-chat.db"),
                "ADMIN_EMAIL": "",
                "ADMIN_PASSWORD": "",
                "GROQ_API_KEY": "fake-groq-key",
                "GEMINI_API_KEY": "",
                "RAG_ENABLED": "true",
            },
        ):
            flask_app = create_app()
            flask_app.config["TESTING"] = True
            case = {
                "id": "chat-case",
                "category": "direct",
                "question": "tell me when the event happens",
                "expected_any": ["kb:2"],
                "expect_no_retrieval": False,
                "must_contain": ["november"],
                "must_not_contain": [],
            }
            completion = SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="The event is in November.")
                    )
                ]
            )
            with (
                patch(
                    "app.get_hackathon_faq_reply",
                    return_value=None,
                ),
                patch(
                    "app.get_food_facility_reply",
                    return_value=None,
                ),
                patch(
                    "app.retrieve_hybrid",
                    return_value={
                        "mode": "bm25_fallback",
                        "results": [
                            {
                                "chunk_text": "The event is in November.",
                                "title": "Event Details",
                                "source_type": "custom",
                                "source_key": "kb:2",
                                "bm25_score": 0.4,
                                "semantic_score": None,
                                "fused_score": 0.01,
                            }
                        ],
                    },
                ),
                patch("chatbot.Groq") as groq_class,
            ):
                groq_class.return_value.chat.completions.create.return_value = completion
                report = eval_rag.run_chat_evaluation(flask_app, [case], delay_seconds=0)
            self.assertEqual(report["metrics"]["answer_pass_rate"], 1.0)
            self.assertEqual(report["metrics"]["path_counts"], {"rag": 1})
            self.assertTrue(report["cases"]["chat-case"]["sources_returned"])
            groq_class.return_value.chat.completions.create.assert_called_once()


if __name__ == "__main__":
    unittest.main()
