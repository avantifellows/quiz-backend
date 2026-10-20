"""Tests for the conditional-display (display_condition) rule on the backend:
`_compute_form_question_visibility` (the single visibility evaluator) and its use in
`_get_incomplete_required_form_positions` (pure functions — no MongoDB needed), plus the
POST /quiz creation checks (API, real test MongoDB)."""

import json
import unittest
from copy import deepcopy
from pathlib import Path

from routers.sessions import (
    _answer_option_indices,
    _compute_form_question_visibility,
    _get_incomplete_required_form_positions,
)

from .base import BaseTestCase

_DUMMY_DATA = Path(__file__).resolve().parent / "dummy_data"


def _q(qtype="single-choice", display_condition=None, required=None):
    question = {"type": qtype}
    if display_condition is not None:
        question["display_condition"] = display_condition
    if required is not None:
        question["required"] = required
    return question


def _cond(source_position, option_indices):
    return {"source_position": source_position, "option_indices": option_indices}


def _quiz(*questions):
    """Wrap a flat list of questions into a one-set quiz doc."""
    return {"question_sets": [{"questions": list(questions)}]}


def _session(*answers):
    return {"session_answers": [{"answer": answer} for answer in answers]}


class AnswerOptionIndicesTests(unittest.TestCase):
    def test_list_answer_returns_int_indices(self):
        self.assertEqual(_answer_option_indices([0, 2]), [0, 2])

    def test_non_list_shapes_contribute_nothing(self):
        # matrix dict, numerical, string, None cannot drive a v1 condition
        self.assertEqual(_answer_option_indices({"row": 1}), [])
        self.assertEqual(_answer_option_indices(3), [])
        self.assertEqual(_answer_option_indices("text"), [])
        self.assertEqual(_answer_option_indices(None), [])


class VisibilityTests(unittest.TestCase):
    def test_no_conditions_all_visible(self):
        questions = [_q(), _q(), _q()]
        self.assertEqual(
            _compute_form_question_visibility(questions, []),
            [True, True, True],
        )

    def test_dependent_shown_when_trigger_option_selected(self):
        questions = [_q(), _q(display_condition=_cond(0, [0]))]
        answers = [{"answer": [0]}, {"answer": None}]
        self.assertEqual(
            _compute_form_question_visibility(questions, answers),
            [True, True],
        )

    def test_dependent_hidden_when_trigger_option_not_selected(self):
        questions = [_q(), _q(display_condition=_cond(0, [0]))]
        answers = [{"answer": [1]}, {"answer": None}]
        self.assertEqual(
            _compute_form_question_visibility(questions, answers),
            [True, False],
        )

    def test_multi_choice_intersection_shows_dependent(self):
        questions = [_q("multi-choice"), _q(display_condition=_cond(0, [2]))]
        answers = [{"answer": [1, 2]}, {"answer": None}]
        self.assertEqual(
            _compute_form_question_visibility(questions, answers),
            [True, True],
        )

    def test_one_trigger_reveals_multiple_dependents(self):
        questions = [
            _q(),
            _q(display_condition=_cond(0, [0])),
            _q(display_condition=_cond(0, [0])),
        ]
        answers = [{"answer": [0]}, {"answer": None}, {"answer": None}]
        self.assertEqual(
            _compute_form_question_visibility(questions, answers),
            [True, True, True],
        )

    def test_visibility_is_transitive(self):
        # q1 hidden (trigger q0 not matched) ⇒ q2 depending on q1 is also hidden,
        # even though q2's own condition on q1 would match if q1 were shown.
        questions = [
            _q(),
            _q(display_condition=_cond(0, [0])),
            _q(display_condition=_cond(1, [0])),
        ]
        answers = [{"answer": [1]}, {"answer": [0]}, {"answer": [0]}]
        self.assertEqual(
            _compute_form_question_visibility(questions, answers),
            [True, False, False],
        )

    def test_forward_or_out_of_range_source_is_hidden(self):
        # source_position points at the dependent itself / a later question / nonsense
        questions = [
            _q(display_condition=_cond(0, [0])),  # self-reference
            _q(display_condition=_cond(5, [0])),  # out of range
            _q(display_condition=_cond(None, [0])),  # missing
        ]
        self.assertEqual(
            _compute_form_question_visibility(questions, [{"answer": [0]}]),
            [False, False, False],
        )


