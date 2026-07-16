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

        # numerical-integer and numerical-float are distinct engine types (different input
        # widgets), so a section mixing them splits into two homogeneous sets — matching
        # legacy split_using_question_type, which keys on the resolved question type.
        quiz, warnings = map_cms_test_to_quiz(assembled)
        self.assertEqual(len(quiz["question_sets"]), 2)
        integer_q = quiz["question_sets"][0]["questions"][0]
        float_q = quiz["question_sets"][1]["questions"][0]
        self.assertEqual(integer_q["type"], "numerical-integer")
        self.assertEqual(integer_q["correct_answer"], 4)
        self.assertEqual(float_q["type"], "numerical-float")
        self.assertEqual(float_q["correct_answer"], 3.14)

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

    def test_numerical_range_warns_and_stores_midpoint(self):
        # A [low, high] range collapses to its midpoint (the engine grades a point +/-
        # tolerance, so the midpoint is the least-biased answer), not the low bound.
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
        self.assertEqual(question["correct_answer"], 15)
        self.assertTrue(any("midpoint" in w for w in warnings))

    def test_numerical_range_midpoint_can_be_float(self):
        assembled = _test_with_problems(
            problems=[
                _problem(
                    703,
                    "numerical_answer",
                    {
                        "text": "r?",
                        "options": [],
                        "answer": ["5", "6"],
                        "solutions": [],
                    },
                )
            ],
            sections=[
                {
                    "type": "numerical_answer",
                    "name": "R",
                    "compulsory": {
                        "problems": [{"id": 703, "pos_marks": [4], "neg_marks": [0]}]
                    },
                }
            ],
        )

        quiz, _ = map_cms_test_to_quiz(assembled)
        question = quiz["question_sets"][0]["questions"][0]
        self.assertEqual(question["type"], "numerical-float")
        self.assertEqual(question["correct_answer"], 5.5)

    def test_comprehension_inlines_paragraph_and_maps_numerical_answer(self):
        assembled = _test_with_problems(
            problems=[
                _problem(
                    800,
                    "comprehension",
                    {
                        "text": "Q on passage",
                        "options": None,
                        "answer": ["24.00"],
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
        self.assertEqual(question["type"], "numerical-float")
        self.assertEqual(question["correct_answer"], 24.0)
        self.assertEqual(question["options"], [])
        self.assertTrue(question["text"].startswith("PASSAGE. "))

    def test_invalid_comprehension_answer_names_problem(self):
        assembled = _test_with_problems(
            problems=[
                _problem(
                    801,
                    "comprehension",
                    {
                        "text": "Q on passage",
                        "options": None,
                        "answer": ["not-a-number"],
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
                        "problems": [{"id": 801, "pos_marks": [4], "neg_marks": [1]}]
                    },
                }
            ],
        )

        with self.assertRaisesRegex(CmsIngestError, "problem 801"):
            map_cms_test_to_quiz(assembled)

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

    def test_mixed_type_section_splits_into_homogeneous_sets(self):
        # A section that mixes question types is split into one set per contiguous type
        # run, so the grader (set-level marking) applies a coherent scheme to each. The
        # partial ladder lands only on the multi-choice set.
        assembled = _test_with_problems(
            problems=[
                _problem(
                    1,
                    "mcq_single_answer",
                    {
                        "text": "s1",
                        "options": ["A", "B"],
                        "answer": ["1"],
                        "solutions": [],
                    },
                ),
                _problem(
                    2,
                    "mcq_single_answer",
                    {
                        "text": "s2",
                        "options": ["A", "B"],
                        "answer": ["2"],
                        "solutions": [],
                    },
                ),
                _problem(
                    3,
                    "mcq_multiple_answer",
                    {
                        "text": "m1",
                        "options": ["A", "B", "C", "D"],
                        "answer": ["1", "2"],
                        "solutions": [],
                    },
                ),
            ],
            sections=[
                {
                    "type": "mixed",
                    "name": "Mixed",
                    "compulsory": {
                        "problems": [
                            {"id": 1, "pos_marks": [4], "neg_marks": [1]},
                            {"id": 2, "pos_marks": [4], "neg_marks": [1]},
                            {"id": 3, "pos_marks": [4], "neg_marks": [1]},
                        ]
                    },
                }
            ],
        )

        quiz, _ = map_cms_test_to_quiz(assembled)
        self.assertEqual(len(quiz["question_sets"]), 2)

        single_set, multi_set = quiz["question_sets"]
        self.assertEqual(len(single_set["questions"]), 2)
        self.assertEqual(single_set["questions"][0]["type"], "single-choice")
        self.assertIsNone(single_set["marking_scheme"]["partial"])

        self.assertEqual(len(multi_set["questions"]), 1)
        self.assertEqual(multi_set["questions"][0]["type"], "multi-choice")
        self.assertIsNotNone(multi_set["marking_scheme"]["partial"])
        # split sets are disambiguated by type in the title
        self.assertIn("multi-choice", multi_set["title"])
        # max_marks counts every attemptable question: (2 + 1) * 4
        self.assertEqual(quiz["max_marks"], 12)
        self.assertEqual(quiz["num_graded_questions"], 3)

    def test_optional_section_uses_mandatory_count_as_attempt_limit(self):
        # "attempt N of M": the optional pool becomes a set whose
        # max_questions_allowed_to_attempt is mandatory_count, and max_marks reflects only
        # the attemptable count — not every optional question.
        assembled = _test_with_problems(
            problems=[
                _problem(
                    10 + i,
                    "numerical_answer",
                    {
                        "text": f"q{i}",
                        "options": [],
                        "answer": [str(i + 1)],
                        "solutions": [],
                    },
                )
                for i in range(5)
            ],
            sections=[
                {
                    "type": "numerical_answer",
                    "name": "Section 2",
                    "compulsory": {
                        "problems": [
                            {"id": 10, "pos_marks": [4], "neg_marks": [0]},
                            {"id": 11, "pos_marks": [4], "neg_marks": [0]},
                        ]
                    },
                    "optional": {
                        "mandatory_count": 1,
                        "problems": [
                            {"id": 12, "pos_marks": [4], "neg_marks": [0]},
                            {"id": 13, "pos_marks": [4], "neg_marks": [0]},
                            {"id": 14, "pos_marks": [4], "neg_marks": [0]},
                        ],
                    },
                }
            ],
        )

        quiz, _ = map_cms_test_to_quiz(assembled)
        self.assertEqual(len(quiz["question_sets"]), 2)
        compulsory_set, optional_set = quiz["question_sets"]

        self.assertEqual(compulsory_set["max_questions_allowed_to_attempt"], 2)
        # all 3 optional questions are present, but only 1 may be attempted
        self.assertEqual(len(optional_set["questions"]), 3)
        self.assertEqual(optional_set["max_questions_allowed_to_attempt"], 1)
        self.assertIn("optional", optional_set["title"].lower())
        # max_marks = compulsory (2 * 4) + optional attemptable (1 * 4) = 12, NOT 5 * 4
        self.assertEqual(quiz["max_marks"], 12)

    def test_duration_maps_to_time_limit(self):
        assembled = _test_with_problems(
            problems=[
                _problem(
                    1,
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
                    "compulsory": {
                        "problems": [{"id": 1, "pos_marks": [4], "neg_marks": [1]}]
                    },
                }
            ],
        )
        assembled["test"]["type_params"]["duration"] = "60"

        quiz, _ = map_cms_test_to_quiz(assembled)
        self.assertEqual(quiz["time_limit"], {"min": 0, "max": 3600})

    def test_missing_duration_leaves_time_limit_none(self):
        assembled = _test_with_problems(
            problems=[
                _problem(
                    1,
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
                    "compulsory": {
                        "problems": [{"id": 1, "pos_marks": [4], "neg_marks": [1]}]
                    },
                }
            ],
        )
        assembled["test"]["type_params"]["duration"] = ""

        quiz, _ = map_cms_test_to_quiz(assembled)
        self.assertIsNone(quiz["time_limit"])

    def test_unknown_subtype_raises(self):
        # Unsupported subtypes (e.g. native matrix types the new CMS does not emit) fail
        # the ingest rather than being silently flattened to single-choice.
        assembled = _test_with_problems(
            problems=[
                _problem(
                    1,
                    "advanced_matrix_match",
                    {"text": "q", "options": ["A"], "answer": ["AQ"], "solutions": []},
                )
            ],
            sections=[
                {
                    "type": "advanced_matrix_match",
                    "name": "",
                    "compulsory": {
                        "problems": [{"id": 1, "pos_marks": [4], "neg_marks": [1]}]
                    },
                }
            ],
        )
        with self.assertRaises(CmsIngestError):
            map_cms_test_to_quiz(assembled)

    def test_question_set_carries_marking_description(self):
        assembled = _test_with_problems(
            problems=[
                _problem(
                    1,
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
                    "compulsory": {
                        "problems": [{"id": 1, "pos_marks": [4], "neg_marks": [1]}]
                    },
                }
            ],
        )

        quiz, _ = map_cms_test_to_quiz(assembled)
        description = quiz["question_sets"][0]["description"]
        self.assertIn("SINGLE correct option", description)
        self.assertIn("+4.0", description)


if __name__ == "__main__":
    unittest.main()
