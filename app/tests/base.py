import unittest
import json
import warnings
from fastapi.testclient import TestClient
from mongoengine import connect, disconnect
from main import app
from routers import quizzes, sessions, organizations


def _load_dummy_data(path):
    with open(path, "r", encoding="utf-8") as data_file:
        return json.load(data_file)


class BaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="pkg_resources is deprecated as an API.*",
                category=DeprecationWarning,
            )
            warnings.filterwarnings(
                "ignore",
                message=r"Deprecated call to `pkg_resources.declare_namespace\(.*\)`.*",
                category=DeprecationWarning,
            )
            connect(
                "mongoenginetest",
                host="mongomock://127.0.0.1:8000",
                uuidRepresentation="standard",
            )
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        disconnect()

    def setUp(self):
        # Set up for organizations
        self.organization_data = _load_dummy_data(
            "app/tests/dummy_data/organization.json"
        )
        self.organization_api_key, self.organization = self.post_and_get_organization(
            self.organization_data
        )

        # short homework quiz
        self.short_homework_quiz_data = _load_dummy_data(
            "app/tests/dummy_data/short_homework_quiz.json"
        )
        self.short_homework_quiz_id, self.short_homework_quiz = self.post_and_get_quiz(
            self.short_homework_quiz_data
        )

        # homework quiz
        self.homework_quiz_data = _load_dummy_data(
            "app/tests/dummy_data/homework_quiz.json"
        )
        self.homework_quiz_id, self.homework_quiz = self.post_and_get_quiz(
            self.homework_quiz_data
        )

        # timed quiz
        self.timed_quiz_data = _load_dummy_data(
            "app/tests/dummy_data/assessment_timed.json"
        )
        self.timed_quiz_id, self.timed_quiz = self.post_and_get_quiz(
            self.timed_quiz_data
        )

        # assessment quiz with multiple question sets
        self.multi_qset_quiz_data = _load_dummy_data(
            "app/tests/dummy_data/multiple_question_set_quiz.json"
        )
        self.multi_qset_quiz_id, self.multi_qset_quiz = self.post_and_get_quiz(
            self.multi_qset_quiz_data
        )

        # omr quiz with multiple question sets (same content as above)
        self.multi_qset_omr_data = _load_dummy_data(
            "app/tests/dummy_data/multiple_question_set_omr_quiz.json"
        )
        self.multi_qset_omr_id, self.multi_qset_omr = self.post_and_get_quiz(
            self.multi_qset_omr_data
        )

        # quiz with partial marking
        self.partial_mark_data = _load_dummy_data(
            "app/tests/dummy_data/partial_marking_assessment.json"
        )
        self.partial_mark_quiz_id, self.partial_mark_quiz = self.post_and_get_quiz(
            self.partial_mark_data
        )

        # quiz with matrix matching
        self.matrix_match_data = _load_dummy_data(
            "app/tests/dummy_data/matrix_matching_assessment.json"
        )
        self.matrix_match_quiz_id, self.matrix_match_quiz = self.post_and_get_quiz(
            self.matrix_match_data
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

    def post_and_get_organization(self, organization_data):
        """helper function to add organization to db and retrieve it"""
        response = self.client.post(
            organizations.router.prefix + "/", json=organization_data
        )
        organization = json.loads(response.content)
        organization_api_key = organization["key"]

        return organization_api_key, organization


class SessionsBaseTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()

        # create a session (and thus, session answers as well) for the dummy quizzes that we have created

        # short homework quiz
        response = self.client.post(
            sessions.router.prefix + "/",
            json={"quiz_id": self.short_homework_quiz["_id"], "user_id": 1},
        )
        self.short_homework_quiz_session = json.loads(response.content)

        # assessment quiz with multiple question sets
        response = self.client.post(
            sessions.router.prefix + "/",
            json={"quiz_id": self.multi_qset_quiz["_id"], "user_id": 1},
        )
        self.multi_qset_quiz_session = json.loads(response.content)

        # omr assessment with multiple question sets
        response = self.client.post(
            sessions.router.prefix + "/",
            json={
                "quiz_id": self.multi_qset_omr["_id"],
                "user_id": 1,
                "omr_mode": True,
            },
        )
        self.multi_qset_omr_session = json.loads(response.content)

        # homework quiz
        response = self.client.post(
            sessions.router.prefix + "/",
            json={"quiz_id": self.homework_quiz["_id"], "user_id": 1},
        )
        self.homework_session = json.loads(response.content)

        # timed quiz
        response = self.client.post(
            sessions.router.prefix + "/",
            json={"quiz_id": self.timed_quiz["_id"], "user_id": 1},
        )
        self.timed_quiz_session = json.loads(response.content)
