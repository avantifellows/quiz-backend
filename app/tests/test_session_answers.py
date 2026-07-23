import json
from unittest.mock import patch
from bson import ObjectId
from pymongo.collection import Collection
from database import client as db_client
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

    # --- US-003: Lightweight aggregation read path ---

    def test_batch_update_out_of_bounds_position_returns_400(self):
        """Position greater than session_answers length returns 400 via aggregation num_answers."""
        out_of_bounds = len(self.session_answers) + 1
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=[[out_of_bounds, {"answer": [0]}]],
        )
        assert response.status_code == 400
        assert "out of bounds" in response.json()["detail"]

    def test_batch_update_session_not_found_returns_404(self):
        """Nonexistent session returns 404 through aggregation read path."""
        response = self.client.patch(
            f"{session_answers.router.prefix}/nonexistent-session-id/update-multiple-answers",
            json=[[0, {"answer": [0]}]],
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_batch_update_preserves_user_and_quiz_logging_context(self):
        """Aggregation read path still retrieves user_id and quiz_id for logging."""
        # A successful batch update proves user_id and quiz_id were retrieved
        # (the endpoint would fail with KeyError if they were missing from the projection)
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=[[0, {"answer": [0, 1]}]],
        )
        assert response.status_code == 200

    # --- US-004: Post-read bounds checking with off-by-one fix ---

    def test_batch_update_position_equal_to_length_returns_400(self):
        """Position == len(session_answers) returns 400 (off-by-one fix: >= not >)."""
        exact_length = len(self.session_answers)
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=[[exact_length, {"answer": [0]}]],
        )
        assert response.status_code == 400
        assert "out of bounds" in response.json()["detail"]

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
        from database import client

        exact_length = len(self.session_answers)
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/update-multiple-answers",
            json=[[exact_length, {"answer": [0]}]],
        )
        assert response.status_code == 400

        # Verify array was not extended
        session = client.quiz.sessions.find_one({"_id": self.session_id})
        assert len(session["session_answers"]) == exact_length

    # --- US-005: Malformed session_answers test coverage ---

    def test_batch_update_missing_session_answers_field_returns_404(self):
        """Session document with no session_answers field returns 404."""
        doc_id = str(ObjectId())
        db_client.quiz.sessions.insert_one(
            {"_id": doc_id, "user_id": "test_user", "quiz_id": "test_quiz"}
        )
        self.addCleanup(lambda: db_client.quiz.sessions.delete_one({"_id": doc_id}))

        response = self.client.patch(
            f"{session_answers.router.prefix}/{doc_id}/update-multiple-answers",
            json=[[0, {"answer": [0]}]],
        )
        assert response.status_code == 404
        assert "No session answers found" in response.json()["detail"]

    def test_batch_update_null_session_answers_returns_404(self):
        """Session document with session_answers: None returns 404."""
        doc_id = str(ObjectId())
        db_client.quiz.sessions.insert_one(
            {
                "_id": doc_id,
                "user_id": "test_user",
                "quiz_id": "test_quiz",
                "session_answers": None,
            }
        )
        self.addCleanup(lambda: db_client.quiz.sessions.delete_one({"_id": doc_id}))

        response = self.client.patch(
            f"{session_answers.router.prefix}/{doc_id}/update-multiple-answers",
            json=[[0, {"answer": [0]}]],
        )
        assert response.status_code == 404
        assert "No session answers found" in response.json()["detail"]

    def test_batch_update_non_array_session_answers_returns_404(self):
        """Session document with non-array session_answers (e.g., 'corrupted') returns 404."""
        doc_id = str(ObjectId())
        db_client.quiz.sessions.insert_one(
            {
                "_id": doc_id,
                "user_id": "test_user",
                "quiz_id": "test_quiz",
                "session_answers": "corrupted",
            }
        )
        self.addCleanup(lambda: db_client.quiz.sessions.delete_one({"_id": doc_id}))

        response = self.client.patch(
            f"{session_answers.router.prefix}/{doc_id}/update-multiple-answers",
            json=[[0, {"answer": [0]}]],
        )
        assert response.status_code == 404
        assert "No session answers found" in response.json()["detail"]

    # --- US-006: Single-item PATCH — validation tightening ---

    def test_single_update_negative_index_returns_400(self):
        """Negative position_index returns 400 (pre-DB validation)."""
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/-1",
            json={"answer": [0]},
        )
        assert response.status_code == 400
        assert "negative" in response.json()["detail"]

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

    def test_single_update_empty_payload_returns_400(self):
        """Empty payload (zero business fields in __fields_set__) returns 400."""
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/{self.session_answer_position_index}",
            json={},
        )
        assert response.status_code == 400
        assert "Empty payload" in response.json()["detail"]

    def test_single_update_empty_payload_rejected_before_db_read(self):
        """Empty payload is rejected before any DB read (nonexistent session)."""
        response = self.client.patch(
            f"{session_answers.router.prefix}/nonexistent-session-id/0",
            json={},
        )
        assert response.status_code == 400
        assert "Empty payload" in response.json()["detail"]

    def test_single_update_negative_index_rejected_before_db_read(self):
        """Negative index is rejected before any DB read (nonexistent session)."""
        response = self.client.patch(
            f"{session_answers.router.prefix}/nonexistent-session-id/-1",
            json={"answer": [0]},
        )
        assert response.status_code == 400
        assert "negative" in response.json()["detail"]

    def test_single_update_validation_order_empty_before_negative(self):
        """Empty payload check fires before negative index check."""
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/-1",
            json={},
        )
        assert response.status_code == 400
        # Empty payload message, not negative — validates ordering
        assert "Empty payload" in response.json()["detail"]

    # --- US-007: Spy test — prove lightweight read is used ---

    def test_batch_update_uses_aggregate_not_find_one(self):
        """Prove the batch endpoint uses aggregation instead of find_one for the read path."""
        # Create a minimal session via direct insert (bypasses BaseTestCase setup
        # to avoid unrelated DB calls that would confuse spy assertions)
        doc_id = str(ObjectId())
        db_client.quiz.sessions.insert_one(
            {
                "_id": doc_id,
                "user_id": "spy_test_user",
                "quiz_id": "spy_test_quiz",
                "session_answers": [
                    {"question_id": "q1", "answer": None, "visited": False}
                ],
            }
        )
        self.addCleanup(lambda: db_client.quiz.sessions.delete_one({"_id": doc_id}))

        # Patch at CLASS level — pymongo Database.__getitem__ returns a NEW
        # Collection object on every access, so instance-level patching would
        # miss the router's Collection instance.
        # Use plain function replacements as spies (wraps= doesn't work at
        # class level because the mock doesn't forward self to the unbound method).
        original_find_one = Collection.find_one
        original_aggregate = Collection.aggregate
        find_one_called = False
        aggregate_called = False

        def spy_find_one(self_col, *args, **kwargs):
            nonlocal find_one_called
            find_one_called = True
            return original_find_one(self_col, *args, **kwargs)

        def spy_aggregate(self_col, *args, **kwargs):
            nonlocal aggregate_called
            aggregate_called = True
            return original_aggregate(self_col, *args, **kwargs)

        with patch.object(Collection, "find_one", spy_find_one), patch.object(
            Collection, "aggregate", spy_aggregate
        ):
            response = self.client.patch(
                f"{session_answers.router.prefix}/{doc_id}/update-multiple-answers",
                json=[[0, {"answer": [1, 2]}]],
            )
            assert response.status_code == 200

            # The batch endpoint must use aggregate (lightweight read), not find_one
            assert (
                not find_one_called
            ), "find_one should not be called — batch endpoint should use aggregate"
            assert (
                aggregate_called
            ), "aggregate should be called for the lightweight read path"

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
