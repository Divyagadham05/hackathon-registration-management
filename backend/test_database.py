import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database import DatabaseConnection, connect_database
from app import create_app


class RecordingConnection:
    def execute(self, query, parameters):
        self.last_query = query
        self.last_parameters = parameters
        return "cursor"


class StartupCursor:
    def fetchall(self):
        return []


class StartupConnection:
    def execute(self, query, parameters=()):
        return StartupCursor()

    def commit(self):
        pass

    def close(self):
        pass


class PostgreSQLAdapterTests(unittest.TestCase):
    def test_translates_sqlite_placeholders_for_postgres(self):
        connection = RecordingConnection()
        database = DatabaseConnection(connection, postgres=True)

        result = database.execute("SELECT id FROM users WHERE email = ?", ("user@example.invalid",))

        self.assertEqual(result, "cursor")
        self.assertEqual(connection.last_query, "SELECT id FROM users WHERE email = %s")
        self.assertEqual(connection.last_parameters, ("user@example.invalid",))

    def test_postgres_connection_does_not_create_a_local_database_file(self):
        connection = RecordingConnection()

        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "unused-database.db"
            with patch("database.psycopg.connect", return_value=connection) as connect:
                database = connect_database("postgresql://example.invalid/database", database_path)

            self.assertTrue(database.postgres)
            connect.assert_called_once()
            self.assertFalse(database_path.exists())

    def test_postgres_app_startup_does_not_create_sqlite_instance_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sqlite_path = Path(temp_dir) / "instance" / "hackathon.db"
            environment = {
                "SECRET_KEY": "postgres-startup-test-secret",
                "DATABASE_URL": "postgresql://example.invalid/database",
                "DATABASE_PATH": str(sqlite_path),
                "ADMIN_EMAIL": "",
                "ADMIN_PASSWORD": "",
            }
            database = DatabaseConnection(StartupConnection(), postgres=True)
            with (
                patch.dict(os.environ, environment),
                patch("app.connect_database", return_value=database) as connect,
            ):
                application = create_app()

            self.assertEqual(application.config["DATABASE_TYPE"], "postgres")
            self.assertIsNone(application.config["DATABASE"])
            connect.assert_called_once_with(environment["DATABASE_URL"], None)
            self.assertFalse(sqlite_path.parent.exists())


class SQLiteApplicationSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.environment = patch.dict(
            os.environ,
            {
                "SECRET_KEY": "deployment-smoke-test-secret",
                "DATABASE_URL": "",
                "DATABASE_PATH": str(Path(self.temp_dir.name) / "smoke-test.db"),
                "ADMIN_EMAIL": "",
                "ADMIN_PASSWORD": "",
                "SMTP_HOST": "",
                "SMTP_FROM_EMAIL": "",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        csrf = self.client.get("/api/csrf").get_json()["csrf_token"]
        response = self.client.post(
            "/api/signup",
            json={
                "full_name": "Deployment Smoke User",
                "email": "smoke@example.invalid",
                "password": "deployment-smoke-password",
            },
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(response.status_code, 201)
        self.csrf = response.get_json()["csrf_token"]

    def test_signup_registration_admin_and_export_routes(self):
        registration = {
            "full_name": "Deployment Smoke User",
            "mobile_number": "+1 555 123 4567",
            "college_name": "Example University",
            "degree": "B.Tech",
            "department": "Computer Science",
            "year_of_study": "3rd year",
            "college_location": "Example City",
            "participation_type": "Individual",
            "domain": "Web Development",
            "technical_skills": "React, Python",
            "project_idea": "A test project idea",
            "accept_rules": True,
            "confirm_information": True,
        }
        created = self.client.post(
            "/api/registration",
            json=registration,
            headers={"X-CSRF-Token": self.csrf},
        )

        self.assertEqual(created.status_code, 201)
        registration_id = created.get_json()["registration"]["registration_id"]
        saved = self.client.get("/api/registration").get_json()["registration"]
        self.assertEqual(saved["registration_id"], registration_id)

        with self.app.app_context():
            database = self.app.get_db()
            database.execute(
                "UPDATE users SET is_admin = TRUE WHERE email = ?",
                ("smoke@example.invalid",),
            )
            database.commit()

        listed = self.client.get("/api/admin/registrations?q=Smoke")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.get_json()["registrations"]), 1)

        changed = self.client.patch(
            f"/api/admin/registrations/{registration_id}",
            json={"status": "Accepted"},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(changed.status_code, 200)
        self.assertIn("registration_id,full_name,email", self.client.get("/api/admin/export.csv").text)

        logged_out = self.client.post(
            "/api/logout",
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(logged_out.status_code, 200)
        csrf = self.client.get("/api/csrf").get_json()["csrf_token"]
        logged_in = self.client.post(
            "/api/login",
            json={
                "email": "smoke@example.invalid",
                "password": "deployment-smoke-password",
            },
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(logged_in.status_code, 200)
        self.assertEqual(logged_in.get_json()["user"]["email"], "smoke@example.invalid")

    def test_existing_food_facility_table_is_migrated_without_losing_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "legacy-food.db"
            connection = sqlite3.connect(database_path)
            try:
                connection.execute(
                    """CREATE TABLE food_facilities (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        facility_type TEXT NOT NULL UNIQUE,
                        timing TEXT,
                        availability TEXT NOT NULL DEFAULT 'Not Announced Yet',
                        price_status TEXT NOT NULL DEFAULT 'Not Announced Yet',
                        charges TEXT,
                        location TEXT,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )"""
                )
                connection.execute(
                    """INSERT INTO food_facilities
                       (facility_type, timing, availability, price_status, location)
                       VALUES ('Lunch', '12:00 PM–1:00 PM', 'Available', 'Free', 'Dining Hall')"""
                )
                connection.commit()
            finally:
                connection.close()
            with patch.dict(
                os.environ,
                {
                    "SECRET_KEY": "food-schema-migration-test",
                    "DATABASE_URL": "",
                    "DATABASE_PATH": str(database_path),
                    "ADMIN_EMAIL": "",
                    "ADMIN_PASSWORD": "",
                },
            ):
                create_app()

            connection = sqlite3.connect(database_path)
            try:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(food_facilities)")
                }
                saved = connection.execute(
                    "SELECT timing, start_time, end_time, items, published FROM food_facilities WHERE facility_type = 'Lunch'"
                ).fetchone()
            finally:
                connection.close()
            self.assertTrue({"start_time", "end_time", "items", "published"}.issubset(columns))
            self.assertEqual(saved, ("12:00 PM–1:00 PM", None, None, None, 0))

    def test_food_facilities_admin_crud_public_data_and_chatbot_answers(self):
        types = [
            "Breakfast",
            "Lunch",
            "Evening Snacks",
            "Dinner",
            "Tea Stall",
            "Coffee Stall",
            "Other Beverages",
            "Drinking Water",
        ]
        public = self.client.get("/api/food-facilities")
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.get_json()["food_facilities"], [])
        payload = {
            "facility_type": "Lunch",
            "start_time": "12:30",
            "end_time": "13:30",
            "items": "Rice and vegetables",
            "availability": "Available",
            "price_status": "Free",
            "charges": "",
            "location": "Main dining hall",
            "published": False,
        }
        rejected = self.client.post(
            "/api/admin/food-facilities",
            json=payload,
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(rejected.status_code, 403)

        with self.app.app_context():
            database = self.app.get_db()
            database.execute(
                "UPDATE users SET is_admin = TRUE WHERE email = ?",
                ("smoke@example.invalid",),
            )
            database.commit()

        missing_csrf = self.client.post("/api/admin/food-facilities", json=payload)
        self.assertEqual(missing_csrf.status_code, 403)
        created = self.client.post(
            "/api/admin/food-facilities",
            json=payload,
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(created.status_code, 201)
        facility_id = created.get_json()["food_facility"]["id"]
        self.assertFalse(created.get_json()["food_facility"]["published"])
        self.assertEqual(self.client.get("/api/food-facilities").get_json()["food_facilities"], [])

        duplicate = self.client.post(
            "/api/admin/food-facilities",
            json=payload,
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(duplicate.status_code, 409)

        updated_payload = {
            **payload,
            "start_time": "13:00",
            "end_time": "14:00",
            "items": "Rice, vegetables, and fruit",
            "published": True,
        }
        updated = self.client.put(
            f"/api/admin/food-facilities/{facility_id}",
            json=updated_payload,
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(
            updated.get_json()["food_facility"]["start_time"],
            "13:00",
        )
        self.assertEqual(
            [
                item["facility_type"]
                for item in self.client.get("/api/food-facilities").get_json()["food_facilities"]
            ],
            ["Lunch"],
        )

        additional_facilities = [
            {
                "facility_type": "Breakfast",
                "start_time": "08:00",
                "end_time": "09:00",
                "items": "Idli and fruit",
                "availability": "Available",
                "price_status": "Free",
                "charges": "",
                "location": "North dining hall",
            },
            {
                "facility_type": "Evening Snacks",
                "start_time": "16:00",
                "end_time": "17:00",
                "items": "Samosa and tea",
                "availability": "Available",
                "price_status": "Free",
                "charges": "",
                "location": "Main dining hall",
            },
            {
                "facility_type": "Dinner",
                "start_time": "19:00",
                "end_time": "20:00",
                "items": "Rice and curry",
                "availability": "Available",
                "price_status": "Free",
                "charges": "",
                "location": "Main dining hall",
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
                "start_time": "",
                "end_time": "",
                "items": "Lemonade - ₹30",
                "availability": "Available",
                "price_status": "Paid",
                "charges": "See item prices",
                "location": "Student plaza",
            },
            {
                "facility_type": "Drinking Water",
                "start_time": "",
                "end_time": "",
                "items": "",
                "availability": "Available",
                "price_status": "Free",
                "charges": "",
                "location": "Library entrance\nInnovation Hub",
            },
        ]
        for facility in additional_facilities:
            response = self.client.post(
                "/api/admin/food-facilities",
                json=facility,
                headers={"X-CSRF-Token": self.csrf},
            )
            self.assertEqual(response.status_code, 201, response.get_json())

        public_facilities = self.client.get("/api/food-facilities").get_json()["food_facilities"]
        public_lunch = next(item for item in public_facilities if item["facility_type"] == "Lunch")
        self.assertEqual(public_lunch["start_time"], "13:00")
        self.assertEqual(public_lunch["items"], "Rice, vegetables, and fruit")
        self.assertEqual(public_lunch["price_status"], "Free")
        self.assertEqual(public_lunch["location"], "Main dining hall")
        self.assertEqual(
            {item["facility_type"] for item in public_facilities},
            set(types),
        )

        with patch("app.get_chatbot_reply") as project_chat:
            answer = self.client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "What is the lunch timing?"}]},
                headers={"X-CSRF-Token": self.csrf},
            )
        self.assertEqual(answer.status_code, 200)
        self.assertEqual(
            answer.get_json()["reply"],
            "Lunch is scheduled from 1:00 PM to 2:00 PM.",
        )
        project_chat.assert_not_called()

        tea_price = self.client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "How much does coffee cost?"}]},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertIn("Coffee Stall is PAID. Price: ₹25.", tea_price.get_json()["reply"])
        breakfast_price = self.client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "Are breakfast and lunch complimentary?"}]},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertIn(
            "Yes! Breakfast is completely free for eligible participants.",
            breakfast_price.get_json()["reply"],
        )
        self.assertIn(
            "Yes! Lunch is completely free for eligible participants.",
            breakfast_price.get_json()["reply"],
        )
        breakfast_time = self.client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "What time is breakfast?"}]},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(
            breakfast_time.get_json()["reply"],
            "Breakfast is scheduled from 8:00 AM to 9:00 AM.",
        )
        snacks = self.client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "What snacks are provided?"}]},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertIn("Evening Snacks items: Samosa and tea.", snacks.get_json()["reply"])
        dinner = self.client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "What time is dinner?"}]},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(
            dinner.get_json()["reply"],
            "Dinner is scheduled from 7:00 PM to 8:00 PM.",
        )
        stalls = self.client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "Are tea and coffee stalls available?"}]},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertIn("Tea Stall availability: Available.", stalls.get_json()["reply"])
        self.assertIn("Coffee Stall availability: Available.", stalls.get_json()["reply"])
        water = self.client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "Is drinking water free?"}]},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(
            water.get_json()["reply"],
            "Yes! Drinking water is available throughout the event. 💧",
        )
        counters = self.client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "Where are the food counters?"}]},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertIn("Main dining hall", counters.get_json()["reply"])
        self.assertIn("Student plaza", counters.get_json()["reply"])

        deleted = self.client.delete(
            f"/api/admin/food-facilities/{facility_id}",
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(deleted.status_code, 200)
        unavailable = self.client.post(
            "/api/chat",
            json={"messages": [{"role": "user", "content": "When is lunch?"}]},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(unavailable.status_code, 200)
        self.assertEqual(
            unavailable.get_json()["reply"],
            "Lunch is scheduled from 1:00 PM to 2:00 PM.",
        )


if __name__ == "__main__":
    unittest.main()