class IncompleteRequiredPositionsTests(unittest.TestCase):
    def test_hidden_required_question_is_not_incomplete(self):
        # q1 is hidden (trigger not matched) so its null answer must NOT block submit.
        quiz = _quiz(_q(), _q("subjective", display_condition=_cond(0, [0])))
        session = _session([1], None)
        self.assertEqual(_get_incomplete_required_form_positions(quiz, session), [])

    def test_visible_unanswered_dependent_is_incomplete(self):
        # trigger matched ⇒ dependent visible ⇒ its empty answer blocks submit.
        quiz = _quiz(_q(), _q("subjective", display_condition=_cond(0, [0])))
        session = _session([0], None)
        self.assertEqual(_get_incomplete_required_form_positions(quiz, session), [1])

    def test_visible_answered_dependent_is_complete(self):
        quiz = _quiz(_q(), _q("subjective", display_condition=_cond(0, [0])))
        session = _session([0], "because reasons")
        self.assertEqual(_get_incomplete_required_form_positions(quiz, session), [])

    def test_unanswered_trigger_itself_is_incomplete(self):
        quiz = _quiz(_q(), _q("subjective", display_condition=_cond(0, [0])))
        session = _session(None, None)
        # trigger (0) is unanswered ⇒ incomplete; dependent (1) hidden ⇒ skipped.
        self.assertEqual(_get_incomplete_required_form_positions(quiz, session), [0])


class RequiredFlagWithDisplayConditionTests(unittest.TestCase):
    """Per-question `required` (False = opt-out of require_all_questions) combined with
    display_condition: a position is skipped if it is hidden OR required is False."""

    def test_optional_question_is_not_incomplete(self):
        quiz = _quiz(_q(), _q("subjective", required=False))
        session = _session([0], None)
        self.assertEqual(_get_incomplete_required_form_positions(quiz, session), [])

    def test_explicit_required_true_is_enforced(self):
        quiz = _quiz(_q(), _q("subjective", required=True))
        session = _session([0], None)
        self.assertEqual(_get_incomplete_required_form_positions(quiz, session), [1])

    def test_visible_optional_dependent_is_not_incomplete(self):
        # dependent is shown (trigger matched) but opted out ⇒ empty answer is fine.
        quiz = _quiz(
            _q(),
            _q("subjective", display_condition=_cond(0, [0]), required=False),
        )
        session = _session([0], None)
        self.assertEqual(_get_incomplete_required_form_positions(quiz, session), [])

    def test_optional_trigger_still_drives_dependent_visibility(self):
        # q0 is optional; q1 (required) depends on it. Skipping q0 for completeness must
        # not skip it for visibility.
        quiz = _quiz(
            _q(required=False),
            _q("subjective", display_condition=_cond(0, [0])),
        )
        # q0 unanswered ⇒ q1 hidden ⇒ nothing incomplete
        self.assertEqual(
            _get_incomplete_required_form_positions(quiz, _session(None, None)), []
        )
        # q0 picks the trigger option ⇒ q1 visible + required + empty ⇒ incomplete
        self.assertEqual(
            _get_incomplete_required_form_positions(quiz, _session([0], None)), [1]
        )

    def test_mixed_form_skips_hidden_and_optional_only(self):
        quiz = _quiz(
            _q(),  # 0 trigger, answered "no"
            _q("subjective", display_condition=_cond(0, [0])),  # 1 hidden
            _q("subjective", required=False),  # 2 optional, unanswered
            _q("subjective"),  # 3 required, unanswered
            _q("subjective", display_condition=_cond(0, [1])),  # 4 visible, unanswered
        )
        session = _session([1], None, None, None, None)
        self.assertEqual(_get_incomplete_required_form_positions(quiz, session), [3, 4])


