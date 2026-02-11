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
