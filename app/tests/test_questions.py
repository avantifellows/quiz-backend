from .base import BaseTestCase
from ..routers import questions
from settings import Settings

settings = Settings()


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

    def test_get_questions_for_multiple_question_sets(self):
        # get question set ids
        qset_id_0 = self.multi_qset_quiz["question_sets"][0]["_id"]
        qset_id_1 = self.multi_qset_quiz["question_sets"][1]["_id"]

        # query a subset of questions belonging to each question set id
        for qset_id in [qset_id_0, qset_id_1]:
            response = self.client.get(
                f"{questions.router.prefix}/"
                + f"?question_set_id={qset_id}"
                + f"&skip={settings.subset_size}"
                + f"&limit={settings.subset_size}"
            )

            assert response.status_code == 200
            response = response.json()
            assert isinstance(response, list)
            assert len(response) == settings.subset_size
