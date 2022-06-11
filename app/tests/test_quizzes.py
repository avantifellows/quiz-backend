import json
from .base import BaseTestCase
from ..routers import quizzes
from settings import Settings

settings = Settings()


class QuizTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.short_quiz_id = self.short_quiz["_id"]
        self.long_quiz_id = self.long_quiz["_id"]
        self.short_quiz_questions_length = len(
            self.short_quiz_data["question_sets"][0]["questions"]
        )
        self.long_quiz_questions_length = len(
            self.long_quiz_data["question_sets"][0]["questions"]
        )

    def test_create_quiz(self):
        response = self.client.post(
            quizzes.router.prefix + "/", json=self.short_quiz_data
        )
        response = json.loads(response.content)
        id = response["_id"]
        response = self.client.get(f"{quizzes.router.prefix}/{id}")
        assert response.status_code == 200

    def test_get_quiz_if_id_valid(self):
        response = self.client.get(f"{quizzes.router.prefix}/{self.short_quiz_id}")
        assert response.status_code == 200
        response = response.json()
        assert (
            len(response["question_sets"][0]["questions"])
            == self.short_quiz_questions_length
        )

    def test_get_quiz_returns_error_if_id_invalid(self):
        response = self.client.get(f"{quizzes.router.prefix}/00")
        assert response.status_code == 404
        response = response.json()
        assert response["detail"] == "quiz 00 not found"

    def test_created_long_quiz_contains_subsets(self):
        # the created long quiz should contain the same number of questions as the one in the provided input json
        assert self.long_quiz_questions_length == len(
            self.long_quiz["question_sets"][0]["questions"]
        )

        # checking the first subset_size bucket of questions in the quiz. This should contain all the keys/details of a question
        for i in range(0, settings.subset_size):
            question = self.long_quiz["question_sets"][0]["questions"][i]
            # all the following keys should be present in these questions
            assert "text" in question
            assert "type" in question
            assert "instructions" in question
            assert "image" in question
            assert "options" in question
            assert "max_char_limit" in question
            assert "correct_answer" in question
            assert "graded" in question
            assert "marking_scheme" in question
            assert "solution" in question
            assert "metadata" in question
            assert "question_set_id" in question

        # checking the rest of the subset of questions in the quiz. They should only contain some required keys and not all the keys
        for i in range(
            settings.subset_size, len(self.long_quiz["question_sets"][0]["questions"])
        ):
            question = self.long_quiz["question_sets"][0]["questions"][i]

            # these following required keys should be present
            assert "type" in question
            assert "correct_answer" in question
            assert "graded" in question
            assert "question_set_id" in question

            # these following keys should not be present. They will be present in the individual question document, not the quiz document
            assert "text" not in question
            assert "instructions" not in question
            assert "image" not in question
            assert "options" not in question
            assert "max_char_limit" not in question
            assert "marking_scheme" not in question
            assert "solution" not in question
            assert "metadata" not in question
