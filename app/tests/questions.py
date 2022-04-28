from fastapi.testclient import TestClient
import unittest
import json
from mongoengine import connect, disconnect
from app.main import app

client = TestClient(app)


class QuestionsTestCase(unittest.TestCase):
    question_id = ""
    text = ""

    @classmethod
    def setUpClass(cls):
        connect("mongoenginetest", host="mongomock://127.0.0.1:8000")

    @classmethod
    def tearDownClass(cls):
        disconnect()

    def setUp(self):
        response = client.post(
            "/quiz/",
            json={
                "question_sets": [
                    {
                        "questions": [
                            {
                                "text": "Which grade are you in?",
                                "type": "single-choice",
                                "options": [
                                    {"text": "Option 1"},
                                    {"text": "Option 2"},
                                    {"text": "Option 3"},
                                ],
                                "graded": False,
                            },
                            {
                                "text": "Which grade are you in?",
                                "type": "multi-choice",
                                "image": {
                                    "url": "https://plio-prod-assets.s3.ap-south-1.amazonaws.com/images/afbxudrmbl.png",
                                    "alt_text": "Image",
                                },
                                "options": [
                                    {"text": "Option 1"},
                                    {
                                        "text": "Option 2",
                                        "image": {
                                            "url": "https://plio-prod-assets.s3.ap-south-1.amazonaws.com/images/afbxudrmbl.png"
                                        },
                                    },
                                    {"text": "Option 3"},
                                ],
                                "correct_answer": [0, 2],
                                "graded": True,
                            },
                        ]
                    }
                ],
                "max_marks": 10,
                "num_graded_questions": 1,
                "shuffle": False,
                "num_attempts_allowed": 1,
                "time_limit": None,
                "navigation_mode": "linear",
                "language": "en",
                "metadata": {"quiz_type": "JEE", "subject": "Maths", "grade": "8"},
            },
        )
        res = response.content
        res = json.loads(res)
        self.question_id = res["question_sets"][0]["questions"][0]["_id"]
        self.text = res["question_sets"][0]["questions"][0]["text"]

    def test_get_question_if_id_invalid(self):
        response = client.get("/questions/00")
        assert response.status_code == 404, response.text
        message = response.json()
        assert message["detail"] == "Question 00 not found"

    def test_get_question_if_id_valid(self):
        response = client.get(f"/questions/{self.question_id}")
        question = response.json()
        assert question["text"] == self.text
