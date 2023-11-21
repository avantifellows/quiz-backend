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
