import unittest
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient
from pymongo.errors import OperationFailure

from main import app
from database import client as mongo_client


class _DummySession:
    def __init__(self, on_abort):
        self._on_abort = on_abort
        self.aborted = False
        self.committed = False
        self.ended = False

    def start_transaction(self):
        return None

    def commit_transaction(self):
        self.committed = True

    def abort_transaction(self):
        self.aborted = True
        self._on_abort()

    def end_session(self):
        self.ended = True


class QuizCreationAtomicTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, raise_server_exceptions=False)

    def test_create_quiz_rolls_back_when_quiz_insert_fails(self):
        quiz_title = f"atomic-rollback-{uuid4()}"
        payload = {
            "title": quiz_title,
            "question_sets": [
                {
                    "title": "Section A",
                    "max_questions_allowed_to_attempt": 1,
                    "questions": [
                        {
                            "text": "Sample question",
                            "type": "single-choice",
                            "options": [{"text": "A"}, {"text": "B"}],
                            "correct_answer": [0],
                            "graded": True,
                        }
                    ],
                }
            ],
            "max_marks": 1,
            "num_graded_questions": 1,
            "metadata": {"quiz_type": "homework"},
        }

        inserted_question_ids = []
        original_insert_many = mongo_client.quiz.questions.insert_many
        original_aggregate = mongo_client.quiz.questions.aggregate

        def cleanup_inserted_questions():
            if inserted_question_ids:
                mongo_client.quiz.questions.delete_many(
                    {"_id": {"$in": inserted_question_ids}}
                )

        dummy_session = _DummySession(on_abort=cleanup_inserted_questions)

        def insert_many_with_tracking(documents, session=None):
            assert session is dummy_session
            result = original_insert_many(documents, session=session)
            inserted_question_ids.extend(result.inserted_ids)
            return result

        def aggregate_without_session(pipeline, session=None):
            assert session is dummy_session
            return original_aggregate(pipeline, session=session)

        def fail_quiz_insert(document, session=None):
            assert session is dummy_session
            raise RuntimeError("Simulated failure after question insert")

        with patch.object(
            mongo_client, "start_session", return_value=dummy_session
        ), patch.object(
            mongo_client.quiz.questions,
            "insert_many",
            side_effect=insert_many_with_tracking,
        ), patch.object(
            mongo_client.quiz.questions,
            "aggregate",
            side_effect=aggregate_without_session,
        ), patch.object(
            mongo_client.quiz.quizzes,
            "insert_one",
            side_effect=fail_quiz_insert,
        ):
            response = self.client.post("/quiz/", json=payload)

        assert response.status_code == 500
        assert dummy_session.aborted is True
        assert dummy_session.committed is False
        assert dummy_session.ended is True
        assert (
            mongo_client.quiz.questions.count_documents(
                {"_id": {"$in": inserted_question_ids}}
            )
            == 0
        )
        assert mongo_client.quiz.quizzes.count_documents({"title": quiz_title}) == 0

    def test_non_transaction_fallback_cleans_partial_writes_when_quiz_insert_fails(
        self,
    ):
        quiz_title = f"atomic-fallback-cleanup-{uuid4()}"
        unique_question_text = f"sample-question-{uuid4()}"
        payload = {
            "title": quiz_title,
            "question_sets": [
                {
                    "title": "Section A",
                    "max_questions_allowed_to_attempt": 1,
                    "questions": [
                        {
                            "text": unique_question_text,
                            "type": "single-choice",
                            "options": [{"text": "A"}, {"text": "B"}],
                            "correct_answer": [0],
                            "graded": True,
                        }
                    ],
                }
            ],
            "max_marks": 1,
            "num_graded_questions": 1,
            "metadata": {"quiz_type": "homework"},
        }

        original_insert_many = mongo_client.quiz.questions.insert_many
        quizzes_collection_cls = type(mongo_client.quiz.quizzes)
        original_insert_one = quizzes_collection_cls.insert_one

        def insert_many_tx_then_non_tx(documents, session=None):
            if session is not None:
                raise OperationFailure(
                    "Transaction numbers are only allowed on a replica set member or mongos",
                    code=20,
                )
            return original_insert_many(documents)

        def fail_non_transaction_insert_one(self, document, *args, **kwargs):
            if kwargs.get("session") is None:
                raise RuntimeError(
                    "Simulated failure after non-transaction question insert"
                )
            return original_insert_one(self, document, *args, **kwargs)

        with patch.object(
            mongo_client.quiz.questions,
            "insert_many",
            side_effect=insert_many_tx_then_non_tx,
        ), patch.object(
            quizzes_collection_cls,
            "insert_one",
            new=fail_non_transaction_insert_one,
        ):
            response = self.client.post("/quiz/", json=payload)

        assert response.status_code == 500
        assert mongo_client.quiz.quizzes.count_documents({"title": quiz_title}) == 0

        orphaned_questions = list(
            mongo_client.quiz.questions.find({"question_set_id": {"$exists": True}})
        )
        assert not any(
            q.get("text") == unique_question_text for q in orphaned_questions
        )
