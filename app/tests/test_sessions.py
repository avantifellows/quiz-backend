from .base import SessionsBaseTestCase


class SessionsTestCase(SessionsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.session_id = self.session["_id"]

    def test_gets_session_answer_with_valid_id(self):
        response = self.client.get(f"/sessions/{self.session_id}")
        assert response.status_code == 200
        session = response.json()
        for key in ["quiz_id", "user_id"]:
            assert session[key] == self.session[key]

    def test_get_question_returns_error_if_id_invalid(self):
        response = self.client.get("/sessions/00")
        assert response.status_code == 404
        response = response.json()
        assert response["detail"] == "session 00 not found"
