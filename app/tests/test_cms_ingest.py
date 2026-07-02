"""Unit tests for the CMS -> quiz mapper (services.cms_ingest.map_cms_test_to_quiz).

Fixtures mirror the assembled-test JSON shape verified live against staging
(test 504 / problem 506) plus fabricated multi-choice and numerical problems.
No MongoDB needed — these exercise the pure mapping.
"""

import unittest

from services.cms_ingest import map_cms_test_to_quiz, CmsIngestError


def _test_with_problems(problems, sections, subtype="chapter_test"):
    """Build an assembled {test, problems} payload for a single subject/section."""
    return {
        "test": {
            "id": 504,
            "name": [{"lang_code": "en", "resource": "Trial"}],
            "subtype": subtype,
            "exam_ids": [1],
            "type_params": {
                "marks": 4,
                "pos_marks": [4],
                "neg_marks": [1],
                "subjects": [
                    {"subject_id": 2, "Name": "Chemistry", "sections": sections}
                ],
            },
        },
        "problems": problems,
    }


def _problem(pid, subtype, meta, **extra):
    base = {
        "id": pid,
        "type": "problem",
        "subtype": subtype,
        "meta_data": meta,
        "grade_id": 1,
        "subject_id": 2,
        "Subject": {"name": "Chemistry"},
    }
    base.update(extra)
    return base


