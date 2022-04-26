from fastapi.testclient import TestClient
import unittest
from mongoengine import connect, disconnect
from .main import app

client = TestClient(app)


class test_get_questions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        connect("mongoenginetest", host="mongomock://127.0.0.1:8000")

    @classmethod
    def tearDownClass(cls):
        disconnect()

    def test_get_question_if_id_invalid(self):
        response = client.get("/questions/1a")
        assert response.status_code == 404, response.text
        message = response.json()
        assert message["detail"] == "Question 1a not found"

    def test_get_question_if_id_valid(self):
        response = client.get("/questions/6266381ea5450a1ecaa29480")
        question = response.json()
        assert question["text"] == "Which grade are you in?"
