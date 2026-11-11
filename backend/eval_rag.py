#!/usr/bin/env python3
"""Evaluate RAG retrieval locally, with optional opt-in chat-answer checks."""

import argparse
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import embeddings
import rag
from chatbot import redact_sensitive_content
from hackathon_knowledge import OUT_OF_SCOPE_REPLY, UNKNOWN_INFO_REPLY
from rag import retrieve, retrieve_hybrid, retrieve_semantic, reindex_all


BASE_DIR = Path(__file__).resolve().parent
DATASET_PATH = BASE_DIR / "eval" / "rag_eval_set.json"
DEFAULT_SWEEP_THRESHOLDS = tuple(round(0.40 + index * 0.05, 2) for index in range(8))
RETRIEVAL_MODES = ("bm25", "semantic", "hybrid")


def load_dataset(path=DATASET_PATH):
    with Path(path).open(encoding="utf-8") as dataset_file:
        dataset = json.load(dataset_file)
    if not isinstance(dataset, dict) or not isinstance(dataset.get("cases"), list):
        raise ValueError("Evaluation dataset must contain a cases list.")
    required = {
        "id",
        "category",
        "question",
        "expected_any",
        "expect_no_retrieval",
        "must_contain",
        "must_not_contain",
    }
    identifiers = set()
    for case in dataset["cases"]:
        if not isinstance(case, dict) or required - case.keys():
            raise ValueError("Every evaluation case must contain all required fields.")
        if case["id"] in identifiers:
            raise ValueError(f"Duplicate evaluation case id: {case['id']}")
        identifiers.add(case["id"])
        if not isinstance(case["expected_any"], list):
            raise ValueError(f"{case['id']}: expected_any must be a list.")
        if not isinstance(case["expect_no_retrieval"], bool):
            raise ValueError(f"{case['id']}: expect_no_retrieval must be boolean.")
    return dataset


def retrieval_case_passes(case, results):
    if case["expect_no_retrieval"]:
        return not results
    expected = set(case["expected_any"])
    return any(result.get("source_key") in expected for result in results)


def retrieval_metrics(cases, case_results, k=3):
    relevant_cases = [case for case in cases if case["expected_any"]]
    no_retrieval_cases = [case for case in cases if case["expect_no_retrieval"]]
    hits_at_1 = 0
    hits_at_k = 0
    reciprocal_rank_sum = 0.0
    for case in relevant_cases:
        results = case_results.get(case["id"], {}).get("results", [])[:k]
        expected = set(case["expected_any"])
        ranks = [
            rank
            for rank, result in enumerate(results, start=1)
            if result.get("source_key") in expected
        ]
        if ranks:
            hits_at_k += 1
            reciprocal_rank_sum += 1 / ranks[0]
            if ranks[0] == 1:
                hits_at_1 += 1
    rejected = sum(
        not case_results.get(case["id"], {}).get("results", [])
        for case in no_retrieval_cases
    )
    return {
        "relevant_cases": len(relevant_cases),
        "no_retrieval_cases": len(no_retrieval_cases),
        "hit_at_1": hits_at_1 / len(relevant_cases) if relevant_cases else None,
        "hit_at_3": hits_at_k / len(relevant_cases) if relevant_cases else None,
        "mrr": reciprocal_rank_sum / len(relevant_cases) if relevant_cases else None,
        "rejection_rate": (
            rejected / len(no_retrieval_cases) if no_retrieval_cases else None
        ),
    }


def evaluate_retrieval(db, cases, mode="all"):
    selected_modes = RETRIEVAL_MODES if mode == "all" else (mode,)
    results_by_mode = {}
    skipped = {}
    for selected_mode in selected_modes:
        if selected_mode not in RETRIEVAL_MODES:
            raise ValueError(f"Unsupported retrieval mode: {selected_mode}")
        if selected_mode != "bm25" and not embeddings.embeddings_available():
            skipped[selected_mode] = "GEMINI_API_KEY is missing; embeddings are unavailable."
            continue

        per_case = {}
        try:
            for case in cases:
                if selected_mode == "bm25":
                    results = retrieve(db, case["question"], k=3)
                elif selected_mode == "semantic":
                    results = retrieve_semantic(db, case["question"], k=3)
                else:
                    results = retrieve_hybrid(db, case["question"], k=3)["results"]
                per_case[case["id"]] = {
                    "question": case["question"],
                    "results": results,
                    "pass": retrieval_case_passes(case, results),
                }
        except embeddings.EmbeddingError as exc:
            skipped[selected_mode] = f"Embedding request failed: {exc}"
            continue

        categories = {}
        for category in sorted({case["category"] for case in cases}):
            category_cases = [case for case in cases if case["category"] == category]
            categories[category] = retrieval_metrics(
                category_cases,
                per_case,
            )
        results_by_mode[selected_mode] = {
            "metrics": retrieval_metrics(cases, per_case),
            "categories": categories,
            "cases": per_case,
        }
    return {"modes": results_by_mode, "skipped": skipped}


