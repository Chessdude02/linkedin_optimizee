"""Direct unit tests for the CSRF helpers, against a minimal Flask app
rather than the full dashboard (test_dashboard.py exercises it through
the real routes; this isolates the mechanism itself)."""
import os
import unittest

os.environ.setdefault("DASHBOARD_SECRET_KEY", "test-secret-key-not-for-real-use")

from flask import Flask, session  # noqa: E402

from dashboard.csrf import csrf_protect, get_csrf_token  # noqa: E402


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret-key-not-for-real-use"

    @app.route("/token")
    def token():
        return get_csrf_token()

    @app.route("/protected", methods=["POST"])
    @csrf_protect
    def protected():
        return "ok"

    return app


class TestCsrf(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()
        self.client = self.app.test_client()

    def test_token_is_stable_within_a_session(self):
        first = self.client.get("/token").get_data(as_text=True)
        second = self.client.get("/token").get_data(as_text=True)
        self.assertEqual(first, second)

    def test_post_without_token_is_rejected(self):
        resp = self.client.post("/protected")
        self.assertEqual(resp.status_code, 403)

    def test_post_with_wrong_token_is_rejected(self):
        self.client.get("/token")
        resp = self.client.post("/protected", data={"csrf_token": "totally-wrong-token"})
        self.assertEqual(resp.status_code, 403)

    def test_post_with_correct_token_succeeds(self):
        token = self.client.get("/token").get_data(as_text=True)
        resp = self.client.post("/protected", data={"csrf_token": token})
        self.assertEqual(resp.status_code, 200)

    def test_token_differs_across_separate_sessions(self):
        client_a = self.app.test_client()
        client_b = self.app.test_client()
        token_a = client_a.get("/token").get_data(as_text=True)
        token_b = client_b.get("/token").get_data(as_text=True)
        self.assertNotEqual(token_a, token_b)

        # A token from session A must not validate against session B.
        resp = client_b.post("/protected", data={"csrf_token": token_a})
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
