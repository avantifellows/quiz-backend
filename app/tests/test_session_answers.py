import json
from .base import SessionsBaseTestCase
from ..routers import session_answers


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

    # --- US-001: Pre-DB validation for batch endpoint ---

    def test_batch_update_empty_batch_returns_400(self):
        """Empty batch [] returns 400 before any DB read."""
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=[],
        )
        assert response.status_code == 400
        assert "No position-answer pairs" in response.json()["detail"]

    def test_batch_update_negative_index_returns_400(self):
        """Negative position index returns 400 before any DB read."""
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=[[-1, {"answer": [0]}]],
        )
        assert response.status_code == 400
        assert "negative" in response.json()["detail"]

    def test_batch_update_duplicate_positions_returns_400(self):
        """Duplicate positions returns 400 before any DB read."""
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=[[0, {"answer": [0]}], [0, {"answer": [1]}]],
        )
        assert response.status_code == 400
        assert "Duplicate" in response.json()["detail"]

    def test_batch_update_negative_index_with_valid_indices_returns_400(self):
        """A mix of valid and negative indices still returns 400."""
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=[[0, {"answer": [0]}], [-2, {"answer": [1]}]],
        )
        assert response.status_code == 400
        assert "negative" in response.json()["detail"]

    def test_batch_update_validation_order_empty_before_negative(self):
        """Empty check fires before negative check (empty batch is checked first)."""
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=[],
        )
        assert response.status_code == 400
        # Empty check message, not negative
        assert "No position-answer pairs" in response.json()["detail"]

    def test_batch_update_nonexistent_session_with_valid_payload(self):
        """Valid payload with nonexistent session still passes pre-DB validation and returns 404."""
        response = self.client.patch(
            f"{session_answers.router.prefix}/nonexistent-session-id/update-multiple-answers",
            json=[[0, {"answer": [0]}]],
        )
        assert response.status_code == 404

    # --- US-002: Pre-DB validation for empty per-item payload ---

    def test_batch_update_empty_per_item_payload_returns_400(self):
        """[index, {}] with no business fields returns 400."""
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=[[0, {}]],
        )
        assert response.status_code == 400
        assert "Empty payload" in response.json()["detail"]

    def test_batch_update_multiple_items_one_empty_returns_400(self):
        """Batch with one valid and one empty per-item payload returns 400."""
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=[[0, {"answer": [0]}], [1, {}]],
        )
        assert response.status_code == 400
        assert "Empty payload at position 1" in response.json()["detail"]

    def test_batch_update_time_spent_only_is_accepted(self):
        """Payload with only time_spent is a valid business field and should be accepted."""
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=[[0, {"time_spent": 45}]],
        )
        assert response.status_code == 200

    def test_batch_update_empty_payload_rejected_before_db_read(self):
        """Empty per-item payload is rejected before any DB read (nonexistent session)."""
        response = self.client.patch(
            f"{session_answers.router.prefix}/nonexistent-session-id/update-multiple-answers",
            json=[[0, {}]],
        )
        assert response.status_code == 400
        assert "Empty payload" in response.json()["detail"]

    def test_update_session_answers_at_specific_positions(self):
        # updating all session answers

        positions_and_answers = [
            [i, {"answer": [0, 2]}] for i in range(0, len(self.session_answers))
        ]

        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=positions_and_answers,
        )
        assert response.status_code == 200

        for session_answer_position_index, session_answer_obj in positions_and_answers:
            response = self.client.get(
                f"{session_answers.router.prefix}/{self.session_id}/{session_answer_position_index}"
            )
            session_answer = json.loads(response.content)

            # ensure that `answer` has been updated at the specified positions
            assert session_answer["answer"] == session_answer_obj["answer"]

            # ensure that `visited` is not affected
            assert (
                session_answer["visited"]
                == self.session_answers[session_answer_position_index]["visited"]
            )