def threshold_sweep(db, cases, thresholds=DEFAULT_SWEEP_THRESHOLDS):
    if not embeddings.embeddings_available():
        return {
            "skipped": "GEMINI_API_KEY is missing; hybrid threshold sweep requires embeddings.",
            "thresholds": [],
            "recommended_threshold": None,
        }
    original_threshold = os.environ.get("SEMANTIC_MIN_SCORE")
    scores = []
    try:
        for threshold in thresholds:
            os.environ["SEMANTIC_MIN_SCORE"] = str(threshold)
            per_case = {}
            for case in cases:
                hybrid = retrieve_hybrid(db, case["question"], k=3)
                per_case[case["id"]] = {
                    "question": case["question"],
                    "results": hybrid["results"],
                    "pass": retrieval_case_passes(case, hybrid["results"]),
                }
            metrics = retrieval_metrics(cases, per_case)
            hit_at_3 = metrics["hit_at_3"] or 0.0
            rejection_rate = metrics["rejection_rate"] or 0.0
            scores.append(
                {
                    "threshold": threshold,
                    "hit_at_3": hit_at_3,
                    "rejection_rate": rejection_rate,
                    "lower_metric": min(hit_at_3, rejection_rate),
                }
            )
    except embeddings.EmbeddingError as exc:
        return {
            "skipped": f"Embedding request failed: {exc}",
            "thresholds": scores,
            "recommended_threshold": None,
        }
    finally:
        if original_threshold is None:
            os.environ.pop("SEMANTIC_MIN_SCORE", None)
        else:
            os.environ["SEMANTIC_MIN_SCORE"] = original_threshold

    recommendation = max(
        scores,
        key=lambda item: (
            item["lower_metric"],
            item["hit_at_3"],
            item["rejection_rate"],
        ),
    )["threshold"] if scores else None
    return {
        "skipped": None,
        "thresholds": scores,
        "recommended_threshold": recommendation,
    }


def quality_gate_failures(
    results_by_mode,
    min_hit3=0.90,
    min_reject=0.90,
    min_answer=None,
    answer_rate=None,
):
    failures = []
    for mode_name, report in results_by_mode.items():
        metrics = report["metrics"] if "metrics" in report else report
        hit_at_3 = metrics.get("hit_at_3")
        rejection_rate = metrics.get("rejection_rate")
        if hit_at_3 is not None and hit_at_3 < min_hit3:
            failures.append(
                f"{mode_name} Hit@3 {hit_at_3:.3f} is below {min_hit3:.3f}"
            )
        if rejection_rate is not None and rejection_rate < min_reject:
            failures.append(
                f"{mode_name} rejection rate {rejection_rate:.3f} is below {min_reject:.3f}"
            )
    if min_answer is not None:
        if answer_rate is None:
            failures.append("--min-answer was set but no chat answer rate is available")
        elif answer_rate < min_answer:
            failures.append(
                f"chat answer rate {answer_rate:.3f} is below {min_answer:.3f}"
            )
    return failures


def quality_gate_exit_code(failures):
    return 1 if failures else 0


def compare_baseline(current, baseline):
    flips = []
    suites = (
        ("retrieval", current.get("case_results", {}), baseline.get("case_results", {})),
        ("chat", current.get("chat_case_results", {}), baseline.get("chat_case_results", {})),
    )
    for suite_name, current_modes, baseline_modes in suites:
        for mode_name, current_cases in current_modes.items():
            previous_cases = baseline_modes.get(mode_name, {})
            for case_id, current_case in current_cases.items():
                previous_case = previous_cases.get(case_id)
                if previous_case is None:
                    continue
                old_pass = bool(previous_case.get("pass"))
                new_pass = bool(current_case.get("pass"))
                if old_pass != new_pass:
                    flips.append(
                        {
                            "suite": suite_name,
                            "mode": mode_name,
                            "id": case_id,
                            "question": current_case.get("question", ""),
                            "previous_pass": old_pass,
                            "current_pass": new_pass,
                        }
                    )
    return flips


def _format_metric(value):
    return "N/A" if value is None else f"{value:.3f}"


