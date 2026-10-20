"""Tests for the `single-choice-other` question type: a single-choice question whose LAST
option is "Other" with a free-text box. Its answer is {"selected": [index], "other_text": ...}.

Covers the required-answer check, the type-aware option reading used by the conditional
display evaluator, and end-quiz validation through the API (including the beyond-subset
hydration of trimmed question options)."""

import unittest

from .base import BaseTestCase
from routers import forms, quizzes, sessions, session_answers
from routers.sessions import (
    _get_incomplete_required_form_positions,
    _is_required_form_answer_complete,
)
from services.form_visibility import (
    answer_option_indices,
    compute_form_question_visibility,
)
from schemas import EventType
from services.scoring import compute_session_metrics
from settings import Settings

settings = Settings()

OPTIONS = [{"text": "I was not aware"}, {"text": "No time"}, {"text": "Other"}]
OTHER_INDEX = 2


def _other_q(display_condition=None, required=None):
    question = {"type": "single-choice-other", "options": OPTIONS}
    if display_condition is not None:
        question["display_condition"] = display_condition
    if required is not None:
        question["required"] = required
    return question


def _answer(selected, other_text=None):
    return {"selected": selected, "other_text": other_text}


class RequiredAnswerCompleteTests(unittest.TestCase):
    def test_normal_option_is_complete(self):
        self.assertTrue(_is_required_form_answer_complete(_other_q(), _answer([0])))

    def test_other_with_text_is_complete(self):
        answer = _answer([OTHER_INDEX], "No internet at home")
        self.assertTrue(_is_required_form_answer_complete(_other_q(), answer))

    def test_other_with_blank_text_is_incomplete(self):
        for text in (None, "", "   "):
            answer = _answer([OTHER_INDEX], text)
            self.assertFalse(_is_required_form_answer_complete(_other_q(), answer))

    def test_nothing_selected_is_incomplete(self):
        self.assertFalse(_is_required_form_answer_complete(_other_q(), None))
        self.assertFalse(_is_required_form_answer_complete(_other_q(), _answer([])))

    def test_wrong_shape_is_incomplete(self):
        # a plain list (single-choice shape) is not a valid answer for this type
        self.assertFalse(_is_required_form_answer_complete(_other_q(), [0]))


class AnswerOptionIndicesTests(unittest.TestCase):
    def test_reads_selected_for_other_type(self):
        self.assertEqual(
            answer_option_indices(_answer([1]), "single-choice-other"), [1]
        )

    def test_list_answers_unchanged(self):
        self.assertEqual(answer_option_indices([0, 2], "multi-choice"), [0, 2])
        self.assertEqual(answer_option_indices([0, 2]), [0, 2])

    def test_matrix_dict_with_selected_key_is_not_misread(self):
        # matrix answers are dicts keyed by row label; a row named "selected" must not
        # be mistaken for this type's answer
        self.assertEqual(answer_option_indices({"selected": [1]}, "matrix-rating"), [])
        self.assertEqual(answer_option_indices({"selected": [1]}), [])


class OtherTypeAsTriggerTests(unittest.TestCase):
    def _questions(self):
        follow_up = {
            "type": "subjective",
            "display_condition": {"source_position": 0, "option_indices": [1]},
        }
        return [_other_q(), follow_up]

    def test_follow_up_shown_when_trigger_selects_option(self):
        answers = [{"answer": _answer([1])}, {"answer": None}]
        self.assertEqual(
            compute_form_question_visibility(self._questions(), answers), [True, True]
        )

    def test_follow_up_hidden_when_trigger_selects_other(self):
        answers = [{"answer": _answer([OTHER_INDEX], "x")}, {"answer": None}]
        self.assertEqual(
            compute_form_question_visibility(self._questions(), answers), [True, False]
        )

    def test_session_metrics_follow_the_trigger(self):
        quiz = {
            "metadata": {"quiz_type": "form"},
            "question_sets": [
                {"_id": "s", "title": "s", "questions": self._questions()}
            ],
        }

        def metrics(trigger_answer):
            session = {
                "session_answers": [{"answer": trigger_answer}, {"answer": None}]
            }
            qset = compute_session_metrics(session, quiz)["qset_metrics"][0]
            return qset["num_answered"], qset["num_skipped"]

        # follow-up hidden (Other picked): answered 1, skipped 0
        self.assertEqual(metrics(_answer([OTHER_INDEX], "x")), (1, 0))
        # follow-up shown and left blank: answered 1, skipped 1
        self.assertEqual(metrics(_answer([1])), (1, 1))


