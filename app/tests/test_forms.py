import copy

from .base import BaseTestCase
from ..routers import forms, quizzes
from settings import Settings


settings = Settings()


class FormTestCase(BaseTestCase):
    def _create_form(self, quiz_data):
        form_data = copy.deepcopy(quiz_data)
        form_data["metadata"] = {"quiz_type": "form"}
        response = self.client.post(quizzes.router.prefix + "/", json=form_data)
        assert response.status_code == 201
        return response.json()["id"]

    def test_form_endpoint_rejects_non_form_quiz(self):
        response = self.client.get(f"{forms.router.prefix}/{self.homework_quiz_id}")

        assert response.status_code == 404
        assert response.json()["detail"] == (f"form {self.homework_quiz_id} not found")

    def test_single_page_mode_restores_trimmed_question_details(self):
        form_id = self._create_form(self.multi_qset_quiz_data)
        default_response = self.client.get(f"{forms.router.prefix}/{form_id}")
        assert default_response.status_code == 200
        trimmed_question = default_response.json()["question_sets"][0]["questions"][
            settings.subset_size
        ]
        assert trimmed_question["text"] is None

        response = self.client.get(
            f"{forms.router.prefix}/{form_id}",
            params={"single_page_mode": True},
        )

        assert response.status_code == 200
        form = response.json()
        assert form["_id"] == form_id
        full_question = next(
            question
            for question in form["question_sets"][0]["questions"]
            if question["_id"] == trimmed_question["_id"]
        )
        assert full_question["text"] is not None

    def test_omr_mode_pads_trimmed_options_to_source_count(self):
        questions = self.multi_qset_omr_data["question_sets"][0]["questions"]
        question_index = next(
            index
            for index, question in enumerate(questions)
            if index >= settings.subset_size and question.get("options")
        )
        expected_option_count = len(questions[question_index]["options"])
        form_id = self._create_form(self.multi_qset_omr_data)

        response = self.client.get(
            f"{forms.router.prefix}/{form_id}",
            params={"omr_mode": True},
        )

        assert response.status_code == 200
        options = response.json()["question_sets"][0]["questions"][question_index][
            "options"
        ]
        assert len(options) == expected_option_count
        assert all(option == {"text": "", "image": None} for option in options)
