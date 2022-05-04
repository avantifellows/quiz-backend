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

    def test_to_create_quiz(self):
        data = open("app/dummy_data/homework_quiz.json")
        quiz_data = json.load(data)
        response = client.post("/quiz/", json=quiz_data)
        quiz_data = json.loads(response.content)
        assert response.status_code == 201

    def test_get_quiz_returns_error_if_id_invalid(self):
        response = client.get("/quiz/00")
        assert response.status_code == 404
        response = response.json()
        assert response["detail"] == "quiz 00 not found"

    def test_get_question_if_id_valid(self):
        id = self.quiz_data["_id"]
        response = client.get(f"/quiz/{id}")
        question = response.json()
        assert question == self.quiz_data