class IncompletePositionsTests(unittest.TestCase):
    def _quiz(self, *questions):
        return {"question_sets": [{"questions": list(questions)}]}

    def _session(self, *answers):
        return {"session_answers": [{"answer": answer} for answer in answers]}

    def test_required_other_blank_is_reported(self):
        quiz = self._quiz(_other_q())
        session = self._session(_answer([OTHER_INDEX], ""))
        self.assertEqual(_get_incomplete_required_form_positions(quiz, session), [0])

    def test_optional_other_blank_is_accepted(self):
        quiz = self._quiz(_other_q(required=False))
        session = self._session(_answer([OTHER_INDEX], None))
        self.assertEqual(_get_incomplete_required_form_positions(quiz, session), [])

    def test_hidden_other_question_is_skipped(self):
        trigger = {"type": "single-choice", "options": OPTIONS}
        dependent = _other_q({"source_position": 0, "option_indices": [0]})
        quiz = self._quiz(trigger, dependent)
        session = self._session([1], None)
        self.assertEqual(_get_incomplete_required_form_positions(quiz, session), [])


class EndQuizApiTests(BaseTestCase):
    """End-quiz validation through the API. The single-choice-other question sits beyond
    the first `subset_size` questions, where the quiz doc trims `options`, so this also
    covers loading the full question before the required check."""

    def setUp(self):
        super().setUp()
        filler = [
            {"text": f"Q{i}", "type": "single-choice", "options": OPTIONS}
            for i in range(settings.subset_size)
        ]
        self.other_position = settings.subset_size
        form = {
            "title": "Other option form",
            "max_marks": 0,
            "num_graded_questions": 0,
            "require_all_questions": True,
            "metadata": {"quiz_type": "form"},
            "question_sets": [
                {
                    "title": "Section",
                    "max_questions_allowed_to_attempt": settings.subset_size + 1,
                    "questions": filler
                    + [
                        {
                            "text": "Why?",
                            "type": "single-choice-other",
                            "options": OPTIONS,
                            "graded": False,
                        }
                    ],
                }
            ],
        }
        response = self.client.post(quizzes.router.prefix + "/", json=form)
        assert response.status_code == 201
        self.quiz_id = response.json()["id"]
        response = self.client.post(
            sessions.router.prefix + "/", json={"quiz_id": self.quiz_id, "user_id": 1}
        )
        self.session_id = response.json()["_id"]
        self.client.patch(
            f"{sessions.router.prefix}/{self.session_id}",
            json={"event": EventType.start_quiz.value},
        )

    def _answer_all(self, other_answer):
        updates = [[i, {"answer": [0]}] for i in range(self.other_position)]
        updates.append([self.other_position, {"answer": other_answer}])
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=updates,
        )
        assert response.status_code == 200

    def _end_quiz(self):
        return self.client.patch(
            f"{sessions.router.prefix}/{self.session_id}",
            json={"event": EventType.end_quiz.value},
        )

    def test_can_trigger_a_follow_up_at_creation(self):
        form = {
            "title": "Other trigger form",
            "max_marks": 0,
            "num_graded_questions": 0,
            "metadata": {"quiz_type": "form"},
            "question_sets": [
                {
                    "max_questions_allowed_to_attempt": 2,
                    "questions": [
                        {
                            "text": "Why?",
                            "type": "single-choice-other",
                            "options": OPTIONS,
                        },
                        {
                            "text": "Tell us more",
                            "type": "subjective",
                            "display_condition": {
                                "source_position": 0,
                                "option_indices": [OTHER_INDEX],
                            },
                        },
                    ],
                }
            ],
        }
        response = self.client.post(quizzes.router.prefix + "/", json=form)
        assert response.status_code == 201, response.text

    def test_question_type_and_options_are_served(self):
        form = self.client.get(
            f"{forms.router.prefix}/{self.quiz_id}", params={"single_page_mode": True}
        ).json()
        question = form["question_sets"][0]["questions"][self.other_position]
        assert question["type"] == "single-choice-other"
        assert [option["text"] for option in question["options"]][-1] == "Other"

    def test_blank_other_blocks_submit(self):
        self._answer_all(_answer([OTHER_INDEX], "  "))
        response = self._end_quiz()
        assert response.status_code == 400
        assert response.json()["detail"]["missing_positions"] == [self.other_position]

    def test_filled_other_allows_submit(self):
        self._answer_all(_answer([OTHER_INDEX], "No internet at home"))
        assert self._end_quiz().status_code == 200

    def test_normal_option_allows_submit(self):
        self._answer_all(_answer([1]))
        assert self._end_quiz().status_code == 200

    def test_answer_round_trips(self):
        self._answer_all(_answer([OTHER_INDEX], "No internet at home"))
        session = self.client.get(f"{sessions.router.prefix}/{self.session_id}").json()
        assert session["session_answers"][self.other_position]["answer"] == {
            "selected": [OTHER_INDEX],
            "other_text": "No internet at home",
        }


if __name__ == "__main__":
    unittest.main()
