import copy
import json
from unittest.mock import patch
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

    def test_patch_quiz_updates_session_editable_fields(self):
        # Timed quiz (time_limit.max = 200s): the stored session_end_time is the supplied
        # window end PLUS the quiz duration (answer-visibility time), not the raw window end.
        quiz_id = self.timed_quiz_id
        resp = self.client.patch(
            f"{quizzes.router.prefix}/{quiz_id}",
            json={
                "title": "Renamed by LMS",
                "shuffle": True,
                "show_scores": False,
                "review_immediate": False,
                "session_end_time": "2026-04-15T14:00:00",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == quiz_id
        assert set(body["updated"]) == {
            "title",
            "shuffle",
            "show_scores",
            "review_immediate",
            "session_end_time",
        }

        doc = mongo_client.quiz.quizzes.find_one({"_id": quiz_id})
        assert doc["title"] == "Renamed by LMS"
        assert doc["shuffle"] is True
        assert doc["show_scores"] is False
        assert doc["review_immediate"] is False
        # 14:00:00 + 200s = 14:03:20
        assert doc["metadata"]["session_end_time"] == "2026-04-15T14:03:20"

    def test_patch_quiz_session_end_time_untimed_quiz_has_no_offset(self):
        # An untimed quiz (time_limit None) adds no duration; the value is just normalized.
        quiz_id = self.homework_quiz_id
        resp = self.client.patch(
            f"{quizzes.router.prefix}/{quiz_id}",
            json={"session_end_time": "2026-04-15T14:00:00"},
        )
        assert resp.status_code == 200
        doc = mongo_client.quiz.quizzes.find_one({"_id": quiz_id})
        assert doc["metadata"]["session_end_time"] == "2026-04-15T14:00:00"

    def test_patch_quiz_session_end_time_when_metadata_is_null(self):
        # A quiz doc can carry metadata: null (the GET route guards for it). A dotted
        # $set would raise on the null intermediate; the endpoint must handle it.
        quiz_id = self.homework_quiz_id
        mongo_client.quiz.quizzes.update_one(
            {"_id": quiz_id}, {"$set": {"metadata": None}}
        )

        resp = self.client.patch(
            f"{quizzes.router.prefix}/{quiz_id}",
            json={"session_end_time": "2026-04-15T14:00:00"},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == ["session_end_time"]

        doc = mongo_client.quiz.quizzes.find_one({"_id": quiz_id})
        # untimed quiz -> no offset, value normalized to isoformat
        assert doc["metadata"] == {"session_end_time": "2026-04-15T14:00:00"}

    def test_patch_quiz_session_end_time_accepts_12h_format(self):
        # The LMS emits the legacy 12-hour "%I:%M:%S %p" format; it must parse and still get
        # the duration offset (else the answer-review gate silently opens at the window end).
        quiz_id = self.timed_quiz_id  # time_limit.max = 200s
        resp = self.client.patch(
            f"{quizzes.router.prefix}/{quiz_id}",
            json={"session_end_time": "2026-04-15 02:00:00 PM"},
        )
        assert resp.status_code == 200
        doc = mongo_client.quiz.quizzes.find_one({"_id": quiz_id})
        # 14:00:00 + 200s = 14:03:20
        assert doc["metadata"]["session_end_time"] == "2026-04-15T14:03:20"

    def test_patch_quiz_only_touches_provided_fields(self):
        quiz_id = self.short_homework_quiz_id
        before = mongo_client.quiz.quizzes.find_one({"_id": quiz_id})

        resp = self.client.patch(
            f"{quizzes.router.prefix}/{quiz_id}", json={"shuffle": True}
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == ["shuffle"]

        after = mongo_client.quiz.quizzes.find_one({"_id": quiz_id})
        assert after["shuffle"] is True
        # untouched field stays as it was
        assert after["title"] == before["title"]

    def test_patch_quiz_with_no_fields_is_a_noop(self):
        quiz_id = self.homework_quiz_id
        resp = self.client.patch(f"{quizzes.router.prefix}/{quiz_id}", json={})
        assert resp.status_code == 200
        assert resp.json()["updated"] == []

    def test_patch_quiz_returns_404_for_unknown_id(self):
        resp = self.client.patch(
            f"{quizzes.router.prefix}/does-not-exist", json={"shuffle": True}
        )
        assert resp.status_code == 404

    # ---- CMS from-cms create: answer-visibility time ----

    def _cms_quiz_dict(self, **overrides):
        """A quiz dict shaped like map_cms_test_to_quiz's output (1 set, 2 questions), built
        off the homework fixture. `overrides` shallow-merge onto the top level."""
        quiz = copy.deepcopy(self.homework_quiz_data)
        quiz.update(overrides)
        return quiz

    def test_create_from_cms_stores_answer_visibility_time(self):
        quiz_dict = self._cms_quiz_dict(time_limit={"min": 0, "max": 200})
        with patch("routers.quizzes.fetch_assembled_test", return_value={}), patch(
            "routers.quizzes.map_cms_test_to_quiz", return_value=(quiz_dict, [])
        ):
            resp = self.client.post(
                f"{quizzes.router.prefix}/from-cms",
                json={
                    "test_id": 504,
                    "curriculum_id": 1,
                    "grade_id": 1,
                    "session_end_time": "2026-04-15T14:00:00",
                },
            )
        assert resp.status_code == 201
        doc = mongo_client.quiz.quizzes.find_one({"_id": resp.json()["id"]})
        # 14:00:00 + 200s duration = 14:03:20
        assert doc["metadata"]["session_end_time"] == "2026-04-15T14:03:20"

    def test_create_from_cms_without_session_end_time_leaves_it_unset(self):
        quiz_dict = self._cms_quiz_dict(time_limit={"min": 0, "max": 200})
        with patch("routers.quizzes.fetch_assembled_test", return_value={}), patch(
            "routers.quizzes.map_cms_test_to_quiz", return_value=(quiz_dict, [])
        ):
            resp = self.client.post(
                f"{quizzes.router.prefix}/from-cms",
                json={"test_id": 504, "curriculum_id": 1, "grade_id": 1},
            )
        assert resp.status_code == 201
        doc = mongo_client.quiz.quizzes.find_one({"_id": resp.json()["id"]})
        assert doc["metadata"].get("session_end_time") is None

    # ---- regenerate in place (PUT /quiz/{id}/from-cms) ----

    def test_regenerate_preserves_ids_and_refreshes_content(self):
        quiz_id, _ = self.post_and_get_quiz(copy.deepcopy(self.homework_quiz_data))
        # Session-edit sets these on the quiz doc; regenerate must not reset them.
        self.client.patch(
            f"{quizzes.router.prefix}/{quiz_id}",
            json={"title": "LMS Session Name", "show_scores": False},
        )
        before = mongo_client.quiz.quizzes.find_one({"_id": quiz_id})
        old_qids = [q["_id"] for q in before["question_sets"][0]["questions"]]

        # Corrected test: same structure, changed content + content-metadata.
        new_quiz = self._cms_quiz_dict()
        new_quiz["title"] = "CMS Test Title"  # must NOT overwrite the session name
        new_quiz["question_sets"][0]["questions"][0]["text"] = "CORRECTED text"
        new_quiz["metadata"]["subject"] = "Physics"  # content metadata -> refreshes
        new_quiz["metadata"]["grade"] = "99"  # session-editable metadata -> preserved

        with patch("routers.quizzes.fetch_assembled_test", return_value={}), patch(
            "routers.quizzes.map_cms_test_to_quiz", return_value=(new_quiz, [])
        ):
            resp = self.client.put(
                f"{quizzes.router.prefix}/{quiz_id}/from-cms",
                json={"test_id": 504, "curriculum_id": 1, "grade_id": 1},
            )
        assert resp.status_code == 200
        assert resp.json()["regenerated"] is True

        after = mongo_client.quiz.quizzes.find_one({"_id": quiz_id})
        # quiz + question ids preserved (attempts stay linked)
        assert after["_id"] == quiz_id
        assert [q["_id"] for q in after["question_sets"][0]["questions"]] == old_qids
        # question content refreshed in the questions collection
        assert (
            mongo_client.quiz.questions.find_one({"_id": old_qids[0]})["text"]
            == "CORRECTED text"
        )
        # session-editable settings preserved
        assert after["title"] == "LMS Session Name"
        assert after["show_scores"] is False
        assert after["metadata"]["grade"] == "8"  # old value kept, not the CMS "99"
        # content metadata refreshed from the corrected test
        assert after["metadata"]["subject"] == "Physics"

    def test_regenerate_recomputes_session_end_time_with_supplied_window(self):
        quiz_id, _ = self.post_and_get_quiz(copy.deepcopy(self.homework_quiz_data))
        new_quiz = self._cms_quiz_dict(time_limit={"min": 0, "max": 200})
        with patch("routers.quizzes.fetch_assembled_test", return_value={}), patch(
            "routers.quizzes.map_cms_test_to_quiz", return_value=(new_quiz, [])
        ):
            resp = self.client.put(
                f"{quizzes.router.prefix}/{quiz_id}/from-cms",
                json={
                    "test_id": 504,
                    "curriculum_id": 1,
                    "grade_id": 1,
                    "session_end_time": "2026-04-15T14:00:00",
                },
            )
        assert resp.status_code == 200
        doc = mongo_client.quiz.quizzes.find_one({"_id": quiz_id})
        assert doc["metadata"]["session_end_time"] == "2026-04-15T14:03:20"

    def test_regenerate_preserves_session_end_time_when_not_supplied(self):
        quiz_id, _ = self.post_and_get_quiz(copy.deepcopy(self.homework_quiz_data))
        self.client.patch(
            f"{quizzes.router.prefix}/{quiz_id}",
            json={"session_end_time": "2026-04-15T14:00:00"},  # untimed -> stored as-is
        )
        new_quiz = self._cms_quiz_dict()
        with patch("routers.quizzes.fetch_assembled_test", return_value={}), patch(
            "routers.quizzes.map_cms_test_to_quiz", return_value=(new_quiz, [])
        ):
            resp = self.client.put(
                f"{quizzes.router.prefix}/{quiz_id}/from-cms",
                json={"test_id": 504, "curriculum_id": 1, "grade_id": 1},
            )
        assert resp.status_code == 200
        doc = mongo_client.quiz.quizzes.find_one({"_id": quiz_id})
        assert doc["metadata"]["session_end_time"] == "2026-04-15T14:00:00"

    def test_regenerate_refuses_structure_change(self):
        quiz_id, _ = self.post_and_get_quiz(copy.deepcopy(self.homework_quiz_data))
        before = mongo_client.quiz.quizzes.find_one({"_id": quiz_id})

        new_quiz = self._cms_quiz_dict()  # add a 3rd question -> structure differs
        new_quiz["question_sets"][0]["questions"].append(
            copy.deepcopy(new_quiz["question_sets"][0]["questions"][0])
        )
        with patch("routers.quizzes.fetch_assembled_test", return_value={}), patch(
            "routers.quizzes.map_cms_test_to_quiz", return_value=(new_quiz, [])
        ):
            resp = self.client.put(
                f"{quizzes.router.prefix}/{quiz_id}/from-cms",
                json={"test_id": 504, "curriculum_id": 1, "grade_id": 1},
            )
        assert resp.status_code == 409
        after = mongo_client.quiz.quizzes.find_one({"_id": quiz_id})
        # nothing was written
        assert len(after["question_sets"][0]["questions"]) == len(
            before["question_sets"][0]["questions"]
        )

    def test_regenerate_refuses_when_question_identity_changes(self):
        # Same set/question counts, but a position is now a DIFFERENT problem (source_id
        # changed) — a reorder or delete+add. Blindly reusing the old _id would mis-score
        # attempts, so this must 409 with no write.
        seed = copy.deepcopy(self.homework_quiz_data)
        for idx, q in enumerate(seed["question_sets"][0]["questions"]):
            q["source_id"] = f"cms-{idx}"
        quiz_id, _ = self.post_and_get_quiz(seed)
        before = mongo_client.quiz.quizzes.find_one({"_id": quiz_id})
        old_q0_id = before["question_sets"][0]["questions"][0]["_id"]

        new_quiz = copy.deepcopy(seed)
        new_quiz["question_sets"][0]["questions"][0]["source_id"] = "cms-999"

        with patch("routers.quizzes.fetch_assembled_test", return_value={}), patch(
            "routers.quizzes.map_cms_test_to_quiz", return_value=(new_quiz, [])
        ):
            resp = self.client.put(
                f"{quizzes.router.prefix}/{quiz_id}/from-cms",
                json={"test_id": 504, "curriculum_id": 1, "grade_id": 1},
            )
        assert resp.status_code == 409
        # no write happened — the question keeps its original source_id
        assert (
            mongo_client.quiz.questions.find_one({"_id": old_q0_id})["source_id"]
            == "cms-0"
        )

    def test_regenerate_returns_404_for_unknown_id(self):
        resp = self.client.put(
            f"{quizzes.router.prefix}/does-not-exist/from-cms",
            json={"test_id": 504, "curriculum_id": 1, "grade_id": 1},
        )
        assert resp.status_code == 404
