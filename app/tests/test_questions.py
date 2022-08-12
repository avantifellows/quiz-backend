from .base import BaseTestCase


class QuestionsTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        question = self.homework_quiz["question_sets"][0]["questions"][0]
        self.question_id, self.text = question["_id"], question["text"]

    def test_get_question_returns_error_if_id_invalid(self):
        response = self.client.get("/questions/00")
        assert response.status_code == 404
        response = response.json()
        assert response["detail"] == "Question 00 not found"

    def test_get_question_if_id_valid(self):
        response = self.client.get(f"/questions/{self.question_id}")
        question = response.json()
        assert question["text"] == self.text
