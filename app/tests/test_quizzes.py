import json
from .base import BaseTestCase
from ..routers import quizzes, questions
from settings import Settings

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

        # the keys that should be present in every question stored inside a quiz
        required_keys = ["type", "correct_answer", "graded", "question_set_id"]
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

        # the keys that should be present in every question stored inside a quiz
        required_keys = ["type", "correct_answer", "graded", "question_set_id"]
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
        # go through quiz and find advanced matrix match question
        for question_set in self.matrix_match_quiz["question_sets"]:
            for question in question_set["questions"]:
                if question["type"] == "matrix-match":
                    assert isinstance(question["correct_answer"], list)
                    for ans in question["correct_answer"]:
                        assert isinstance(ans, str)
