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
sys.path.insert(0, str(BACKEND_DIR))

_IMPORT_TEST_DATA = tempfile.TemporaryDirectory()
os.environ["DATABASE_PATH"] = str(Path(_IMPORT_TEST_DATA.name) / "import-test.db")
os.environ["SECRET_KEY"] = "chatbot-test-import-secret-key"
atexit.register(_IMPORT_TEST_DATA.cleanup)

import chatbot
import hackathon_faq
import hackathon_knowledge
from app import create_app


class HackathonKnowledgeTests(unittest.TestCase):
    def test_retrieves_only_relevant_categorized_hackathon_information(self):
        context = hackathon_knowledge.retrieve_hackathon_context(
            "How do I register?"
        )

        self.assertIn("Registration Process:", context)
        self.assertNotIn("Signup and Login:", context)
        self.assertNotIn("backend/app.py", context)
        self.assertNotIn("CREATE TABLE", context)

    def test_topic_filter_rejects_unrelated_questions(self):
        self.assertTrue(hackathon_knowledge.is_hackathon_question("What is this hackathon?"))
        self.assertFalse(hackathon_knowledge.is_hackathon_question("Write Python code."))
        self.assertFalse(hackathon_knowledge.is_hackathon_question("What is today's gold price?"))
        self.assertFalse(hackathon_knowledge.is_hackathon_question("Explain JavaScript."))

    def test_faq_variations_and_common_typos_match_official_answers(self):
        questions_and_answers = [
            ("What is this hackathon?", "Hack the Future is a student hackathon where participants build innovative projects in a 24-hour sprint."),
            ("What is the purpose of this hackathon?", "Hack the Future is a student hackathon where participants build innovative projects in a 24-hour sprint."),
            ("When does Hack the Future take place?", "The hackathon is scheduled for November 1–2, 2026."),
            ("Where will the event take place?", "The event venue is Innovation Hub, Main Campus."),
            ("How can I register for the hackathon?", "1. Create an account or log in. 2. Select Register and complete the form. 3. Submit it to save your registration and receive a registration ID."),
            ("How do I create an account?", "Select Sign up and enter your name, email, and password."),
            ("How do I log in?", "Select Log in and enter the email and password for your account."),
            ("How can I sign out?", "While signed in, select Log out in the website navigation."),
            ("What details do I need to register?", "The form asks for your name, mobile number, college, degree, department, study year, college location, participation type, domain, technical skills, project idea, and required confirmations. Team registrations also need team and member details. Date of birth, project title, and GitHub profile are optional; your account email is used for registration."),
            ("Who is eligible for the hackathon?", "Participants must be at least 16 years old and college students."),
            ("What is the minimum age to participate?", "Participants must be at least 16 years old and college students."),
            ("Can I join if I am 16?", "Participants must be at least 16 years old and college students."),
            ("Do I need to be a college student?", "Participants must be at least 16 years old and college students."),
            ("Can I come with my family?", "Yes! You can come with your family. However, participants must be 16 years or older and college students."),
            ("Can I bring my parents?", "Yes! You can come with your family. However, participants must be 16 years or older and college students."),
            ("Can I participate alone?", "You can register as an individual or as a team."),
            ("What is the maximum team size?", "Teams can have 2 to 5 participants, including the team leader."),
            ("What time is breakfast?", "Breakfast is scheduled from 8:00 AM to 9:00 AM."),
            ("What time is brekfast?", "Breakfast is scheduled from 8:00 AM to 9:00 AM."),
            ("When is lunch served?", "Lunch is scheduled from 1:00 PM to 2:00 PM."),
            ("Is lunch free?", "Yes! Lunch is completely free for eligible participants. Enjoy your meal! 😊"),
            ("Do we need to pay for lunch?", "No! Lunch is completely free for eligible participants. Enjoy your meal! 😊"),
            ("Do I need to pay for dinner?", "No! Dinner is completely free for eligible participants. Enjoy your meal! 😊"),
            ("Will participants get free lunch?", "Yes! Lunch is completely free for eligible participants. Enjoy your meal! 😊"),
            ("Is lunch included?", "Yes! Lunch is completely free for eligible participants. Enjoy your meal! 😊"),
            ("Is evening snacks free?", "Yes! Evening Snacks is completely free for eligible participants. Enjoy your meal! 😊"),
            ("What are evening snacks timings?", "Evening snacks are scheduled from 4:00 PM to 4:30 PM."),
            ("What time is dinner?", "Dinner is scheduled from 7:30 PM to 8:30 PM. Enjoy your dinner!"),
            ("Is drinking water available?", "Yes! Drinking water is available throughout the event. 💧"),
            ("Is water available?", "Yes! Drinking water is available throughout the event. 💧"),
            ("Do I need to pay for breakfast?", "No! Breakfast is completely free for eligible participants. Enjoy your meal! 😊"),
            ("Do I pay for breakfast?", "No! Breakfast is completely free for eligible participants. Enjoy your meal! 😊"),
            ("Are participants charged for food?", "No! All food is completely free for eligible participants. Enjoy your meals! 😊"),
            ("Is lunch free? What time is dinner?", "Yes! Lunch is completely free for eligible participants. Enjoy your meal! 😊\nDinner is scheduled from 7:30 PM to 8:30 PM. Enjoy your dinner!"),
            ("What facilities are officially announced?", "The announced facilities are breakfast, lunch, evening snacks, dinner, and drinking water."),
            ("How can I contact the organizers?", "Organizer and technical support contact details have not been published on the website yet."),
            ("What is the event parking policy?", "That facility or prize information has not been officially announced. Please check back for updates."),
            ("Write Python code.", None),
            ("What is today's gold price?", None),
            ("Tell me a joke.", None),
            ("What is the weather today?", None),
        ]
        self.assertGreaterEqual(len(questions_and_answers), 20)
        for question, expected in questions_and_answers:
            with self.subTest(question=question):
                if expected is None:
                    self.assertFalse(hackathon_knowledge.is_hackathon_question(question))
                    self.assertIsNone(hackathon_faq.get_faq_reply(question))
                else:
                    self.assertTrue(hackathon_knowledge.is_hackathon_question(question))
                    self.assertEqual(hackathon_faq.get_faq_reply(question), expected)

    def test_published_food_items_override_the_default_unknown_answer(self):
        reply = hackathon_faq.get_faq_reply(
            "What food will be served?",
            [
                {"facility_type": "Lunch", "items": "Rice and vegetables"},
                {"facility_type": "Dinner", "items": "Pasta"},
            ],
        )

        self.assertEqual(
            reply,
            "Lunch items: Rice and vegetables.\nDinner items: Pasta.",
        )

    def test_confirmed_food_policy_overrides_conflicting_published_price_or_availability(self):
        contradictory_facilities = [
            {
                "facility_type": meal,
                "price_status": "Paid",
                "charges": "₹500",
                "availability": "Unavailable",
            }
            for meal in ("Breakfast", "Lunch", "Evening Snacks", "Dinner")
        ] + [
            {
                "facility_type": "Drinking Water",
                "availability": "Unavailable",
                "price_status": "Paid",
            }
        ]

        self.assertEqual(
            hackathon_faq.get_faq_reply("Do I need to pay for dinner?", contradictory_facilities),
            "No! Dinner is completely free for eligible participants. Enjoy your meal! 😊",
        )
        self.assertEqual(
            hackathon_faq.get_faq_reply("Is water available?", contradictory_facilities),
            "Yes! Drinking water is available throughout the event. 💧",
        )

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

    def test_llm_receives_only_latest_question_and_focused_knowledge(self):
        completion = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            "A confirmation email is sent only if delivery is configured "
                            "and succeeds."
                        )
                    )
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
            {"role": "user", "content": "Write Python code."},
            {"role": "assistant", "content": chatbot.OUT_OF_SCOPE_REPLY},
            {"role": "user", "content": "Can you describe the post-submission process for my registration?"},
        ]
        context = (
            "Registration Process:\nA confirmation email is sent only if email "
            "delivery is configured and succeeds."
        )

        with (
            patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}),
            patch.object(chatbot, "Groq", return_value=groq_client),
        ):
            reply = chatbot.get_chatbot_reply(conversation, "Hack the Future", context)

        self.assertEqual(
            reply,
            "A confirmation email is sent only if delivery is configured and succeeds.",
        )
        sent_messages = create_completion.call_args.kwargs["messages"]
        self.assertIn("only facts in the relevant knowledge categories", sent_messages[0]["content"])
        self.assertIn("Registration Process:", sent_messages[0]["content"])
        self.assertNotIn("Write Python", sent_messages[0]["content"])
        self.assertEqual(len(sent_messages), 2)
        self.assertEqual(
            sent_messages[-1]["content"],
            "Can you describe the post-submission process for my registration?",
        )

    def test_sensitive_user_values_are_redacted_before_llm_request(self):
        completion = SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content="Follow the registration steps on the website."))
            ]
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
        ):
            chatbot.get_chatbot_reply(
                [
                    {
                        "role": "user",
                        "content": (
                            "What are the registration steps? "
                            "api_key=gsk_abcdefghijklmnopqrstuvwxyz "
                            "email person@example.com"
                        ),
                    }
                ],
                "Hack the Future",
                "Registration Process:\nCreate an account and submit the form.",
            )

        sent_user_content = create_completion.call_args.kwargs["messages"][-1]["content"]
        self.assertNotIn("gsk_abcdefghijklmnopqrstuvwxyz", sent_user_content)
        self.assertNotIn("person@example.com", sent_user_content)
        self.assertIn("[REDACTED]", sent_user_content)

    def test_missing_knowledge_returns_unknown_without_calling_groq(self):
        with patch.object(chatbot, "Groq") as groq:
            reply = chatbot.get_chatbot_reply(
                [{"role": "user", "content": "What is the event parking policy?"}],
                "Hack the Future",
                "",
            )

        self.assertEqual(reply, hackathon_knowledge.UNKNOWN_INFO_REPLY)
        groq.assert_not_called()

    def test_out_of_scope_question_returns_fixed_reply_without_calling_groq(self):
        with patch.object(chatbot, "Groq") as groq:
            reply = chatbot.get_chatbot_reply(
                [{"role": "user", "content": "Write Python code."}],
                "Hack the Future",
            )

        self.assertEqual(reply, hackathon_knowledge.OUT_OF_SCOPE_REPLY)
        groq.assert_not_called()


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
        self.assertEqual(
            self.answer("What time is breakfast?"),
            "Breakfast is scheduled from 8:00 AM to 9:00 AM.",
        )
        self.assertEqual(
            self.answer("Is lunch complimentary?"),
            "Yes! Lunch is completely free for eligible participants. Enjoy your meal! 😊",
        )
        self.assertEqual(
            self.answer("How much does lunch cost?"),
            "No! Lunch is completely free for eligible participants. Enjoy your meal! 😊",
        )
        self.assertIn("Evening Snacks items: Samosa.", self.answer("What snacks are provided?"))
        self.assertEqual(
            self.answer("What time is dinner?"),
            "Dinner is scheduled from 7:00 PM to 8:00 PM.",
        )
        self.assertIn("Coffee Stall is PAID. Price: ₹25.", self.answer("How much does coffee cost?"))
        self.assertIn("Tea Stall is PAID. Price: ₹15.", self.answer("Is tea free or paid?"))
        self.assertEqual(
            self.answer("Is drinking water free?"),
            "Yes! Drinking water is available throughout the event. 💧",
        )

    def test_stall_availability_and_unknown_values_are_deterministic(self):
        availability = self.answer("Are tea and coffee stalls available?")
        self.assertIn("Tea Stall availability: Available.", availability)
        self.assertIn("Coffee Stall availability: Available.", availability)
        missing_timing = [
            dict(self.food_facilities[0], start_time=None, end_time=None, timing=None)
        ]
        self.assertEqual(
            chatbot.get_food_facility_reply(
                [{"role": "user", "content": "When is breakfast?"}],
                missing_timing,
            ),
            "Breakfast is scheduled from 8:00 AM to 9:00 AM.",
        )

    def test_confirmed_food_policy_is_available_without_database_records(self):
        self.assertEqual(
            chatbot.get_food_facility_reply(
                [{"role": "user", "content": "Is lunch free?"}],
                [],
            ),
            "Yes! Lunch is completely free for eligible participants. Enjoy your meal! 😊",
        )
        self.assertEqual(
            chatbot.get_food_facility_reply(
                [{"role": "user", "content": "What are breakfast timings?"}],
                [],
            ),
            "Breakfast is scheduled from 8:00 AM to 9:00 AM.",
        )
        self.assertEqual(
            chatbot.get_food_facility_reply(
                [{"role": "user", "content": "Is food available?"}],
                [],
            ),
            "Food is available and completely free for eligible participants.",
        )
        self.assertEqual(
            chatbot.get_food_facility_reply(
                [{"role": "user", "content": "Is coffee available?"}],
                [],
            ),
            "Tea and coffee availability has not been officially announced.",
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
                    {
                        "role": "user",
                        "content": "Can you explain the registration steps please?",
                    },
                ],
                self.csrf,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"reply": "It uses React and Flask."})
        self.assertEqual(reply.call_args.args[0][-1]["role"], "user")
        self.assertIn("Registration Process:", reply.call_args.args[2])

    def test_supported_faqs_food_unknowns_and_out_of_scope_questions(self):
        questions_and_replies = [
            (
                "What is this hackathon?",
                "Hack the Future is a student hackathon where participants build "
                "innovative projects in a 24-hour sprint.",
            ),
            (
                "How do I register?",
                "1. Create an account or log in. "
                "2. Select Register and complete the form. "
                "3. Submit it to save your registration and receive a registration ID.",
            ),
            (
                "How do I log in?",
                "Select Log in and enter the email and password for your account.",
            ),
            (
                "Is lunch free?",
                "Yes! Lunch is completely free for eligible participants. Enjoy your meal! 😊",
            ),
            (
                "What are breakfast timings?",
                "Breakfast is scheduled from 8:00 AM to 9:00 AM.",
            ),
            ("Write Python code.", hackathon_knowledge.OUT_OF_SCOPE_REPLY),
            ("What is today's gold price?", hackathon_knowledge.OUT_OF_SCOPE_REPLY),
            (
                "What prizes are there?",
                "That facility or prize information has not been officially announced. "
                "Please check back for updates.",
            ),
            (
                "What is the event parking policy?",
                "That facility or prize information has not been officially announced. "
                "Please check back for updates.",
            ),
            (
                "What facilities are officially announced?",
                "The announced facilities are breakfast, lunch, evening snacks, dinner, "
                "and drinking water.",
            ),
        ]

        with patch("app.get_chatbot_reply") as groq:
            for question, expected_reply in questions_and_replies:
                with self.subTest(question=question):
                    response = self._post_chat(
                        [{"role": "user", "content": question}],
                        self.csrf,
                    )

                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.get_json()["reply"], expected_reply)

        groq.assert_not_called()

    def test_confirmation_email_faq_uses_only_official_behavior(self):
        response = self._post_chat(
            [
                {
                    "role": "user",
                    "content": "Does the website send confirmation emails after registration?",
                }
            ],
            self.csrf,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["reply"],
            "After you submit, the website displays your registration ID. A confirmation "
            "email is sent only if email delivery is configured and succeeds.",
        )

    def test_organizer_contact_is_not_invented(self):
        with patch("app.get_chatbot_reply") as groq:
            response = self._post_chat(
                [{"role": "user", "content": "How can I contact the organizers?"}],
                self.csrf,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["reply"],
            "Organizer and technical support contact details have not been published "
            "on the website yet.",
        )
        groq.assert_not_called()

    def test_provider_failure_returns_clear_error(self):
        provider_error = APIError("provider unavailable", request=Mock(), body=None)
        with patch("app.get_chatbot_reply", side_effect=provider_error):
            response = self._post_chat(
                [
                    {
                        "role": "user",
                        "content": "Can you explain the registration steps please?",
                    }
                ],
                self.csrf,
            )

        self.assertEqual(response.status_code, 502)
        self.assertIn("temporarily unavailable", response.get_json()["error"])

    def test_rate_limits_chat_requests_per_user(self):
        message = [
            {
                "role": "user",
                "content": "What happens after I submit my registration form?",
            }
        ]
        with patch("app.get_chatbot_reply", return_value="Project answer."):
            responses = [self._post_chat(message, self.csrf) for _ in range(10)]
            limited = self._post_chat(message, self.csrf)

        self.assertTrue(all(response.status_code == 200 for response in responses))
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.headers["Retry-After"], "60")


if __name__ == "__main__":
    unittest.main()