def print_retrieval_report(report, cases):
    print("\nRetrieval metrics (k=3)")
    print(f"{'Mode':<10} {'Category':<20} {'Hit@1':>7} {'Hit@3':>7} {'MRR':>7} {'Reject':>8}")
    print("-" * 64)
    for mode_name, mode_report in report["modes"].items():
        metrics = mode_report["metrics"]
        print(
            f"{mode_name:<10} {'ALL':<20} "
            f"{_format_metric(metrics['hit_at_1']):>7} "
            f"{_format_metric(metrics['hit_at_3']):>7} "
            f"{_format_metric(metrics['mrr']):>7} "
            f"{_format_metric(metrics['rejection_rate']):>8}"
        )
        for category, category_metrics in mode_report["categories"].items():
            print(
                f"{'':<10} {category:<20} "
                f"{_format_metric(category_metrics['hit_at_1']):>7} "
                f"{_format_metric(category_metrics['hit_at_3']):>7} "
                f"{_format_metric(category_metrics['mrr']):>7} "
                f"{_format_metric(category_metrics['rejection_rate']):>8}"
            )
        failures = [
            case
            for case in cases
            if not mode_report["cases"][case["id"]]["pass"]
        ]
        if failures:
            print(f"\nFailed cases for {mode_name}:")
            for case in failures:
                actual = mode_report["cases"][case["id"]]["results"]
                retrieved = [
                    {
                        "source_key": item.get("source_key"),
                        "score": item.get(
                            "score",
                            item.get(
                                "semantic_score",
                                item.get("fused_score"),
                            ),
                        ),
                    }
                    for item in actual
                ]
                print(
                    f"- {case['id']} {case['question']!r}; "
                    f"expected_any={case['expected_any']}; actual={retrieved}"
                )
    for mode_name, message in report["skipped"].items():
        print(f"\nSkipped {mode_name}: {message}")

    off_topic = [case for case in cases if case["expect_no_retrieval"]]
    for mode_name in ("bm25", "semantic"):
        mode_report = report["modes"].get(mode_name)
        if mode_report is None:
            continue
        false_positives = [
            case for case in off_topic
            if mode_report["cases"][case["id"]]["results"]
        ]
        if false_positives:
            print(f"\nOff-topic questions wrongly retrieved by {mode_name} (top scores):")
            for case in false_positives:
                results = mode_report["cases"][case["id"]]["results"]
                top = results[0]
                score = top.get("score", top.get("semantic_score"))
                print(
                    f"- {case['id']} {case['question']!r}: "
                    f"{top.get('source_key')} score={score}"
                )


def print_sweep_report(sweep):
    if sweep.get("skipped"):
        print(f"\nThreshold sweep skipped: {sweep['skipped']}")
        return
    print("\nHybrid threshold sweep")
    print(f"{'SEMANTIC_MIN_SCORE':>18} {'Hit@3':>8} {'Reject':>8} {'Lower':>8}")
    for row in sweep["thresholds"]:
        print(
            f"{row['threshold']:>18.2f} {row['hit_at_3']:>8.3f} "
            f"{row['rejection_rate']:>8.3f} {row['lower_metric']:>8.3f}"
        )
    print(f"Recommended threshold: {sweep['recommended_threshold']:.2f}")


class _ChatPathHandler:
    def __init__(self):
        import logging

        self.handler = logging.Handler()
        self.handler.records = []
        self.handler.emit = lambda record: self.handler.records.append(record.getMessage())

    def __enter__(self):
        import logging

        self.logger = logging.getLogger("app")
        self.logger.addHandler(self.handler)
        return self

    def __exit__(self, *_args):
        self.logger.removeHandler(self.handler)

    def take_path(self):
        path_info = None
        ungrounded = False
        for message in self.handler.records:
            if "chatbot_rag ungrounded_number" in message:
                ungrounded = True
            marker = "chatbot_rag "
            index = message.find(marker)
            if index < 0:
                continue
            try:
                payload = json.loads(message[index + len(marker):])
            except json.JSONDecodeError:
                continue
            path_info = payload
            ungrounded = ungrounded or payload.get("warning") == "ungrounded_number"
        self.handler.records.clear()
        return path_info, ungrounded


