import json
from .base import SessionsBaseTestCase
from ..routers import quizzes, sessions, session_answers


class SessionsTestCase(SessionsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.session_id = self.session["_id"]

    def test_gets_session_with_valid_id(self):
        response = self.client.get(f"{sessions.router.prefix}/{self.session_id}")
        assert response.status_code == 200
        session = response.json()
        for key in ["quiz_id", "user_id"]:
            assert session[key] == self.session[key]

    def test_get_session_returns_error_if_id_invalid(self):
        response = self.client.get(f"{sessions.router.prefix}/00")
        assert response.status_code == 404
        response = response.json()
        assert response["detail"] == "session 00 not found"

    def test_update_session(self):
        updated_has_quiz_ended = True
        response = self.client.patch(
            f"{sessions.router.prefix}/{self.session_id}",
            json={"has_quiz_ended": updated_has_quiz_ended},
        )
        assert response.status_code == 200
        response = self.client.get(f"{sessions.router.prefix}/{self.session_id}")
        session = response.json()

        # ensure that `has_quiz_ended` has been updated
        assert session["has_quiz_ended"] == updated_has_quiz_ended

    def test_create_session_with_invalid_quiz_id(self):
        response = self.client.post(
            sessions.router.prefix + "/", json={"quiz_id": "00", "user_id": 1}
        )
        assert response.status_code == 404
        response = response.json()
        assert response["detail"] == "quiz 00 not found"

    def test_create_session_with_valid_quiz_id_and_first_session(self):
        data = open("app/tests/dummy_data/homework_quiz.json")
        quiz_data = json.load(data)
        response = self.client.post(quizzes.router.prefix + "/", json=quiz_data)
        quiz = json.loads(response.content)
        response = self.client.post(
            sessions.router.prefix + "/", json={"quiz_id": quiz["_id"], "user_id": 1}
        )
        assert response.status_code == 201
        session = json.loads(response.content)
        assert session["is_first"] is True
        assert len(session["session_answers"]) == len(
            quiz_data["question_sets"][0]["questions"]
        )

    def test_create_session_with_valid_quiz_id_and_previous_session(self):
        self.session_answers = self.session["session_answers"]
        self.session_answer = self.session_answers[0]
        self.session_answer_id = self.session_answer["_id"]
        new_answer = [0, 1, 2]
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_answer_id}",
            json={"answer": new_answer},
        )
        response = self.client.post(
            sessions.router.prefix + "/",
            json={
                "quiz_id": self.session["quiz_id"],
                "user_id": self.session["user_id"],
            },
        )
        assert response.status_code == 201
        session = json.loads(response.content)
        assert session["is_first"] is False
        assert session["has_quiz_ended"] is False
        assert session["session_answers"][0]["answer"] == new_answer
