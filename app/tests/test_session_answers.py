import json
from unittest.mock import patch
from bson import ObjectId
from .base import SessionsBaseTestCase
from routers import session_answers


class SessionAnswerTestCase(SessionsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.session_answers = self.homework_session["session_answers"]
        self.session_id = self.homework_session["_id"]
        self.session_answer_position_index = 0
        self.session_answer = self.session_answers[0]

    def test_gets_session_answer_from_a_session(self):
        response = self.client.get(
            f"{session_answers.router.prefix}/{self.session_id}/{self.session_answer_position_index}"
        )
        assert response.status_code == 200
        session_answer = json.loads(response.content)
        for key in ["question_id", "answer", "visited"]:
            assert session_answer[key] == self.session_answer[key]

    def test_update_session_answer_with_only_answer(self):
        new_answer = [0, 1, 2]
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/{self.session_answer_position_index}",
            json={"answer": new_answer},
        )
        assert response.status_code == 200
        response = self.client.get(
            f"{session_answers.router.prefix}/{self.session_id}/{self.session_answer_position_index}"
        )
        session_answer = json.loads(response.content)

        # ensure that `answer` has been updated
        assert session_answer["answer"] == new_answer

        # ensure that `visited` is not affected
        assert session_answer["visited"] == self.session_answer["visited"]

    def test_update_session_answer_with_only_visited(self):
        new_visited = True
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/{self.session_answer_position_index}",
            json={"visited": new_visited},
        )
        assert response.status_code == 200
        response = self.client.get(
            f"{session_answers.router.prefix}/{self.session_id}/{self.session_answer_position_index}"
        )
        session_answer = json.loads(response.content)

        # ensure that `visited` has been updated
        assert session_answer["visited"] == new_visited

        # ensure that `answer` is not affected
        assert session_answer["answer"] == self.session_answer["answer"]

    def test_update_session_answer_with_only_marked_for_review(self):
        new_marked_for_review = True
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/{self.session_answer_position_index}",
            json={"marked_for_review": new_marked_for_review},
        )
        assert response.status_code == 200
        response = self.client.get(
            f"{session_answers.router.prefix}/{self.session_id}/{self.session_answer_position_index}"
        )
        session_answer = json.loads(response.content)

        # ensure that `marked_for_review` has been updated
        assert session_answer["marked_for_review"] == new_marked_for_review

        # ensure that `answer` is not affected
        assert session_answer["answer"] == self.session_answer["answer"]

    def test_single_update_clears_explicit_null_fields(self):
        url = (
            f"{session_answers.router.prefix}/{self.session_id}/"
            f"{self.session_answer_position_index}"
        )
        response = self.client.patch(
            url,
            json={"answer": [0], "time_spent": 45},
        )
        assert response.status_code == 200

        response = self.client.patch(
            url,
            json={"answer": None, "time_spent": None},
        )
        assert response.status_code == 200

        session_answer = self.client.get(url).json()
        assert session_answer["answer"] is None
        assert session_answer["time_spent"] is None

    # --- US-001: Pre-DB validation for batch endpoint ---

    def test_batch_update_invalid_payloads_are_rejected_before_db_read(self):
        cases = [
            ([], "No position-answer pairs"),
            ([[0, {"answer": [0]}], [-1, {"answer": [1]}]], "negative"),
            ([[0, {"answer": [0]}], [0, {"answer": [1]}]], "Duplicate"),
            ([[0, {"answer": [0]}], [1, {}]], "Empty payload"),
        ]

        with patch.object(session_answers, "get_quiz_db") as spy_get_quiz_db:
            for payload, expected_detail in cases:
                with self.subTest(payload=payload):
                    response = self.client.patch(
                        f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
                        json=payload,
                    )
                    assert response.status_code == 400
                    assert expected_detail in response.json()["detail"]

            spy_get_quiz_db.assert_not_called()

    # --- US-002: Pre-DB validation for empty per-item payload ---

    def test_batch_update_time_spent_only_is_accepted(self):
        """Payload with only time_spent is a valid business field and should be accepted."""
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=[[0, {"time_spent": 45}]],
        )
        assert response.status_code == 200

    # --- US-003: Lightweight aggregation read path ---

    def test_batch_update_session_not_found_returns_404(self):
        """Nonexistent session returns 404 through aggregation read path."""
        response = self.client.patch(
            f"{session_answers.router.prefix}/nonexistent-session-id/update-multiple-answers",
            json=[[0, {"answer": [0]}]],
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    # --- US-004: Post-read bounds checking with off-by-one fix ---

    def test_batch_update_position_greater_than_length_returns_400(self):
        """Position > len(session_answers) still returns 400."""
        beyond_length = len(self.session_answers) + 5
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=[[beyond_length, {"answer": [0]}]],
        )
        assert response.status_code == 400
        assert "out of bounds" in response.json()["detail"]

    def test_batch_update_exact_length_does_not_extend_array(self):
        """Position == len(session_answers) must not silently extend the array."""
        exact_length = len(self.session_answers)
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=[[exact_length, {"answer": [0]}]],
        )
        assert response.status_code == 400
        assert "out of bounds" in response.json()["detail"]

        # Verify array was not extended
        session = self.db.sessions.find_one({"_id": self.session_id})
        assert len(session["session_answers"]) == exact_length

    # --- US-005: Malformed session_answers test coverage ---

    def test_batch_update_missing_session_answers_field_returns_404(self):
        """Session document with no session_answers field returns 404."""
        doc_id = str(ObjectId())
        self.db.sessions.insert_one(
            {"_id": doc_id, "user_id": "test_user", "quiz_id": "test_quiz"}
        )

        response = self.client.patch(
            f"{session_answers.router.prefix}/{doc_id}/update-multiple-answers",
            json=[[0, {"answer": [0]}]],
        )
        assert response.status_code == 404
        assert "No session answers found" in response.json()["detail"]

    def test_batch_update_null_session_answers_returns_404(self):
        """Session document with session_answers: None returns 404."""
        doc_id = str(ObjectId())
        self.db.sessions.insert_one(
            {
                "_id": doc_id,
                "user_id": "test_user",
                "quiz_id": "test_quiz",
                "session_answers": None,
            }
        )

        response = self.client.patch(
            f"{session_answers.router.prefix}/{doc_id}/update-multiple-answers",
            json=[[0, {"answer": [0]}]],
        )
        assert response.status_code == 404
        assert "No session answers found" in response.json()["detail"]

    def test_batch_update_non_array_session_answers_returns_404(self):
        """Session document with non-array session_answers (e.g., 'corrupted') returns 404."""
        doc_id = str(ObjectId())
        self.db.sessions.insert_one(
            {
                "_id": doc_id,
                "user_id": "test_user",
                "quiz_id": "test_quiz",
                "session_answers": "corrupted",
            }
        )

        response = self.client.patch(
            f"{session_answers.router.prefix}/{doc_id}/update-multiple-answers",
            json=[[0, {"answer": [0]}]],
        )
        assert response.status_code == 404
        assert "No session answers found" in response.json()["detail"]

    # --- US-006: Single-item PATCH — validation tightening ---

    def test_single_update_position_equal_to_length_returns_400(self):
        """position_index >= len(session_answers) returns 400 (off-by-one fix)."""
        exact_length = len(self.session_answers)
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/{exact_length}",
            json={"answer": [0]},
        )
        assert response.status_code == 400
        assert "out of bounds" in response.json()["detail"]

    def test_single_update_position_greater_than_length_returns_400(self):
        """position_index > len(session_answers) still returns 400."""
        beyond_length = len(self.session_answers) + 5
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/{beyond_length}",
            json={"answer": [0]},
        )
        assert response.status_code == 400
        assert "out of bounds" in response.json()["detail"]

    def test_single_update_invalid_payloads_are_rejected_before_db_read(self):
        cases = [
            (0, {}, "Empty payload"),
            (-1, {"answer": [0]}, "negative"),
            (-1, {}, "Empty payload"),
        ]

        with patch.object(session_answers, "get_quiz_db") as spy_get_quiz_db:
            for position, payload, expected_detail in cases:
                with self.subTest(position=position, payload=payload):
                    response = self.client.patch(
                        f"{session_answers.router.prefix}/{self.session_id}/{position}",
                        json=payload,
                    )
                    assert response.status_code == 400
                    assert expected_detail in response.json()["detail"]

            spy_get_quiz_db.assert_not_called()

    def test_batch_update_changes_only_targeted_answer(self):
        new_answer = [0, 2]
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=[[0, {"answer": new_answer}]],
        )
        assert response.status_code == 200

        targeted_answer = self.client.get(
            f"{session_answers.router.prefix}/{self.session_id}/0"
        ).json()
        untouched_answer = self.client.get(
            f"{session_answers.router.prefix}/{self.session_id}/1"
        ).json()

        assert targeted_answer["answer"] == new_answer
        assert targeted_answer["visited"] == self.session_answers[0]["visited"]
        assert untouched_answer == self.session_answers[1]

    def test_batch_update_clears_answer_with_null(self):
        self.db.sessions.update_one(
            {"_id": self.session_id},
            {"$set": {"session_answers.0.answer": [0]}},
        )

        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=[[0, {"answer": None}]],
        )

        assert response.status_code == 200
        answer = self.client.get(
            f"{session_answers.router.prefix}/{self.session_id}/0"
        ).json()
        assert answer["answer"] is None

    def test_batch_update_accepts_mixed_answer_shapes(self):
        session_id = self.multi_qset_quiz_session["_id"]
        updates = [
            [0, {"answer": 42}],
            [1, {"answer": "hello"}],
            [2, {"answer": {"row1": "A"}, "visited": True}],
            [3, {"answer": ["A,B", "C,D"]}],
        ]
        response = self.client.patch(
            f"{session_answers.router.prefix}/{session_id}/update-multiple-answers",
            json=updates,
        )

        assert response.status_code == 200
        for position, expected in updates:
            stored = self.client.get(
                f"{session_answers.router.prefix}/{session_id}/{position}"
            ).json()
            for field, value in expected.items():
                assert stored[field] == value
