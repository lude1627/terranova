from contextlib import closing
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
import json
import os
import tempfile
from threading import Thread
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import database
from backend import main as app
from backend.security import create_session, hash_password, read_session, verify_password


class SecurityTests(unittest.TestCase):
    def test_password_hash_verifies_only_matching_password(self):
        stored = hash_password("UnaClaveLarga123!")
        self.assertTrue(verify_password("UnaClaveLarga123!", stored))
        self.assertFalse(verify_password("otra-clave", stored))

    def test_signed_session_rejects_tampering(self):
        token = create_session(17, "local-test-secret")
        self.assertEqual(read_session(token, "local-test-secret"), 17)
        self.assertIsNone(read_session(token, "different-secret"))
        self.assertIsNone(read_session(token + "x", "local-test-secret"))


class DatabaseTests(unittest.TestCase):
    def test_initialization_creates_schema_and_demo_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "terranova-test.sqlite3"
            with patch.object(database, "DATABASE_PATH", path), patch.dict(
                os.environ,
                {
                    "TERRANOVA_ADMIN_EMAIL": "admin@test.local",
                    "TERRANOVA_ADMIN_PASSWORD": "UnaClaveLarga123!",
                },
            ):
                database.initialize_database()
                with closing(database.connect()) as db:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM plots").fetchone()[0], 15)
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM clients").fetchone()[0], 2)
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 2)
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM payments").fetchone()[0], 3)
                    role = db.execute("SELECT role FROM users WHERE email = ?", ("admin@test.local",)).fetchone()[0]
                    self.assertEqual(role, "Administrador")
                    self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "terranova-api-test.sqlite3"
        self.database_patch = patch.object(database, "DATABASE_PATH", self.database_path)
        self.database_patch.start()
        with patch.dict(
            os.environ,
            {
                "TERRANOVA_ADMIN_EMAIL": "admin@test.local",
                "TERRANOVA_ADMIN_PASSWORD": "UnaClaveLarga123!",
            },
        ):
            database.initialize_database()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.TerranovaHandler)
        self.server_thread = Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.client = build_opener(HTTPCookieProcessor(CookieJar()))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=3)
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def request(self, path, method="GET", data=None):
        body = None if data is None else json.dumps(data).encode("utf-8")
        request = Request(self.base_url + path, data=body, method=method)
        if body is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with self.client.open(request, timeout=5) as response:
                content = response.read()
                return response.status, json.loads(content) if content else None
        except HTTPError as error:
            content = error.read()
            return error.code, json.loads(content) if content else None

    def test_authentication_operations_backup_and_static_page(self):
        status_code, _ = self.request("/api/dashboard")
        self.assertEqual(status_code, 401)

        status_code, user = self.request(
            "/api/auth/login",
            "POST",
            {"email": "admin@test.local", "password": "UnaClaveLarga123!"},
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(user["role"], "Administrador")

        status_code, dashboard = self.request("/api/dashboard")
        self.assertEqual(status_code, 200)
        self.assertEqual(dashboard["total_plots"], 15)

        status_code, backup = self.request("/api/admin/backup")
        self.assertEqual(status_code, 200)
        self.assertEqual(len(backup["sales"]), 2)

        status_code, restored = self.request("/api/admin/restore", "POST", backup)
        self.assertEqual(status_code, 204)
        self.assertIsNone(restored)

        status_code, sales = self.request("/api/sales")
        self.assertEqual(status_code, 200)

        status_code, client = self.request(
            "/api/clients",
            "POST",
            {"name": "Nueva Persona", "document": "99887766"},
        )
        self.assertEqual(status_code, 201)
        self.assertEqual(client["name"], "Nueva Persona")

        status_code, error = self.request(
            "/api/payments",
            "POST",
            {
                "sale_id": sales[0]["id"],
                "date": "2026-11-03",
                "amount": 30_000_000,
                "type": "Abono",
                "method": "Efectivo",
            },
        )
        self.assertEqual(status_code, 422)
        self.assertIn("saldo pendiente", error["detail"])

        with self.client.open(self.base_url + "/", timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("Terranova", response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
