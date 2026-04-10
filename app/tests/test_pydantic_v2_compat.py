"""
Pydantic v2 compatibility tests (US-010).

Proves the v1-to-v2 migration preserves all API contracts:
- PATCH payloads with null fields
- Batch updates with various answer shapes
- user_id int-to-str coercion
- correct_answer union type variants
- Raw-dict response serialization from all major routes
- Backwards compatibility backfill
- Form endpoint validation and modes
"""

import json
from bson import ObjectId
from .base import BaseTestCase, SessionsBaseTestCase
from routers import quizzes, sessions, session_answers, questions, forms
from database import client as mongo_client
from settings import Settings

settings = Settings()


# ---------------------------------------------------------------------------
# AC-1: Single-item PATCH tests for UpdateSessionAnswer
# ---------------------------------------------------------------------------
class SinglePatchCompatTestCase(SessionsBaseTestCase):
    """Single-item PATCH edge cases for Pydantic v2 UpdateSessionAnswer."""

    def setUp(self):
        super().setUp()
        self.session_id = self.homework_session["_id"]
        self.sa_data = self.homework_session["session_answers"]
        self.pos = 0

    def test_patch_visited_true(self):
        r = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/{self.pos}",
            json={"visited": True},
        )
        assert r.status_code == 200
        sa = self.client.get(
            f"{session_answers.router.prefix}/{self.session_id}/{self.pos}"
        ).json()
        assert sa["visited"] is True
        assert sa["answer"] == self.sa_data[self.pos]["answer"]

    def test_patch_answer_list(self):
        r = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/{self.pos}",
            json={"answer": [0, 1]},
        )
        assert r.status_code == 200
        sa = self.client.get(
            f"{session_answers.router.prefix}/{self.session_id}/{self.pos}"
        ).json()
        assert sa["answer"] == [0, 1]

    def test_patch_empty_payload_rejected(self):
        r = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/{self.pos}",
            json={},
        )
        assert r.status_code == 400

    def test_patch_answer_null_clears_answer(self):
        """PATCH {answer: null} should clear the answer field to None."""
        # Set a non-null answer first
        self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/{self.pos}",
            json={"answer": [0, 1, 2]},
        )
        # Clear it with null
        r = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/{self.pos}",
            json={"answer": None},
        )
        assert r.status_code == 200
        sa = self.client.get(
            f"{session_answers.router.prefix}/{self.session_id}/{self.pos}"
        ).json()
        assert sa["answer"] is None

    def test_patch_time_spent_null_clears_time_spent(self):
        """PATCH {time_spent: null} should clear the time_spent field to None."""
        # Set a non-null time_spent first
        self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/{self.pos}",
            json={"time_spent": 45},
        )
        # Clear it with null
        r = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/{self.pos}",
            json={"time_spent": None},
        )
        assert r.status_code == 200
        sa = self.client.get(
            f"{session_answers.router.prefix}/{self.session_id}/{self.pos}"
        ).json()
        assert sa["time_spent"] is None