class CreateQuizDisplayConditionValidationTests(BaseTestCase):
    """POST /quiz rejects a display_condition the runtime could never satisfy, and any
    display_condition outside a form. Fixture positions (one set): 0 subjective,
    1 single-choice (3 options), 2 multi-choice (3), 3 single-choice (7), 4 matrix-rating,
    5 matrix-numerical, 6 subjective, 7 subjective."""

    def setUp(self):
        super().setUp()
        self.form = json.load(open(_DUMMY_DATA / "form_questionnaire.json"))

    def _post(self, quiz):
        return self.client.post("/quiz/", json=quiz)

    def _form_with(self, *conditions):
        """The form fixture with (position, display_condition) pairs attached."""
        form = deepcopy(self.form)
        questions = form["question_sets"][0]["questions"]
        for position, condition in conditions:
            questions[position]["display_condition"] = condition
        return form

    def _assert_rejected(self, quiz, *fragments):
        num_quizzes = self.db.quizzes.count_documents({})
        response = self._post(quiz)
        self.assertEqual(response.status_code, 422, response.text)
        detail = " | ".join(response.json()["detail"])
        for fragment in fragments:
            self.assertIn(fragment, detail)
        # nothing stored
        self.assertEqual(self.db.quizzes.count_documents({}), num_quizzes)

    def test_valid_conditions_are_created(self):
        response = self._post(
            self._form_with((6, _cond(1, [0])), (7, _cond(2, [0, 2])))
        )
        self.assertEqual(response.status_code, 201, response.text)
        stored = self.db.questions.find_one(
            {
                "display_condition": {"$exists": True},
                "text": self.form["question_sets"][0]["questions"][6]["text"],
            }
        )
        self.assertEqual(stored["display_condition"], _cond(1, [0]))

    def test_chained_condition_is_created(self):
        response = self._post(self._form_with((3, _cond(1, [0])), (6, _cond(3, [6]))))
        self.assertEqual(response.status_code, 201, response.text)

    def test_form_without_conditions_is_created(self):
        self.assertEqual(self._post(self.form).status_code, 201)

    def test_forward_reference_rejected(self):
        self._assert_rejected(
            self._form_with((1, _cond(3, [0]))),
            "position 1: source_position 3 must point to an earlier question",
        )

    def test_self_reference_rejected(self):
        self._assert_rejected(
            self._form_with((3, _cond(3, [0]))), "position 3: source_position 3"
        )

    def test_negative_source_rejected(self):
        self._assert_rejected(
            self._form_with((6, _cond(-1, [0]))), "position 6: source_position -1"
        )

    def test_out_of_range_source_rejected(self):
        self._assert_rejected(
            self._form_with((6, _cond(99, [0]))), "position 6: source_position 99"
        )

    def test_non_choice_trigger_rejected(self):
        self._assert_rejected(
            self._form_with((6, _cond(0, [0])), (7, _cond(4, [0]))),
            "trigger at position 0 must be one of single-choice, multi-choice, not subjective",
            "trigger at position 4",
        )

    def test_empty_option_indices_rejected(self):
        self._assert_rejected(
            self._form_with((6, _cond(1, []))), "option_indices must not be empty"
        )

    def test_out_of_range_option_index_rejected(self):
        self._assert_rejected(
            self._form_with((6, _cond(1, [0, 3]))),
            "option_indices [0, 3] must be between 0 and 2 (the trigger has 3 options)",
        )

    def test_negative_option_index_rejected(self):
        self._assert_rejected(
            self._form_with((6, _cond(1, [-1]))), "option_indices [-1]"
        )

    def test_display_condition_rejected_outside_forms(self):
        for quiz_type in ("assessment", "homework", "omr-assessment"):
            with self.subTest(quiz_type=quiz_type):
                quiz = self._form_with((6, _cond(1, [0])))
                quiz["metadata"]["quiz_type"] = quiz_type
                self._assert_rejected(
                    quiz, "position 6: display_condition is only allowed on forms"
                )

    def test_display_condition_rejected_without_metadata(self):
        quiz = self._form_with((6, _cond(1, [0])))
        del quiz["metadata"]
        self._assert_rejected(quiz, "only allowed on forms")


if __name__ == "__main__":
    unittest.main()