def run_chat_evaluation(flask_app, cases, delay_seconds=6.1):
    flask_app.config["TESTING"] = True
    client = flask_app.test_client()
    csrf = client.get("/api/csrf").get_json()["csrf_token"]
    signup = client.post(
        "/api/signup",
        json={
            "full_name": "RAG Evaluation User",
            "email": "rag-eval-user@example.invalid",
            "password": "rag-evaluation-temporary-password",
        },
        headers={"X-CSRF-Token": csrf},
    )
    if signup.status_code != 201:
        raise RuntimeError(f"Could not create temporary evaluation user: HTTP {signup.status_code}.")
    csrf = signup.get_json()["csrf_token"]

    case_results = {}
    path_counts = {}
    ungrounded_fallbacks = 0
    source_count = 0
    passed_count = 0
    with _ChatPathHandler() as path_handler:
        for index, case in enumerate(cases):
            if index:
                time.sleep(max(0.0, delay_seconds))
            print(f"\rChat evaluation: {index + 1}/{len(cases)}", end="", flush=True)
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": case["question"]}]},
                headers={"X-CSRF-Token": csrf},
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"Chat evaluation case {case['id']} returned HTTP {response.status_code}."
                )
            payload = response.get_json()
            reply = str(payload.get("reply", ""))
            log_info, was_ungrounded = path_handler.take_path()
            path_name = (log_info or {}).get("path", "unknown_path")
            path_counts[path_name] = path_counts.get(path_name, 0) + 1
            ungrounded_fallbacks += int(was_ungrounded)
            sources = payload.get("sources") or []
            source_count += int(bool(sources))
            lower_reply = reply.casefold()
            missing = [
                phrase
                for phrase in case["must_contain"]
                if phrase.casefold() not in lower_reply
            ]
            forbidden = [
                phrase
                for phrase in case["must_not_contain"]
                if phrase.casefold() in lower_reply
            ]
            if case["expect_no_retrieval"] and reply not in {
                OUT_OF_SCOPE_REPLY,
                UNKNOWN_INFO_REPLY,
            }:
                forbidden.append("expected out-of-scope or unknown reply")
            passed = not missing and not forbidden
            passed_count += int(passed)
            case_results[case["id"]] = {
                "question": case["question"],
                "reply": redact_sensitive_content(reply),
                "pass": passed,
                "missing": missing,
                "forbidden": forbidden,
                "path": path_name,
                "sources_returned": bool(sources),
            }
    print()
    answer_rate = passed_count / len(cases) if cases else None
    return {
        "metrics": {
            "answer_pass_rate": answer_rate,
            "answers_passed": passed_count,
            "case_count": len(cases),
            "ungrounded_number_fallbacks": ungrounded_fallbacks,
            "answers_with_sources": source_count,
            "path_counts": path_counts,
        },
        "cases": case_results,
    }


def _prepare_isolated_app(database_path):
    os.environ["DATABASE_URL"] = ""
    os.environ["DATABASE_PATH"] = str(database_path)
    os.environ["SECRET_KEY"] = "temporary-rag-evaluation-secret"
    os.environ["ADMIN_EMAIL"] = ""
    os.environ["ADMIN_PASSWORD"] = ""
    os.environ["RAG_ENABLED"] = "true"
    try:
        import app as app_module
    except Exception as exc:
        raise RuntimeError("Could not initialize the Flask app for isolated evaluation.") from exc
    gemini_key = os.environ.get("GEMINI_API_KEY")
    os.environ["GEMINI_API_KEY"] = ""
    try:
        flask_app = app_module.create_app()
    finally:
        if gemini_key is None:
            os.environ.pop("GEMINI_API_KEY", None)
        else:
            os.environ["GEMINI_API_KEY"] = gemini_key
    flask_app.config["TESTING"] = True
    return app_module, flask_app


