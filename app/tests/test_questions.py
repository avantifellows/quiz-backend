from fastapi.testclient import TestClient
import unittest
import json
from mongoengine import connect, disconnect
from main import app


client = TestClient(app)


class QuestionsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        connect("mongoenginetest", host="mongomock://127.0.0.1:8000")

    @classmethod
    def tearDownClass(cls):
        disconnect()

    def setUp(self):
        data = open("app/dummy_data/homework_quiz.json")
        quiz_data = json.load(data)
        # We are currently not providing an endpoint for creating questions and the only way to
        # create a question is through the quiz endpoint which is why we are using the quiz endpoint
        # to create dummy questions
        response = client.post("/quiz/", json=quiz_data)
        response = json.loads(response.content)
        question = response["question_sets"][0]["questions"][0]
        self.question_id, self.text = question["_id"], question["text"]

    def test_get_question_returns_error_if_id_invalid(self):
        response = client.get("/questions/00")
        assert response.status_code == 404
        response = response.json()
        assert response["detail"] == "Question 00 not found"

    def test_get_question_if_id_valid(self):
        response = client.get(f"/questions/{self.question_id}")
        question = response.json()
        assert question["text"] == self.text
