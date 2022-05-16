import unittest
import json
from fastapi.testclient import TestClient
from mongoengine import connect, disconnect
from main import app


class BaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        connect("mongoenginetest", host="mongomock://127.0.0.1:8000")
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        disconnect()

    def setUp(self):
        self.quiz_data = json.load(open("app/tests/dummy_data/homework_quiz.json"))
        # We are currently not providing an endpoint for creating questions and the only way to
        # create a question is through the quiz endpoint which is why we are using the quiz endpoint
        # to create questions and a quiz
        response = self.client.post("/quiz/", json=self.quiz_data)
        self.quiz = json.loads(response.content)


class SessionsBaseTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()

        # create a session (and thus, session answers as well) for the dummy quiz that we have created
        response = self.client.post(
            "/sessions/", json={"quiz_id": self.quiz["_id"], "user_id": 1}
        )
        self.session = json.loads(response.content)
