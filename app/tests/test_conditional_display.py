"""Unit tests for the conditional-display (display_condition) rule on the backend:
`_compute_form_question_visibility` (the single visibility evaluator) and its use in
`_get_incomplete_required_form_positions`. Pure functions — no MongoDB needed."""

import unittest

from routers.sessions import (
    _answer_option_indices,
    _compute_form_question_visibility,
    _get_incomplete_required_form_positions,
)


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


if __name__ == "__main__":
    unittest.main()