class TestCmsMapper(unittest.TestCase):
    def test_single_choice(self):
        assembled = _test_with_problems(
            problems=[
                _problem(
                    506,
                    "mcq_single_answer",
                    {
                        "text": "Avanti?",
                        "options": ["A", "&nbsp;B", "C", "D"],
                        "answer": ["2"],
                        "solutions": [{"type": "text", "value": ""}],
                    },
                )
            ],
            sections=[
                {
                    "type": "mcq_single_answer",
                    "name": "",
                    "compulsory": {
                        "problems": [{"id": 506, "pos_marks": [4], "neg_marks": [1]}]
                    },
                }
            ],
        )

        quiz, warnings = map_cms_test_to_quiz(assembled)

        self.assertEqual(quiz["title"], "Trial")
        self.assertEqual(quiz["metadata"]["test_format"], "chapter_test")
        self.assertEqual(quiz["metadata"]["source"], "nex-gen-cms")
        self.assertEqual(quiz["metadata"]["source_id"], "504")
        self.assertEqual(len(quiz["question_sets"]), 1)

        qset = quiz["question_sets"][0]
        self.assertEqual(len(qset["questions"]), 1)
        question = qset["questions"][0]
        self.assertEqual(question["type"], "single-choice")
        # 1-based CMS answer "2" -> 0-based index [1]
        self.assertEqual(question["correct_answer"], [1])
        self.assertEqual(len(question["options"]), 4)
        self.assertTrue(question["graded"])
        self.assertEqual(question["source_id"], "506")

        marking = qset["marking_scheme"]
        self.assertEqual(marking["correct"], 4.0)
        self.assertEqual(marking["wrong"], -1.0)
        self.assertEqual(marking["skipped"], 0.0)
        self.assertIsNone(marking["partial"])

        self.assertEqual(quiz["max_marks"], 4)
        self.assertEqual(quiz["num_graded_questions"], 1)

    def test_multi_choice_partial_ladder(self):
        assembled = _test_with_problems(
            problems=[
                _problem(
                    600,
                    "mcq_multiple_answer",
                    {
                        "text": "Pick the correct ones",
                        "options": ["A", "B", "C", "D"],
                        "answer": ["1", "3"],  # options 1 and 3 correct
                        "solutions": [],
                    },
                )
            ],
            sections=[
                {
                    "type": "mcq_multiple_answer",
                    "name": "Section B",
                    "compulsory": {
                        "problems": [{"id": 600, "pos_marks": [4], "neg_marks": [1]}]
                    },
                }
            ],
        )

        quiz, warnings = map_cms_test_to_quiz(assembled)
        question = quiz["question_sets"][0]["questions"][0]
        self.assertEqual(question["type"], "multi-choice")
        self.assertEqual(question["correct_answer"], [0, 2])  # 1-based -> 0-based

        marking = quiz["question_sets"][0]["marking_scheme"]
        # 4 options -> partial ladder for 1..3 correct selected, +k each
        self.assertEqual(
            marking["partial"],
            [
                {"conditions": [{"num_correct_selected": 1}], "marks": 1},
                {"conditions": [{"num_correct_selected": 2}], "marks": 2},
                {"conditions": [{"num_correct_selected": 3}], "marks": 3},
            ],
        )
        # set title combines subject + section
        self.assertEqual(quiz["question_sets"][0]["title"], "Chemistry - Section B")

    def test_numerical_scalar_and_float(self):
        assembled = _test_with_problems(
            problems=[
                _problem(
                    700,
                    "numerical_answer",
                    {"text": "2+2?", "options": [], "answer": ["4"], "solutions": []},
                ),
                _problem(
                    701,
                    "numerical_answer",
                    {"text": "pi?", "options": [], "answer": ["3.14"], "solutions": []},
                ),
            ],
            sections=[
                {
                    "type": "numerical_answer",
                    "name": "Numericals",
                    "compulsory": {
                        "problems": [
                            {"id": 700, "pos_marks": [4], "neg_marks": [0]},
                            {"id": 701, "pos_marks": [4], "neg_marks": [0]},
                        ]
                    },
                }
            ],
        )

        quiz, warnings = map_cms_test_to_quiz(assembled)
        questions = quiz["question_sets"][0]["questions"]
        self.assertEqual(questions[0]["type"], "numerical-integer")
        self.assertEqual(questions[0]["correct_answer"], 4)
        self.assertEqual(questions[1]["type"], "numerical-float")
        self.assertEqual(questions[1]["correct_answer"], 3.14)

    def test_integer_type_maps_to_numerical_integer(self):
        # The CMS uses subtype "integer_type" for integer-answer questions (distinct from
        # "numerical_answer"); it must map to numerical-integer, not fall through to the
        # unknown-subtype single-choice default.
        assembled = _test_with_problems(
            problems=[
                _problem(
                    710,
                    "integer_type",
                    {"text": "count?", "options": [], "answer": ["9"], "solutions": []},
                ),
            ],
            sections=[
                {
                    "type": "integer_type",
                    "name": "Integers",
                    "compulsory": {
                        "problems": [{"id": 710, "pos_marks": [4], "neg_marks": [0]}]
                    },
                }
            ],
        )

        quiz, warnings = map_cms_test_to_quiz(assembled)
        question = quiz["question_sets"][0]["questions"][0]
        self.assertEqual(question["type"], "numerical-integer")
        self.assertEqual(question["correct_answer"], 9)
        self.assertFalse(any("unknown subtype" in w for w in warnings))

    def test_numerical_range_warns_and_stores_low(self):
        assembled = _test_with_problems(
            problems=[
                _problem(
                    702,
                    "numerical_answer",
                    {
                        "text": "range?",
                        "options": [],
                        "answer": ["10", "20"],
                        "solutions": [],
                    },
                )
            ],
            sections=[
                {
                    "type": "numerical_answer",
                    "name": "R",
                    "compulsory": {
                        "problems": [{"id": 702, "pos_marks": [4], "neg_marks": [0]}]
                    },
                }
            ],
        )

        quiz, warnings = map_cms_test_to_quiz(assembled)
        question = quiz["question_sets"][0]["questions"][0]
        self.assertEqual(question["correct_answer"], 10)
        self.assertTrue(any("range" in w for w in warnings))

    def test_comprehension_inlines_paragraph(self):
        assembled = _test_with_problems(
            problems=[
                _problem(
                    800,
                    "comprehension",
                    {
                        "text": "Q on passage",
                        "options": ["A", "B"],
                        "answer": ["1"],
                        "solutions": [],
                    },
                    paragraph={"id": 9, "body": "PASSAGE. "},
                )
            ],
            sections=[
                {
                    "type": "comprehension",
                    "name": "",
                    "compulsory": {
                        "problems": [{"id": 800, "pos_marks": [4], "neg_marks": [1]}]
                    },
                }
            ],
        )

        quiz, warnings = map_cms_test_to_quiz(assembled)
        question = quiz["question_sets"][0]["questions"][0]
        self.assertEqual(question["type"], "single-choice")
        self.assertTrue(question["text"].startswith("PASSAGE. "))

    def test_marks_cascade_from_section_when_problem_ref_unset(self):
        assembled = _test_with_problems(
            problems=[
                _problem(
                    900,
                    "mcq_single_answer",
                    {
                        "text": "q",
                        "options": ["A", "B"],
                        "answer": ["1"],
                        "solutions": [],
                    },
                )
            ],
            sections=[
                {
                    "type": "mcq_single_answer",
                    "name": "",
                    "pos_marks": [3],
                    "neg_marks": [1],
                    # problem ref has no pos_marks -> cascade to section
                    "compulsory": {"problems": [{"id": 900}]},
                }
            ],
        )

        quiz, warnings = map_cms_test_to_quiz(assembled)
        marking = quiz["question_sets"][0]["marking_scheme"]
        self.assertEqual(marking["correct"], 3.0)
        self.assertEqual(marking["wrong"], -1.0)

    def test_empty_test_raises(self):
        assembled = _test_with_problems(problems=[], sections=[])
        with self.assertRaises(CmsIngestError):
            map_cms_test_to_quiz(assembled)


if __name__ == "__main__":
    unittest.main()
