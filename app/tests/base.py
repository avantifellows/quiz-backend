import os
import unittest
import json
from pathlib import Path

from pymongo import MongoClient
from fastapi.testclient import TestClient
from routers import quizzes, sessions, organizations

# Resolve fixture directory relative to this file so tests work regardless of CWD
_DUMMY_DATA = Path(__file__).resolve().parent / "dummy_data"

# Safe test database name — must never be "quiz" (the production DB)
_TEST_DB_NAME = "quiz_test"


def _guard_db_name(db_name: str) -> None:
    """Refuse to operate if the effective DB name is the production DB."""
    if db_name == "quiz":
        raise RuntimeError(
            "Refusing to run test cleanup against the production 'quiz' database. "
            "Set MONGO_DB_NAME to a safe test database name."
        )


class BaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Force a safe test DB name BEFORE any app imports that read settings
        os.environ["MONGO_DB_NAME"] = _TEST_DB_NAME

        # 2. Create a sync admin client for direct DB operations in tests
        from settings import get_mongo_settings

        mongo_settings = get_mongo_settings()
        cls._admin_client = MongoClient(mongo_settings.mongo_auth_credentials)
        cls._admin_db = cls._admin_client[_TEST_DB_NAME]

        # 3. Import and construct the app (triggers lifespan on TestClient enter)
        from main import create_app

        app = create_app()
        cls._test_client_ctx = TestClient(app)
        cls.client = cls._test_client_ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        # Exit TestClient context — triggers lifespan shutdown (close_db)
        cls._test_client_ctx.__exit__(None, None, None)
        # Close the sync admin client
        cls._admin_client.close()

    @property
    def db(self):
        """Sync admin database handle for direct DB operations in tests."""
        return self.__class__._admin_db

    def setUp(self):
        _guard_db_name(_TEST_DB_NAME)
        # Drop all collections in the test database before each test
        for collection_name in self.db.list_collection_names():
            self.db.drop_collection(collection_name)

        # Set up for organizations
        self.organization_data = json.load(open(_DUMMY_DATA / "organization.json"))
        self.organization_api_key, self.organization = self.post_and_get_organization(
            self.organization_data
        )

        # short homework quiz
        self.short_homework_quiz_data = json.load(
            open(_DUMMY_DATA / "short_homework_quiz.json")
        )
        self.short_homework_quiz_id, self.short_homework_quiz = self.post_and_get_quiz(
            self.short_homework_quiz_data
        )

        # homework quiz
        self.homework_quiz_data = json.load(open(_DUMMY_DATA / "homework_quiz.json"))
        self.homework_quiz_id, self.homework_quiz = self.post_and_get_quiz(
            self.homework_quiz_data
        )

        # timed quiz
        self.timed_quiz_data = json.load(open(_DUMMY_DATA / "assessment_timed.json"))
        self.timed_quiz_id, self.timed_quiz = self.post_and_get_quiz(
            self.timed_quiz_data
        )

        # assessment quiz with multiple question sets
        self.multi_qset_quiz_data = json.load(
            open(_DUMMY_DATA / "multiple_question_set_quiz.json")
        )
        self.multi_qset_quiz_id, self.multi_qset_quiz = self.post_and_get_quiz(
            self.multi_qset_quiz_data
        )

        # omr quiz with multiple question sets (same content as above)
        self.multi_qset_omr_data = json.load(
            open(_DUMMY_DATA / "multiple_question_set_omr_quiz.json")
        )
        self.multi_qset_omr_id, self.multi_qset_omr = self.post_and_get_quiz(
            self.multi_qset_omr_data
        )

        # quiz with partial marking
        self.partial_mark_data = json.load(
            open(_DUMMY_DATA / "partial_marking_assessment.json")
        )
        self.partial_mark_quiz_id, self.partial_mark_quiz = self.post_and_get_quiz(
            self.partial_mark_data
        )

        # quiz with matrix matching
        self.matrix_match_data = json.load(
            open(_DUMMY_DATA / "matrix_matching_assessment.json")
        )
        self.matrix_match_quiz_id, self.matrix_match_quiz = self.post_and_get_quiz(
            self.matrix_match_data
        )

    def tearDown(self):
        _guard_db_name(_TEST_DB_NAME)
        # Clear test database after each test for isolation
        for collection_name in self.db.list_collection_names():
            self.db.drop_collection(collection_name)

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