# ---------------------------------------------------------------------------
# AC-2: Batch PATCH tests for various answer shapes
# ---------------------------------------------------------------------------
class BatchPatchAnswerShapesTestCase(SessionsBaseTestCase):
    """Batch PATCH with various answer value types (Pydantic v2 union handling)."""

    def setUp(self):
        super().setUp()
        self.session_id = self.homework_session["_id"]
        self.sa_data = self.homework_session["session_answers"]

    def _batch_patch(self, pairs):
        return self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=pairs,
        )

    def _get_answer(self, pos):
        return self.client.get(
            f"{session_answers.router.prefix}/{self.session_id}/{pos}"
        ).json()

    def test_batch_empty_item_payload_rejected(self):
        r = self._batch_patch([[0, {}]])
        assert r.status_code == 400
        assert "Empty payload" in r.json()["detail"]

    def test_batch_scalar_int_answer(self):
        """Answer as a bare integer (e.g., numerical-integer response)."""
        r = self._batch_patch([[0, {"answer": 42}]])
        assert r.status_code == 200
        sa = self._get_answer(0)
        assert sa["answer"] == 42

    def test_batch_scalar_str_answer(self):
        """Answer as a bare string (e.g., subjective response)."""
        r = self._batch_patch([[0, {"answer": "hello world"}]])
        assert r.status_code == 200
        sa = self._get_answer(0)
        assert sa["answer"] == "hello world"

    def test_batch_dict_answer(self):
        """Answer as a dict (e.g., matrix-match response)."""
        answer = {"row1": "A", "row2": "B"}
        r = self._batch_patch([[0, {"answer": answer}]])
        assert r.status_code == 200
        sa = self._get_answer(0)
        assert sa["answer"] == answer

    def test_batch_list_str_answer(self):
        """Answer as a list of strings (e.g., matrix-match list response)."""
        answer = ["A,B", "C,D"]
        r = self._batch_patch([[0, {"answer": answer}]])
        assert r.status_code == 200
        sa = self._get_answer(0)
        assert sa["answer"] == answer

    def test_batch_duplicate_positions_rejected(self):
        r = self._batch_patch([[0, {"answer": [0]}], [0, {"answer": [1]}]])
        assert r.status_code == 400
        assert "Duplicate" in r.json()["detail"]

    def test_batch_negative_position_rejected(self):
        r = self._batch_patch([[-1, {"answer": [0]}]])
        assert r.status_code == 400
        assert "negative" in r.json()["detail"]

    def test_batch_out_of_bounds_position_rejected(self):
        oob = len(self.sa_data) + 1
        r = self._batch_patch([[oob, {"answer": [0]}]])
        assert r.status_code == 400
        assert "out of bounds" in r.json()["detail"]


# ---------------------------------------------------------------------------
# AC-3: POST /sessions — user_id int-to-str coercion
# ---------------------------------------------------------------------------
class SessionUserIdCoercionTestCase(BaseTestCase):
    """Prove user_id integer input is stored and returned as string."""

    def test_create_session_with_int_user_id_returns_string(self):
        """POST /sessions with user_id=123 must return user_id as '123'."""
        r = self.client.post(
            sessions.router.prefix + "/",
            json={"quiz_id": self.homework_quiz["_id"], "user_id": 123},
        )
        assert r.status_code == 201
        session = r.json()
        assert session["user_id"] == "123"
        assert isinstance(session["user_id"], str)

    def test_create_session_with_int_user_id_stored_as_string(self):
        """user_id must be stored as string in MongoDB, not as int."""
        r = self.client.post(
            sessions.router.prefix + "/",
            json={"quiz_id": self.homework_quiz["_id"], "user_id": 456},
        )
        assert r.status_code == 201
        session_id = r.json()["_id"]

        # Verify directly in DB
        db_session = mongo_client.quiz.sessions.find_one({"_id": session_id})
        assert db_session is not None
        assert db_session["user_id"] == "456"
        assert isinstance(db_session["user_id"], str)


# ---------------------------------------------------------------------------
# AC-4: Quiz create/read — correct_answer shapes
# ---------------------------------------------------------------------------
class CorrectAnswerShapesTestCase(BaseTestCase):
    """Prove correct_answer union variants roundtrip through create and read."""

    def _create_quiz_with_answer(self, correct_answer, q_type="numerical-integer"):
        """Helper: create a single-question quiz with the given correct_answer."""
        quiz_data = {
            "question_sets": [
                {
                    "title": "Test Set",
                    "max_questions_allowed_to_attempt": 1,
                    "questions": [
                        {
                            "text": "Test question",
                            "type": q_type,
                            "options": (
                                [{"text": "A"}, {"text": "B"}, {"text": "C"}]
                                if q_type in ("single-choice", "multi-choice")
                                else []
                            ),
                            "correct_answer": correct_answer,
                            "graded": True,
                        }
                    ],
                }
            ],
            "max_marks": 1,
            "num_graded_questions": 1,
            "metadata": {"quiz_type": "assessment"},
        }
        r = self.client.post(quizzes.router.prefix + "/", json=quiz_data)
        assert r.status_code == 201
        quiz_id = r.json()["id"]

        # Read back with include_answers to see correct_answer
        quiz = self.client.get(
            f"{quizzes.router.prefix}/{quiz_id}",
            params={"include_answers": True},
        ).json()
        return quiz["question_sets"][0]["questions"][0]

    def test_correct_answer_float(self):
        q = self._create_quiz_with_answer(23.2, "numerical-float")
        assert q["correct_answer"] == 23.2
        assert isinstance(q["correct_answer"], float)

    def test_correct_answer_integer(self):
        q = self._create_quiz_with_answer(42, "numerical-integer")
        assert q["correct_answer"] == 42
        assert isinstance(q["correct_answer"], int)

    def test_correct_answer_list_int(self):
        q = self._create_quiz_with_answer([0, 2], "multi-choice")
        assert q["correct_answer"] == [0, 2]

    def test_correct_answer_list_str(self):
        """Matrix-match answers are stored as List[str]."""
        q = self._create_quiz_with_answer(["A,B", "C,D"], "matrix-match")
        assert q["correct_answer"] == ["A,B", "C,D"]
        for item in q["correct_answer"]:
            assert isinstance(item, str)


