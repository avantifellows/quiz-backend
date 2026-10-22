import json
import unittest

from services.scoring import compute_session_metrics


class TestScoring(unittest.TestCase):
    def test_assessment_metrics_with_partial_and_ungraded(self):
        quiz = json.load(open("app/tests/dummy_data/scoring_small_assessment.json"))
        session = {
            "session_answers": [
                {"answer": [0, 2], "marked_for_review": False},
                {"answer": [0, 1], "marked_for_review": True},
                {"answer": 5, "marked_for_review": False},
                {"answer": "hello", "marked_for_review": False},
            ]
        }

        metrics = compute_session_metrics(session, quiz)
        self.assertEqual(len(metrics["qset_metrics"]), 1)
        qset = metrics["qset_metrics"][0]

        self.assertEqual(qset["num_answered"], 3)
        self.assertEqual(qset["num_skipped"], 0)
        self.assertEqual(qset["num_correct"], 1)
        self.assertEqual(qset["num_wrong"], 1)
        self.assertEqual(qset["num_partially_correct"], 1)
        self.assertEqual(qset["num_marked_for_review"], 1)
        self.assertEqual(qset["marks_scored"], 5.0)
        self.assertAlmostEqual(qset["attempt_rate"], 1.0, places=4)
        self.assertAlmostEqual(qset["accuracy_rate"], 0.5, places=4)

        self.assertEqual(metrics["total_answered"], 3)
        self.assertEqual(metrics["total_skipped"], 0)
        self.assertEqual(metrics["total_correct"], 1)
        self.assertEqual(metrics["total_wrong"], 1)
        self.assertEqual(metrics["total_partially_correct"], 1)
        self.assertEqual(metrics["total_marked_for_review"], 1)
        self.assertEqual(metrics["total_marks"], 5.0)

    def test_form_metrics_counts_only(self):
        quiz = json.load(open("app/tests/dummy_data/scoring_small_form.json"))
        session = {
            "session_answers": [
                {"answer": "yes", "marked_for_review": False},
                {"answer": None, "marked_for_review": False},
            ]
        }

        metrics = compute_session_metrics(session, quiz)
        self.assertEqual(len(metrics["qset_metrics"]), 1)
        qset = metrics["qset_metrics"][0]

        self.assertEqual(qset["num_answered"], 1)
        self.assertEqual(qset["num_skipped"], 1)
        self.assertEqual(qset["num_correct"], 0)
        self.assertEqual(qset["num_wrong"], 0)
        self.assertEqual(qset["num_partially_correct"], 0)
        self.assertEqual(qset["marks_scored"], 0.0)
        self.assertAlmostEqual(qset["attempt_rate"], 0.5, places=4)
        self.assertAlmostEqual(qset["accuracy_rate"], 0.0, places=4)

        self.assertEqual(metrics["total_answered"], 1)
        self.assertEqual(metrics["total_skipped"], 1)
        self.assertEqual(metrics["total_marks"], 0.0)

    def _conditional_form(self):
        """Two sets. Position 1 (set A) and position 3 (set B) are shown only when
        position 0 picks option 0."""
        condition = {"source_position": 0, "option_indices": [0]}
        return {
            "metadata": {"quiz_type": "form"},
            "question_sets": [
                {
                    "_id": "A",
                    "title": "A",
                    "questions": [
                        {"type": "single-choice"},
                        {"type": "subjective", "display_condition": condition},
                        {"type": "subjective"},
                    ],
                },
                {
                    "_id": "B",
                    "title": "B",
                    "questions": [
                        {"type": "subjective", "display_condition": condition},
                        {"type": "single-choice"},
                    ],
                },
            ],
        }

    def _session(self, *answers):
        return {
            "session_answers": [
                {"answer": answer, "marked_for_review": False} for answer in answers
            ]
        }

    def test_form_hidden_questions_are_neither_answered_nor_skipped(self):
        # trigger picks option 1: positions 1 and 3 are hidden; position 1 still holds
        # an old answer, which must not count
        metrics = compute_session_metrics(
            self._session([1], "old answer", "x", None, None), self._conditional_form()
        )
        set_a, set_b = metrics["qset_metrics"]
        self.assertEqual((set_a["num_answered"], set_a["num_skipped"]), (2, 0))
        self.assertAlmostEqual(set_a["attempt_rate"], 1.0, places=4)
        self.assertEqual((set_b["num_answered"], set_b["num_skipped"]), (0, 1))
        self.assertAlmostEqual(set_b["attempt_rate"], 0.0, places=4)
        self.assertEqual((metrics["total_answered"], metrics["total_skipped"]), (2, 1))

    def test_form_shown_follow_ups_count_normally(self):
        # trigger picks option 0: every question is shown
        metrics = compute_session_metrics(
            self._session([0], None, "x", "y", [1]), self._conditional_form()
        )
        set_a, set_b = metrics["qset_metrics"]
        self.assertEqual((set_a["num_answered"], set_a["num_skipped"]), (2, 1))
        self.assertAlmostEqual(set_a["attempt_rate"], 0.6667, places=4)
        self.assertEqual((set_b["num_answered"], set_b["num_skipped"]), (2, 0))
        self.assertEqual((metrics["total_answered"], metrics["total_skipped"]), (4, 1))

    def test_form_with_every_question_hidden_in_a_set(self):
        quiz = self._conditional_form()
        quiz["question_sets"][1]["questions"] = [
            quiz["question_sets"][1]["questions"][0]
        ]
        metrics = compute_session_metrics(self._session([1], None, None, None), quiz)
        set_b = metrics["qset_metrics"][1]
        self.assertEqual((set_b["num_answered"], set_b["num_skipped"]), (0, 0))
        self.assertEqual(set_b["attempt_rate"], 0)
