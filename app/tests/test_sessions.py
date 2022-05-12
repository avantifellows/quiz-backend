import json
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

    def test_update_session(self):
        updated_has_quiz_ended = True
        response = self.client.patch(
            f"/sessions/{self.session_id}",
            json={"has_quiz_ended": updated_has_quiz_ended},
        )
        assert response.status_code == 200
        response = self.client.get(f"/sessions/{self.session_id}")
        session = response.json()

        # ensure that `has_quiz_ended` has been updated
        assert session["has_quiz_ended"] == updated_has_quiz_ended

    def test_create_session_with_invalid_quiz_id(self):
        response = self.client.post("/sessions/", json={"quiz_id": "00", "user_id": 1})
        assert response.status_code == 404
        response = response.json()
        assert response["detail"] == "quiz 00 not found"

    def test_create_session_with_valid_quiz_id(self):
        data = open("app/dummy_data/homework_quiz.json")
        quiz_data = json.load(data)
        response = self.client.post("/quiz/", json=quiz_data)
        quiz = json.loads(response.content)
        response = self.client.post(
            "/sessions/", json={"quiz_id": quiz["_id"], "user_id": 1}
        )
        assert response.status_code == 201
        session = json.loads(response.content)
        assert session["is_first"] is True
        assert len(session["session_answers"]) == len(
            quiz_data["question_sets"][0]["questions"]
        )
        response = self.client.post(
            "/sessions/", json={"quiz_id": quiz["_id"], "user_id": 1}
        )
        assert response.status_code == 201
        session = json.loads(response.content)
        assert session["is_first"] is False
        assert session["has_quiz_ended"] is False
        assert len(session["session_answers"]) == len(
            quiz_data["question_sets"][0]["questions"]
        )
