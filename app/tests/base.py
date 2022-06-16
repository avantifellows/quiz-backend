import unittest
import json
from fastapi.testclient import TestClient
from mongoengine import connect, disconnect
from main import app
from routers import quizzes, sessions


class BaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        connect("mongoenginetest", host="mongomock://127.0.0.1:8000")
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        disconnect()

    def setUp(self):
        self.short_quiz_data = json.load(
            open("app/tests/dummy_data/short_homework_quiz.json")
        )
        self.long_quiz_data = json.load(
            open("app/tests/dummy_data/long_assessment_quiz.json")
        )

        # We are currently not providing an endpoint for creating questions and the only way to
        # create a question is through the quiz endpoint which is why we are using the quiz endpoint
        # to create questions and a quiz
        response = self.client.post(
            quizzes.router.prefix + "/", json=self.short_quiz_data
        )
        self.short_quiz = json.loads(response.content)

        response = self.client.post(
            quizzes.router.prefix + "/", json=self.long_quiz_data
        )
        self.long_quiz = json.loads(response.content)


class SessionsBaseTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()

        # create a session (and thus, session answers as well) for the dummy quizzes that we have created
        response = self.client.post(
            sessions.router.prefix + "/",
            json={"quiz_id": self.short_quiz["_id"], "user_id": 1},
        )
        self.session_short_quiz = json.loads(response.content)

        response = self.client.post(
            sessions.router.prefix + "/",
            json={"quiz_id": self.long_quiz["_id"], "user_id": 1},
        )
        self.session_long_quiz = json.loads(response.content)