def run(args):
    dataset = load_dataset(args.dataset)
    cases = dataset["cases"]
    with tempfile.TemporaryDirectory(prefix="rag-eval-") as temp_dir:
        database_path = Path(temp_dir) / "evaluation.sqlite"
        _app_module, flask_app = _prepare_isolated_app(database_path)
        for worker in threading.enumerate():
            if worker.name == "knowledge-embeddings" and worker.is_alive():
                worker.join()
        with flask_app.app_context():
            db = flask_app.get_db()
            reindex_all(db, embed=False)
            if embeddings.embeddings_available():
                embedded = rag.embed_missing_chunks(db)
                if embedded.get("embedding_error"):
                    print(
                        "Warning: some document chunks could not be embedded; "
                        "semantic evaluation may be incomplete."
                    )
                else:
                    print(
                        "Embedding preparation: "
                        f"{embedded['chunks_embedded']} embedded, "
                        f"{embedded['chunks_skipped_unchanged']} unchanged."
                    )
            else:
                print("GEMINI_API_KEY is missing; semantic and hybrid retrieval will be skipped.")
            retrieval = evaluate_retrieval(db, cases, mode=args.mode)
            sweep = (
                threshold_sweep(db, cases)
                if args.sweep and args.mode in {"all", "hybrid"}
                else None
            )
        print_retrieval_report(retrieval, cases)
        if sweep is not None:
            print_sweep_report(sweep)

        chat_report = None
        if args.chat:
            if not os.environ.get("GROQ_API_KEY", "").strip():
                raise RuntimeError("GROQ_API_KEY is required for --chat.")
            if not embeddings.embeddings_available():
                print(
                    "Warning: GEMINI_API_KEY is unavailable; chat will use the "
                    "application's BM25 fallback where needed."
                )
            chat_report = run_chat_evaluation(
                flask_app,
                cases,
                delay_seconds=args.chat_delay,
            )
            chat_metrics = chat_report["metrics"]
            print("\nChat answer evaluation")
            print(
                f"Answer pass rate: {chat_metrics['answer_pass_rate']:.3f} "
                f"({chat_metrics['answers_passed']}/{chat_metrics['case_count']})"
            )
            print(
                f"Ungrounded-number fallbacks: {chat_metrics['ungrounded_number_fallbacks']}; "
                f"answers with sources: {chat_metrics['answers_with_sources']}"
            )
            print(f"Paths: {chat_metrics['path_counts']}")
            failures = [
                (case, chat_report["cases"][case["id"]])
                for case in cases
                if not chat_report["cases"][case["id"]]["pass"]
            ]
            if failures:
                print("Chat answer failures:")
                for case, result in failures:
                    print(
                        f"- {case['id']} {case['question']!r}; "
                        f"missing={result['missing']}; forbidden={result['forbidden']}; "
                        f"path={result['path']}; reply={result['reply']!r}"
                    )

        full_results = {
            "dataset_notes": dataset.get("notes", ""),
            "case_count": len(cases),
            "embeddings_available": embeddings.embeddings_available(),
            "retrieval": retrieval,
            "case_results": {
                mode_name: mode_report["cases"]
                for mode_name, mode_report in retrieval["modes"].items()
            },
            "sweep": sweep,
            "chat": chat_report,
            "chat_case_results": chat_report["cases"] if chat_report else {},
        }
        if args.baseline:
            with Path(args.baseline).open(encoding="utf-8") as baseline_file:
                flips = compare_baseline(full_results, json.load(baseline_file))
            full_results["baseline_flips"] = flips
            print("\nBaseline comparison")
            if not flips:
                print("No cases flipped.")
            for flip in flips:
                transition = "pass → fail" if flip["previous_pass"] else "fail → pass"
                print(
                    f"- {flip['suite']}/{flip['mode']} {flip['id']}: "
                    f"{transition} — {flip['question']}"
                )
        answer_rate = chat_report["metrics"]["answer_pass_rate"] if chat_report else None
        gate_failures = quality_gate_failures(
            retrieval["modes"],
            min_hit3=args.min_hit3,
            min_reject=args.min_reject,
            min_answer=args.min_answer,
            answer_rate=answer_rate,
        )
        full_results["gate_failures"] = gate_failures
        if args.json_path:
            output_path = Path(args.json_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(full_results, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"\nFull results written to {output_path}")
        if gate_failures:
            print("\nQuality gates failed:")
            for failure in gate_failures:
                print(f"- {failure}")
            return quality_gate_exit_code(gate_failures)
        print("\nQuality gates passed.")
        return quality_gate_exit_code(gate_failures)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=(*RETRIEVAL_MODES, "all"),
        default="all",
        help="Retrieval modes to evaluate (default: all).",
    )
    parser.add_argument("--sweep", action="store_true", help="Sweep hybrid relevance thresholds.")
    parser.add_argument("--chat", action="store_true", help="Opt in to real Groq/Gemini chat evaluation.")
    parser.add_argument("--chat-delay", type=float, default=6.1, help=argparse.SUPPRESS)
    parser.add_argument("--json", dest="json_path", help="Write full results to this JSON file.")
    parser.add_argument("--baseline", help="Compare case pass/fail results with a prior JSON run.")
    parser.add_argument("--min-hit3", type=float, default=0.90)
    parser.add_argument("--min-reject", type=float, default=0.90)
    parser.add_argument("--min-answer", type=float)
    parser.add_argument("--dataset", default=str(DATASET_PATH), help=argparse.SUPPRESS)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.min_answer is not None and not args.chat:
        parser.error("--min-answer requires --chat.")
    if args.chat_delay < 0:
        parser.error("--chat-delay must be non-negative.")
    try:
        return run(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
