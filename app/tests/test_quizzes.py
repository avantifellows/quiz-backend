import json
from .base import BaseTestCase
from ..routers import quizzes


class QuizTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.id = self.quiz["_id"]
        self.length = len(self.quiz_data["question_sets"][0]["questions"])

    def test_setup_quizId_and_quiz(self):
        assert self.quiz_id == self.quiz["_id"]

    def test_create_quiz(self):
        response = self.client.post(quizzes.router.prefix + "/", json=self.quiz_data)
        response = json.loads(response.content)
        id = response["quiz_id"]
        response = self.client.get(f"{quizzes.router.prefix}/{id}")
        assert response.status_code == 200

    def test_get_question_if_id_valid(self):
        response = self.client.get(f"{quizzes.router.prefix}/{self.id}")
        assert response.status_code == 200
        response = response.json()
        assert len(response["question_sets"][0]["questions"]) == self.length

    def test_get_quiz_returns_error_if_id_invalid(self):
        response = self.client.get(f"{quizzes.router.prefix}/00")
        assert response.status_code == 404
        response = response.json()
        assert response["detail"] == "quiz 00 not found"
