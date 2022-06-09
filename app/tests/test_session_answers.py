import json
from .base import SessionsBaseTestCase
from ..routers import session_answers


class SessionAnswerTestCase(SessionsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.session_answers = self.session["session_answers"]
        self.session_answer = self.session_answers[0]
        self.session_answer_id = self.session_answer["_id"]

    def test_gets_session_answer_with_valid_id(self):
        response = self.client.get(
            f"{session_answers.router.prefix}/{self.session_answer_id}"
        )
        assert response.status_code == 200
        session_answer = json.loads(response.content)
        for key in ["question_id", "answer", "visited"]:
            assert session_answer[key] == self.session_answer[key]

    def test_update_session_answer_with_only_answer(self):
        new_answer = [0, 1, 2]
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_answer_id}",
            json={"answer": new_answer},
        )
        assert response.status_code == 200
        response = self.client.get(
            f"{session_answers.router.prefix}/{self.session_answer_id}"
        )
        session_answer = json.loads(response.content)

        # ensure that `answer` has been updated
        assert session_answer["answer"] == new_answer

        # ensure that `visited` is not affected
        assert session_answer["visited"] == self.session_answer["visited"]

    def test_update_session_answer_with_only_visited(self):
        new_visited = True
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_answer_id}",
            json={"visited": new_visited},
        )
        assert response.status_code == 200
        response = self.client.get(
            f"{session_answers.router.prefix}/{self.session_answer_id}"
        )
        session_answer = json.loads(response.content)

        # ensure that `visited` has been updated
        assert session_answer["visited"] == new_visited

        # ensure that `answer` is not affected
        assert session_answer["answer"] == self.session_answer["answer"]