# ---------------------------------------------------------------------------
# AC-5: Raw-dict route response tests
# ---------------------------------------------------------------------------
class RawDictResponseTestCase(SessionsBaseTestCase):
    """Verify raw-dict routes return expected keys through Pydantic v2 response_model."""

    def test_get_quiz_response_keys(self):
        """GET /quiz/{id} returns dict with all expected top-level keys."""
        r = self.client.get(f"{quizzes.router.prefix}/{self.homework_quiz_id}")
        assert r.status_code == 200
        quiz = r.json()
        expected = {
            "_id",
            "question_sets",
            "max_marks",
            "num_graded_questions",
            "shuffle",
            "num_attempts_allowed",
            "navigation_mode",
            "language",
            "metadata",
        }
        assert expected.issubset(set(quiz.keys()))
        assert isinstance(quiz["question_sets"], list)
        assert len(quiz["question_sets"]) > 0

    def test_get_session_response_keys(self):
        """GET /sessions/{id} returns dict with all expected top-level keys."""
        session_id = self.homework_session["_id"]
        r = self.client.get(f"{sessions.router.prefix}/{session_id}")
        assert r.status_code == 200
        session = r.json()
        expected = {
            "_id",
            "user_id",
            "quiz_id",
            "is_first",
            "session_answers",
            "has_quiz_ended",
            "question_order",
            "events",
        }
        assert expected.issubset(set(session.keys()))
        assert isinstance(session["session_answers"], list)
        assert isinstance(session["question_order"], list)

    def test_get_question_response_keys(self):
        """GET /questions/{id} returns dict with all expected keys."""
        # Get a question_id from the homework quiz
        q_id = self.homework_quiz["question_sets"][0]["questions"][0]["_id"]
        r = self.client.get(f"{questions.router.prefix}/{q_id}")
        assert r.status_code == 200
        q = r.json()
        expected = {"_id", "text", "type", "graded", "question_set_id"}
        assert expected.issubset(set(q.keys()))

    def test_get_form_response_keys(self):
        """GET /form/{id} returns dict with expected keys for a form quiz."""
        # Create a form
        form_data = json.load(open("app/tests/dummy_data/form_questionnaire.json"))
        r = self.client.post(quizzes.router.prefix + "/", json=form_data)
        assert r.status_code == 201
        form_id = r.json()["id"]

        r = self.client.get(f"{forms.router.prefix}/{form_id}")
        assert r.status_code == 200
        form = r.json()
        expected = {
            "_id",
            "question_sets",
            "max_marks",
            "num_graded_questions",
            "metadata",
        }
        assert expected.issubset(set(form.keys()))
        assert form["metadata"]["quiz_type"] == "form"


