import atexit
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from groq import APIError


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

_IMPORT_TEST_DATA = tempfile.TemporaryDirectory()
os.environ["DATABASE_PATH"] = str(Path(_IMPORT_TEST_DATA.name) / "import-test.db")
os.environ["SECRET_KEY"] = "chatbot-test-import-secret-key"
atexit.register(_IMPORT_TEST_DATA.cleanup)

import chatbot
import project_knowledge
from app import create_app


class ProjectKnowledgeTests(unittest.TestCase):
    def test_retrieves_relevant_registration_and_login_sources(self):
        registration_context = project_knowledge.retrieve_project_context(
            [{"role": "user", "content": "How does user registration work?"}]
        )
        login_context = project_knowledge.retrieve_project_context(
            [{"role": "user", "content": "How does login authenticate accounts?"}]
        )

        self.assertIn("backend/app.py", registration_context)
        self.assertIn("backend/app.py", login_context)

    def test_database_questions_retrieve_schema_without_database_records(self):
        context = project_knowledge.retrieve_project_context(
            [{"role": "user", "content": "What tables are in the database?"}]
        )

        self.assertIn("backend/schema.sql", context)
        self.assertIn("CREATE TABLE", context)
        self.assertNotIn("backend/instance/", context)
        source_paths = [
            line.removeprefix("Source: ")
            for line in context.splitlines()
            if line.startswith("Source: ")
        ]
        self.assertNotIn("backend/.env", source_paths)
        self.assertNotIn("backend/instance/", source_paths)

    def test_redacts_secrets_and_contact_details_before_model_request(self):
        message = (
            "My password=hunter2 and api_key=gsk_abcdefghijklmnopqrstuvwxyz "
            "email me at student@example.com or call +1 (555) 123-4567"
        )

        redacted = chatbot.redact_sensitive_content(message)

        self.assertNotIn("hunter2", redacted)
        self.assertNotIn("gsk_abcdefghijklmnopqrstuvwxyz", redacted)
        self.assertNotIn("student@example.com", redacted)
        self.assertNotIn("555", redacted)
        self.assertEqual(redacted.count("[REDACTED]"), 4)

    def test_llm_receives_retrieved_sources_and_recent_conversation(self):
        completion = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Registration uses a Flask endpoint.")
                )
            ]
        )
        create_completion = Mock(return_value=completion)
        groq_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create_completion)
            )
        )
        conversation = [
            {"role": "user", "content": "What technologies does this project use?"},
            {"role": "assistant", "content": "It uses React and Flask."},
            {"role": "user", "content": "How does registration work?"},
        ]

        with (
            patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}),
            patch.object(chatbot, "Groq", return_value=groq_client),
            patch.object(
                chatbot,
                "retrieve_project_context",
                return_value="Source: backend/app.py\n@app.post('/api/registration')",
            ),
        ):
            reply = chatbot.get_chatbot_reply(conversation, "Hack the Future")

        self.assertEqual(reply, "Registration uses a Flask endpoint.")
        sent_messages = create_completion.call_args.kwargs["messages"]
        self.assertIn("backend/app.py", sent_messages[0]["content"])
        self.assertEqual(sent_messages[-2]["content"], "It uses React and Flask.")
        self.assertEqual(sent_messages[-1]["content"], "How does registration work?")

    def test_sensitive_user_values_are_redacted_before_llm_request(self):
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="I can help with project questions."))]
        )
        create_completion = Mock(return_value=completion)
        groq_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create_completion)
            )
        )

        with (
            patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}),
            patch.object(chatbot, "Groq", return_value=groq_client),
            patch.object(chatbot, "retrieve_project_context", return_value="Source: README.md"),
        ):
            chatbot.get_chatbot_reply(
                [
                    {
                        "role": "user",
                        "content": "My password=hunter2 is private; email is person@example.com",
                    }
                ],
                "Hack the Future",
            )

        sent_user_content = create_completion.call_args.kwargs["messages"][-1]["content"]
        self.assertNotIn("hunter2", sent_user_content)
        self.assertNotIn("person@example.com", sent_user_content)
        self.assertIn("[REDACTED]", sent_user_content)

    def test_missing_project_match_is_sent_to_llm_as_unknown_context(self):
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="The project sources do not specify that."))]
        )
        create_completion = Mock(return_value=completion)
        groq_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create_completion)
            )
        )

        with (
            patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}),
            patch.object(chatbot, "Groq", return_value=groq_client),
            patch.object(chatbot, "retrieve_project_context", return_value=""),
        ):
            reply = chatbot.get_chatbot_reply(
                [{"role": "user", "content": "What are the unlisted cash prizes?"}],
                "Hack the Future",
            )

        self.assertIn("do not specify", reply)
        self.assertIn("No directly relevant", create_completion.call_args.kwargs["messages"][0]["content"])


