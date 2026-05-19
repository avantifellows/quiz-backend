from .base import BaseTestCase
from fastapi import status
import json

class ValidationTestCase(BaseTestCase):
    def test_create_quiz_empty_title_fails(self):
        # Using a copy of valid data but with empty title
        invalid_data = self.short_homework_quiz_data.copy()
        invalid_data["title"] = ""
        response = self.client.post("/quiz/", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_quiz_empty_question_sets_fails(self):
        invalid_data = self.short_homework_quiz_data.copy()
        invalid_data["question_sets"] = []
        response = self.client.post("/quiz/", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_quiz_zero_marks_fails(self):
        invalid_data = self.short_homework_quiz_data.copy()
        invalid_data["max_marks"] = 0
        response = self.client.post("/quiz/", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_organization_empty_name_fails(self):
        invalid_data = {"name": ""}
        response = self.client.post("/organizations/", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_create_question_empty_text_fails(self):
        # We create questions via the quiz endpoint
        invalid_data = self.short_homework_quiz_data.copy()
        # Deep copy the question set to modify question text
        invalid_data["question_sets"] = [
            {
                "title": "Set 1",
                "max_questions_allowed_to_attempt": 1,
                "questions": [
                    {
                        "text": "", # Invalid empty text
                        "type": "single-choice",
                        "options": [{"text": "Opt 1"}],
                        "graded": True
                    }
                ]
            }
        ]
        response = self.client.post("/quiz/", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
