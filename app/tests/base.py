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
        self.homework_quiz_data = json.load(
            open("app/tests/dummy_data/homework_quiz.json")
        )
        self.timed_quiz_data = json.load(
            open("app/tests/dummy_data/assessment_timed.json")
        )
        self.homework_quiz_id, self.homework_quiz = self.post_and_get_quiz(
            self.homework_quiz_data
        )
        self.timed_quiz_id, self.timed_quiz = self.post_and_get_quiz(
            self.timed_quiz_data
        )

    def post_and_get_quiz(self, quiz_data):
        """helper function to add quiz to db and retrieve it"""
        """We are currently not providing an endpoint for creating questions and the only way to
        create a question is through the quiz endpoint which is why we are using the quiz endpoint
        to create questions and a quiz"""
        response = self.client.post(quizzes.router.prefix + "/", json=quiz_data)
        quiz_id = json.loads(response.content)["id"]
        quiz = self.client.get(quizzes.router.prefix + f"/{quiz_id}").json()

        return quiz_id, quiz


class SessionsBaseTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()

        # create a session (and thus, session answers as well) for the dummy quiz that we have created
        response = self.client.post(
            sessions.router.prefix + "/",
            json={"quiz_id": self.homework_quiz["_id"], "user_id": 1},
        )
        self.homework_session = json.loads(response.content)

        # similar session for timed quiz
        response = self.client.post(
            sessions.router.prefix + "/",
            json={"quiz_id": self.timed_quiz["_id"], "user_id": 1},
        )
        self.timed_quiz_session = json.loads(response.content)