# ---------------------------------------------------------------------------
# AC-6: Sparse-response test (trimmed questions have placeholder keys)
# ---------------------------------------------------------------------------
class SparseQuizResponseTestCase(BaseTestCase):
    """Trimmed questions beyond subset_size keep placeholder keys with correct defaults."""

    def test_trimmed_questions_have_none_and_empty_list_placeholders(self):
        """Questions beyond subset_size have None for optional keys and [] for list keys."""
        quiz = self.multi_qset_quiz
        for qset in quiz["question_sets"]:
            for i, q in enumerate(qset["questions"]):
                if i >= settings.subset_size:
                    # Optional text-like keys should be None
                    assert q.get("text") is None
                    assert q.get("instructions") is None
                    assert q.get("image") is None
                    assert q.get("max_char_limit") is None
                    assert q.get("marking_scheme") is None
                    assert q.get("metadata") is None
                    # List keys should be empty lists
                    assert q.get("solution") == []
                    # correct_answer is sanitized to None by base endpoint
                    assert q.get("correct_answer") is None


# ---------------------------------------------------------------------------
# AC-7: Legacy stored-quiz test (update_quiz_for_backwards_compatibility)
# ---------------------------------------------------------------------------
class BackwardsCompatibilityTestCase(BaseTestCase):
    """Prove update_quiz_for_backwards_compatibility() backfills missing fields."""

    def test_legacy_quiz_without_max_questions_gets_backfilled(self):
        """
        A quiz stored without max_questions_allowed_to_attempt should be
        backfilled on read via update_quiz_for_backwards_compatibility().
        """
        # Use valid ObjectId strings for all IDs
        quiz_id = str(ObjectId())
        qset_id = str(ObjectId())
        q1_id = str(ObjectId())
        q2_id = str(ObjectId())

        legacy_quiz = {
            "_id": quiz_id,
            "title": "Legacy Quiz",
            "question_sets": [
                {
                    "_id": qset_id,
                    "questions": [
                        {
                            "_id": q1_id,
                            "text": "Q1",
                            "type": "single-choice",
                            "options": [{"text": "A"}, {"text": "B"}],
                            "correct_answer": [0],
                            "graded": True,
                            "question_set_id": qset_id,
                            "marking_scheme": {"correct": 1, "wrong": 0, "skipped": 0},
                        },
                        {
                            "_id": q2_id,
                            "text": "Q2",
                            "type": "single-choice",
                            "options": [{"text": "X"}, {"text": "Y"}],
                            "correct_answer": [1],
                            "graded": True,
                            "question_set_id": qset_id,
                            "marking_scheme": {"correct": 1, "wrong": 0, "skipped": 0},
                        },
                    ],
                    # NOTE: no max_questions_allowed_to_attempt, no title, no marking_scheme
                }
            ],
            "max_marks": 2,
            "num_graded_questions": 2,
            "metadata": {"quiz_type": "assessment"},
        }
        # Insert questions and quiz directly
        mongo_client.quiz.questions.insert_many(
            legacy_quiz["question_sets"][0]["questions"]
        )
        mongo_client.quiz.quizzes.insert_one(legacy_quiz)

        # GET /quiz should trigger backwards compatibility backfill
        r = self.client.get(f"{quizzes.router.prefix}/{quiz_id}")
        assert r.status_code == 200
        quiz = r.json()

        qset = quiz["question_sets"][0]
        # Backfilled fields
        assert qset["max_questions_allowed_to_attempt"] == 2  # len(questions)
        assert qset["title"] == "Section A"
        assert qset["marking_scheme"] is not None
        assert "correct" in qset["marking_scheme"]

    def test_legacy_quiz_without_marking_scheme_gets_default(self):
        """
        A question set with no marking_scheme (and questions with no marking_scheme)
        gets the default {correct: 1, wrong: 0, skipped: 0}.
        """
        quiz_id = str(ObjectId())
        qset_id = str(ObjectId())
        q1_id = str(ObjectId())

        legacy_quiz = {
            "_id": quiz_id,
            "title": "No MS Quiz",
            "question_sets": [
                {
                    "_id": qset_id,
                    "questions": [
                        {
                            "_id": q1_id,
                            "text": "Q1",
                            "type": "single-choice",
                            "options": [{"text": "A"}],
                            "correct_answer": [0],
                            "graded": True,
                            "question_set_id": qset_id,
                            "marking_scheme": None,
                        },
                    ],
                }
            ],
            "max_marks": 1,
            "num_graded_questions": 1,
            "metadata": {"quiz_type": "assessment"},
        }
        mongo_client.quiz.questions.insert_many(
            legacy_quiz["question_sets"][0]["questions"]
        )
        mongo_client.quiz.quizzes.insert_one(legacy_quiz)

        r = self.client.get(f"{quizzes.router.prefix}/{quiz_id}")
        assert r.status_code == 200
        qset = r.json()["question_sets"][0]
        ms = qset["marking_scheme"]
        assert ms is not None
        assert ms["correct"] == 1
        assert ms["wrong"] == 0
        assert ms["skipped"] == 0


