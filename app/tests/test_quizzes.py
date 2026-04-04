import json
from .base import BaseTestCase
from ..routers import quizzes, questions
from settings import Settings
from ..database import client as mongo_client

settings = Settings()


class QuizTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.short_homework_quiz_questions_length = len(
            self.short_homework_quiz_data["question_sets"][0]["questions"]
        )
        self.multi_qset_quiz_lengths = [
            len(self.multi_qset_quiz_data["question_sets"][i]["questions"])
            for i in range(2)
        ]  # two question sets in dummy data

        self.id = self.homework_quiz["_id"]
        self.length = len(self.homework_quiz_data["question_sets"][0]["questions"])

    def test_base_setup_quizId_and_quiz(self):
        assert self.homework_quiz_id == self.homework_quiz["_id"]

    def test_create_short_homework_quiz(self):
        response = self.client.post(
            quizzes.router.prefix + "/", json=self.short_homework_quiz_data
        )
        response = json.loads(response.content)
        quiz_id = response["id"]
        response = self.client.get(f"{quizzes.router.prefix}/{quiz_id}")
        assert response.status_code == 200

    def test_create_homework_quiz(self):
        response = self.client.post(
            quizzes.router.prefix + "/", json=self.homework_quiz_data
        )
        response = json.loads(response.content)
        quiz_id = response["id"]
        response = self.client.get(f"{quizzes.router.prefix}/{quiz_id}")
        assert response.status_code == 200

    def test_get_quiz_if_id_valid(self):
        response = self.client.get(
            f"{quizzes.router.prefix}/{self.short_homework_quiz_id}"
        )
        assert response.status_code == 200
        response = response.json()
        assert (
            len(response["question_sets"][0]["questions"])
            == self.short_homework_quiz_questions_length
        )

    def test_get_quiz_if_id_valid_and_omr_mode_in_params(self):
        response = self.client.get(
            f"{quizzes.router.prefix}/{self.multi_qset_quiz_id}",
            params={"omr_mode": True},
        )
        assert response.status_code == 200
        response = response.json()
        assert self.multi_qset_quiz_lengths == [
            len(response["question_sets"][i]["questions"]) for i in range(2)
        ]

    def test_get_quiz_returns_error_if_id_invalid(self):
        response = self.client.get(f"{quizzes.router.prefix}/00")
        assert response.status_code == 404
        response = response.json()
        assert response["detail"] == "quiz 00 not found"

    def test_created_multi_qset_quiz_contains_subsets(self):
        # the created long multi qset quiz should contain the same number of questions as the one in the provided input json
        assert self.multi_qset_quiz_lengths == [
            len(self.multi_qset_quiz["question_sets"][i]["questions"]) for i in range(2)
        ]

        # GET /quiz payload is sanitized (no answers/solutions)
        required_keys = ["type", "graded", "question_set_id"]
        # the keys that can be skipped in questions stored inside a quiz
        optional_keys = [
            "text",
            "instructions",
            "image",
            "options",
            "max_char_limit",
            "marking_scheme",
            "solution",
            "metadata",
        ]

        # checking the first subset_size bucket of questions in the quiz.
        # This should contain all the keys/details of a question
        for question_set_index in range(0, 2):
            for question_index in range(0, settings.subset_size):
                question = self.multi_qset_quiz["question_sets"][question_set_index][
                    "questions"
                ][question_index]
                for key in optional_keys + required_keys:
                    assert key in question
                assert question.get("correct_answer") is None
                assert question.get("solution") == []

        # checking the rest of the subset of questions in the quiz.
        # They should only contain some required keys and not all the keys
        for question_set_index in range(0, 2):
            for question_index in range(
                settings.subset_size,
                len(
                    self.multi_qset_quiz["question_sets"][question_set_index][
                        "questions"
                    ]
                ),
            ):
                question = self.multi_qset_quiz["question_sets"][question_set_index][
                    "questions"
                ][question_index]

                for key in required_keys:
                    assert key in question
                assert question.get("correct_answer") is None
                assert question.get("solution") == []

                for key in optional_keys:
                    # key exists in the returned question
                    assert key in question

                    # if the key is solution or option, they should be empty arrays
                    # because that is what is set as the default value in models.py
                    if key in ["solution", "options"]:
                        assert len(question[key]) == 0
                    # if the key is not solution or options, the value of those keys
                    # should be None as these are all optional keys
                    else:
                        assert question[key] is None

    def test_created_omr_contains_subsets(self):
        # the created long multi qset omr should contain the same number of questions as the one in the provided input json
        # multi qset quiz and multi qset omr have same data/lengths
        assert self.multi_qset_quiz_lengths == [
            len(self.multi_qset_omr["question_sets"][i]["questions"]) for i in range(2)
        ]  # 2 --> two question sets

        # Base GET /quiz payload is sanitized (no answers/solutions)
        required_keys = ["type", "graded", "question_set_id"]
        # the keys that can be skipped in questions stored inside a quiz
        optional_keys = [
            "text",
            "instructions",
            "image",
            "max_char_limit",
            "marking_scheme",
            "options",
            "solution",
            "metadata",
        ]

        # checking the first subset_size bucket of questions in the quiz.
        # This should contain all the keys/details of a question
        for question_set_index in range(0, 2):
            for question_index in range(0, settings.subset_size):
                question = self.multi_qset_omr["question_sets"][question_set_index][
                    "questions"
                ][question_index]
                for key in optional_keys + required_keys:
                    assert key in question
                assert question.get("correct_answer") is None
                assert question.get("solution") == []

        # checking the rest of the subset of questions in the quiz.
        # They should only contain some required keys and not all the keys
        for question_set_index in range(0, 2):
            for question_index in range(
                settings.subset_size,
                len(
                    self.multi_qset_omr["question_sets"][question_set_index][
                        "questions"
                    ]
                ),
            ):
                question = self.multi_qset_omr["question_sets"][question_set_index][
                    "questions"
                ][question_index]

                for key in required_keys:
                    assert key in question
                assert question.get("correct_answer") is None
                assert question.get("solution") == []

                for key in optional_keys:
                    # key exists in the returned question
                    assert key in question

                    # if the key is solution, they should be empty arrays
                    # because that is what is set as the default value in models.py
                    if key == "solution":
                        assert len(question[key]) == 0
                    # if the key is `options` and question type is single/multi-choice,
                    # the value should contain an array of option objects having length
                    # equal to number of options corresponding to that question
                    elif key == "options":
                        # get number of optiions fr this question
                        response = self.client.get(
                            questions.router.prefix + "/" + question["_id"]
                        )
                        ques_response = json.loads(response.content)
                        length_of_options = len(ques_response["options"])
                        assert len(question[key]) == length_of_options
                        if len(question[key]) != 0:
                            # single / multi-choice
                            for option_item in question[key]:
                                assert "text" in option_item
                                assert "image" in option_item
                    # if the key is not solution or options, the value of those keys
                    # should be None as these are all optional keys
                    else:
                        assert question[key] is None

    def test_get_quiz_include_answers_returns_full_questions_and_unsanitized_answers(
        self,
    ):
        response = self.client.get(
            f"{quizzes.router.prefix}/{self.multi_qset_quiz_id}",
            params={"include_answers": True},
        )
        assert response.status_code == 200
        payload = response.json()

        # include_answers=true should preserve bucketing (details only for first subset_size),
        # but answers should not be sanitized.
        first_q = payload["question_sets"][0]["questions"][0]
        assert first_q.get("text") is not None

        # Pick a trimmed question (first one after subset_size) and ensure it is still trimmed
        trimmed_q = payload["question_sets"][0]["questions"][settings.subset_size]
        assert trimmed_q.get("text") is None
        assert trimmed_q.get("options") in (None, [])

        # Answers should not be sanitized under include_answers=true
        assert first_q.get("correct_answer") is not None
        assert trimmed_q.get("correct_answer") is not None

    def test_get_quiz_include_answers_respects_display_solution_false(self):
        # Update the embedded (bucketed) quiz payload so we can verify the endpoint clears it.
        embedded_q_id = self.multi_qset_quiz["question_sets"][0]["questions"][0]["_id"]
        mongo_client.quiz.quizzes.update_one(
            {
                "_id": self.multi_qset_quiz_id,
                "question_sets._id": self.multi_qset_quiz["question_sets"][0]["_id"],
            },
            {"$set": {"question_sets.0.questions.0.solution": ["example-solution"]}},
        )
        mongo_client.quiz.quizzes.update_one(
            {"_id": self.multi_qset_quiz_id},
            {"$set": {"display_solution": False}},
        )

        response = self.client.get(
            f"{quizzes.router.prefix}/{self.multi_qset_quiz_id}",
            params={"include_answers": True},
        )
        assert response.status_code == 200
        payload = response.json()

        # Find the updated question in the response and ensure its solution is cleared
        found = None
        for qs in payload.get("question_sets") or []:
            for qq in qs.get("questions") or []:
                if qq.get("_id") == embedded_q_id:
                    found = qq
                    break
            if found is not None:
                break
        assert found is not None
        assert found.get("solution") == []

    def test_created_partial_mark_quiz_contains_partial_key(self):
        # check that key exists
        assert "partial" in self.partial_mark_quiz["question_sets"][0]["marking_scheme"]

        partial_mark_rules = self.partial_mark_quiz["question_sets"][0][
            "marking_scheme"
        ]["partial"]

        assert len(partial_mark_rules) > 0

        for partial_mark_rule in partial_mark_rules:
            assert "conditions" in partial_mark_rule
            assert "marks" in partial_mark_rule

            for condition in partial_mark_rule["conditions"]:
                assert "num_correct_selected" in condition

    def test_created_matrix_match_quiz_contains_list_of_string_answer(self):
        # Base GET /quiz payload is sanitized in Phase 3, so fetch with include_answers=true
        response = self.client.get(
            f"{quizzes.router.prefix}/{self.matrix_match_quiz_id}",
            params={"include_answers": True},
        )
        assert response.status_code == 200
        quiz_payload = response.json()

        # go through quiz and find advanced matrix match question
        for question_set in quiz_payload["question_sets"]:
            for question in question_set["questions"]:
                if question["type"] == "matrix-match":
                    assert isinstance(question["correct_answer"], list)
                    for ans in question["correct_answer"]:
                        assert isinstance(ans, str)

    def test_get_quiz_with_single_page_mode_returns_all_questions_with_full_details(
        self,
    ):
        """Test that single_page_mode parameter fetches all questions with full details"""
        response = self.client.get(
            f"{quizzes.router.prefix}/{self.multi_qset_quiz_id}",
            params={"single_page_mode": True},
        )
        assert response.status_code == 200
        response = response.json()

        # All questions in all question sets should have full details
        for question_set in response["question_sets"]:
            for question in question_set["questions"]:
                # Check that question has text (not None/empty)
                assert "text" in question
                # For single/multi-choice questions, options should have text content
                if question["type"] in ["single-choice", "multi-choice"]:
                    assert len(question["options"]) > 0
                    for option in question["options"]:
                        assert "text" in option

    def test_create_quiz_rejects_string_answer_for_single_choice(self):
        """correct_answer must be a list of ints for single-choice, not a string"""
        invalid_quiz = {
            "question_sets": [
                {
                    "title": "Section A",
                    "max_questions_allowed_to_attempt": 1,
                    "questions": [
                        {
                            "text": "Pick one",
                            "type": "single-choice",
                            "options": [
                                {"text": "Option 1"},
                                {"text": "Option 2"},
                            ],
                            "correct_answer": "wrong_type",
                            "graded": True,
                        }
                    ],
                }
            ],
            "max_marks": 1,
            "num_graded_questions": 1,
            "metadata": {"quiz_type": "homework"},
        }
        response = self.client.post(quizzes.router.prefix + "/", json=invalid_quiz)
        assert response.status_code == 422

    def test_create_quiz_rejects_list_answer_for_numerical_integer(self):
        """correct_answer must be int or str for numerical-integer, not a list"""
        invalid_quiz = {
            "question_sets": [
                {
                    "title": "Section A",
                    "max_questions_allowed_to_attempt": 1,
                    "questions": [
                        {
                            "text": "What is 2+2?",
                            "type": "numerical-integer",
                            "options": [],
                            "correct_answer": [4],
                            "graded": True,
                        }
                    ],
                }
            ],
            "max_marks": 1,
            "num_graded_questions": 1,
            "metadata": {"quiz_type": "assessment"},
        }
        response = self.client.post(quizzes.router.prefix + "/", json=invalid_quiz)
        assert response.status_code == 422

    def test_create_quiz_allows_none_answer_for_ungraded_question(self):
        """correct_answer can be None for any question type when ungraded"""
        valid_quiz = {
            "question_sets": [
                {
                    "title": "Section A",
                    "max_questions_allowed_to_attempt": 1,
                    "questions": [
                        {
                            "text": "Pick one",
                            "type": "single-choice",
                            "options": [
                                {"text": "Option 1"},
                                {"text": "Option 2"},
                            ],
                            "graded": False,
                        }
                    ],
                }
            ],
            "max_marks": 0,
            "num_graded_questions": 0,
            "metadata": {"quiz_type": "homework"},
        }
        response = self.client.post(quizzes.router.prefix + "/", json=valid_quiz)
        assert response.status_code == 201

    def test_single_page_mode_clears_solutions_when_display_solution_false(self):
        # Ensure at least one question has a non-empty solution in the questions collection
        qset_id = self.multi_qset_quiz["question_sets"][0]["_id"]
        q = mongo_client.quiz.questions.find_one({"question_set_id": qset_id})
        assert q is not None
        mongo_client.quiz.questions.update_one(
            {"_id": q["_id"]},
            {"$set": {"solution": ["example-solution"]}},
        )

        # Set quiz policy to hide solutions
        mongo_client.quiz.quizzes.update_one(
            {"_id": self.multi_qset_quiz_id},
            {"$set": {"display_solution": False}},
        )

        resp = self.client.get(
            f"{quizzes.router.prefix}/{self.multi_qset_quiz_id}",
            params={"single_page_mode": True},
        )
        assert resp.status_code == 200
        payload = resp.json()

        # Find the updated question in the response and ensure its solution is cleared
        found = None
        for qs in payload.get("question_sets") or []:
            for qq in qs.get("questions") or []:
                if qq.get("_id") == q["_id"]:
                    found = qq
                    break
            if found is not None:
                break
        assert found is not None
        assert found.get("solution") == []