class FoodFacilityChatTests(unittest.TestCase):
    def setUp(self):
        self.food_facilities = [
            {
                "facility_type": "Breakfast",
                "start_time": "08:00",
                "end_time": "09:00",
                "items": "Idli and fruit",
                "availability": "Available",
                "price_status": "Free",
                "charges": None,
                "location": "Dining hall",
            },
            {
                "facility_type": "Lunch",
                "start_time": "12:30",
                "end_time": "13:30",
                "items": "Rice and vegetables",
                "availability": "Available",
                "price_status": "Free",
                "charges": None,
                "location": "Dining hall",
            },
            {
                "facility_type": "Dinner",
                "start_time": "19:00",
                "end_time": "20:00",
                "items": "Rice and curry",
                "availability": "Available",
                "price_status": "Free",
                "charges": None,
                "location": "Dining hall",
            },
            {
                "facility_type": "Evening Snacks",
                "start_time": "16:00",
                "end_time": "17:00",
                "items": "Samosa",
                "availability": "Available",
                "price_status": "Free",
                "charges": None,
                "location": "Dining hall",
            },
            {
                "facility_type": "Tea Stall",
                "start_time": "10:00",
                "end_time": "22:00",
                "items": "Tea",
                "availability": "Available",
                "price_status": "Paid",
                "charges": "₹15",
                "location": "Student plaza",
            },
            {
                "facility_type": "Coffee Stall",
                "start_time": "10:00",
                "end_time": "22:00",
                "items": "Coffee",
                "availability": "Available",
                "price_status": "Paid",
                "charges": "₹25",
                "location": "Student plaza",
            },
            {
                "facility_type": "Other Beverages",
                "start_time": None,
                "end_time": None,
                "items": "Lemonade - ₹30",
                "availability": "Available",
                "price_status": "Paid",
                "charges": "See item prices",
                "location": "Student plaza",
            },
            {
                "facility_type": "Drinking Water",
                "start_time": None,
                "end_time": None,
                "items": None,
                "availability": "Available",
                "price_status": "Free",
                "charges": None,
                "location": "Library entrance",
            },
        ]

    def answer(self, question):
        return chatbot.get_food_facility_reply(
            [{"role": "user", "content": question}],
            self.food_facilities,
        )

    def test_food_questions_use_saved_times_items_and_prices(self):
        self.assertIn("Breakfast timing: 8:00 AM–9:00 AM.", self.answer("What time is breakfast?"))
        self.assertIn("Lunch is FREE.", self.answer("Is lunch complimentary?"))
        self.assertIn("Evening Snacks items: Samosa.", self.answer("What snacks are provided?"))
        self.assertIn("Dinner timing: 7:00 PM–8:00 PM.", self.answer("What time is dinner?"))
        self.assertIn("Coffee Stall is PAID. Price: ₹25.", self.answer("How much does coffee cost?"))
        self.assertIn("Tea Stall is PAID. Price: ₹15.", self.answer("Is tea free or paid?"))
        self.assertIn("Drinking Water is FREE.", self.answer("Is drinking water free?"))

    def test_stall_availability_and_unknown_values_are_deterministic(self):
        availability = self.answer("Are tea and coffee stalls available?")
        self.assertIn("Tea Stall availability: Available.", availability)
        self.assertIn("Coffee Stall availability: Available.", availability)
        missing_timing = [dict(self.food_facilities[0], start_time=None, end_time=None, timing=None)]
        self.assertEqual(
            chatbot.get_food_facility_reply(
                [{"role": "user", "content": "When is breakfast?"}],
                missing_timing,
            ),
            "Food information has not been announced yet. Please contact the event organizers.",
        )


class ChatRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.old_secret_key = os.environ.get("SECRET_KEY")
        self.old_database_path = os.environ.get("DATABASE_PATH")
        os.environ["SECRET_KEY"] = "chatbot-test-secret-key"
        os.environ["DATABASE_PATH"] = str(Path(self.temp_dir.name) / "chatbot-test.db")
        self.addCleanup(self._restore_secret_key)
        self.addCleanup(self._restore_database_path)

        with patch.dict(os.environ, {"ADMIN_EMAIL": "", "ADMIN_PASSWORD": ""}):
            self.app = create_app()
        self.app.config["TESTING"] = True

        self.client = self.app.test_client()
        csrf = self.client.get("/api/csrf").get_json()["csrf_token"]
        signup = self.client.post(
            "/api/signup",
            json={
                "full_name": "Chat Test User",
                "email": "chat-test@example.invalid",
                "password": "chat-test-password-123",
            },
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(signup.status_code, 201)
        self.csrf = signup.get_json()["csrf_token"]

    def _restore_secret_key(self):
        if self.old_secret_key is None:
            os.environ.pop("SECRET_KEY", None)
        else:
            os.environ["SECRET_KEY"] = self.old_secret_key

    def _restore_database_path(self):
        if self.old_database_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = self.old_database_path

    def _post_chat(self, messages, csrf=None):
        return self.client.post(
            "/api/chat",
            json={"messages": messages},
            headers={"X-CSRF-Token": csrf} if csrf else {},
        )

    def test_requires_authentication_and_csrf(self):
        anonymous = self.app.test_client().post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "Explain the project"}]},
        )
        missing_csrf = self._post_chat(
            [{"role": "user", "content": "Explain the project"}]
        )

        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(missing_csrf.status_code, 403)

    def test_rejects_malformed_and_oversized_conversations(self):
        malformed = self._post_chat([{"role": [], "content": "hello"}], self.csrf)
        oversized = self._post_chat(
            [{"role": "user", "content": "x" * 1201}],
            self.csrf,
        )

        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(oversized.status_code, 400)

    def test_successful_chat_returns_json_reply(self):
        with patch("app.get_chatbot_reply", return_value="It uses React and Flask.") as reply:
            response = self._post_chat(
                [
                    {"role": "assistant", "content": "Hi!"},
                    {"role": "user", "content": "What technologies are used?"},
                ],
                self.csrf,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"reply": "It uses React and Flask."})
        self.assertEqual(reply.call_args.args[0][-1]["role"], "user")

    def test_provider_failure_returns_clear_error(self):
        provider_error = APIError("provider unavailable", request=Mock(), body=None)
        with patch("app.get_chatbot_reply", side_effect=provider_error):
            response = self._post_chat(
                [{"role": "user", "content": "Explain the project"}],
                self.csrf,
            )

        self.assertEqual(response.status_code, 502)
        self.assertIn("temporarily unavailable", response.get_json()["error"])

    def test_rate_limits_chat_requests_per_user(self):
        message = [{"role": "user", "content": "Explain the project"}]
        with patch("app.get_chatbot_reply", return_value="Project answer."):
            responses = [self._post_chat(message, self.csrf) for _ in range(10)]
            limited = self._post_chat(message, self.csrf)

        self.assertTrue(all(response.status_code == 200 for response in responses))
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.headers["Retry-After"], "60")


if __name__ == "__main__":
    unittest.main()