# ---------------------------------------------------------------------------
# AC-8: Form endpoint tests
# ---------------------------------------------------------------------------
class FormEndpointTestCase(BaseTestCase):
    """Form endpoint validation: non-form rejection, single_page_mode, OMR padding."""

    def _create_form(self):
        """Create a form quiz and return its ID."""
        form_data = json.load(open("app/tests/dummy_data/form_questionnaire.json"))
        r = self.client.post(quizzes.router.prefix + "/", json=form_data)
        assert r.status_code == 201
        return r.json()["id"]

    def test_form_endpoint_rejects_non_form_quiz(self):
        """GET /form/{id} with a homework quiz returns 404."""
        r = self.client.get(f"{forms.router.prefix}/{self.homework_quiz_id}")
        assert r.status_code == 404
        assert "form" in r.json()["detail"]

    def test_quiz_endpoint_rejects_form(self):
        """GET /quiz/{id} with a form quiz returns 404."""
        form_id = self._create_form()
        r = self.client.get(f"{quizzes.router.prefix}/{form_id}")
        assert r.status_code == 404

    def test_form_endpoint_returns_form_successfully(self):
        """GET /form/{id} with a form quiz returns 200."""
        form_id = self._create_form()
        r = self.client.get(f"{forms.router.prefix}/{form_id}")
        assert r.status_code == 200
        form = r.json()
        assert form["metadata"]["quiz_type"] == "form"

    def test_form_single_page_mode_returns_all_questions_with_full_details(self):
        """GET /form/{id}?single_page_mode=true returns all questions with text."""
        form_id = self._create_form()
        r = self.client.get(
            f"{forms.router.prefix}/{form_id}",
            params={"single_page_mode": True},
        )
        assert r.status_code == 200
        form = r.json()
        for qset in form["question_sets"]:
            for q in qset["questions"]:
                assert q.get("text") is not None
                assert q["text"] != ""

    def test_form_omr_mode_pads_options_for_trimmed_questions(self):
        """
        GET /form/{id}?omr_mode=true pads option counts for questions
        beyond subset_size (if the form has enough questions).
        """
        # The form_questionnaire has 8 questions, subset_size is typically 10,
        # so all are in the detailed bucket. Create a form with quiz_type=omr
        # to trigger the OMR padding code path on a quiz with >subset_size questions.
        omr_data = json.load(
            open("app/tests/dummy_data/multiple_question_set_omr_quiz.json")
        )
        # Override to make it a form+omr hybrid for this test
        omr_data["metadata"] = {"quiz_type": "form"}
        r = self.client.post(quizzes.router.prefix + "/", json=omr_data)
        assert r.status_code == 201
        form_id = r.json()["id"]

        r = self.client.get(
            f"{forms.router.prefix}/{form_id}",
            params={"omr_mode": True},
        )
        assert r.status_code == 200
        form = r.json()
        # Verify questions beyond subset_size have padded options
        for qset in form["question_sets"]:
            for i, q in enumerate(qset["questions"]):
                if i >= settings.subset_size:
                    # Padded options should have text and image keys
                    if len(q.get("options", [])) > 0:
                        for opt in q["options"]:
                            assert "text" in opt
                            assert "image" in opt

    def test_form_not_found_returns_404(self):
        """GET /form/{id} with nonexistent ID returns 404."""
        r = self.client.get(f"{forms.router.prefix}/nonexistent-form-id")
        assert r.status_code == 404
