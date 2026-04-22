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
        payload = response.json()
        assert payload["success"] is False
        assert payload["message"] == "Validation failed"
        assert "details" in payload

    def test_get_non_existent_quiz_fails(self):
        response = self.client.get("/quiz/non-existent-id")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        payload = response.json()
        assert payload["success"] is False
        assert "message" in payload
        assert "quiz" in payload["message"]

    def test_create_organization_empty_name_fails(self):
        invalid_data = {"name": ""}
        response = self.client.post("/organizations/", json=invalid_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        payload = response.json()
        assert payload["success"] is False
        assert payload["message"] == "Validation failed"
