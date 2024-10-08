import json
from .base import SessionsBaseTestCase
from ..routers import quizzes, sessions, session_answers
from ..schemas import EventType
from datetime import datetime
import time


class SessionsTestCase(SessionsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.homework_session_id = self.homework_session["_id"]
        self.timed_quiz_session_id = self.timed_quiz_session["_id"]

    def test_gets_session_with_valid_id(self):
        response = self.client.get(
            f"{sessions.router.prefix}/{self.homework_session_id}"
        )
        assert response.status_code == 200
        session = response.json()
        for key in ["quiz_id", "user_id", "omr_mode"]:
            assert session[key] == self.homework_session[key]

    def test_get_session_returns_error_if_id_invalid(self):
        response = self.client.get(f"{sessions.router.prefix}/00")
        assert response.status_code == 404
        response = response.json()
        assert response["detail"] == "session 00 not found"

    def test_update_session(self):
        payload = {"event": EventType.start_quiz.value}
        response = self.client.patch(
            f"{sessions.router.prefix}/{self.homework_session_id}", json=payload
        )
        payload = {"event": EventType.end_quiz.value}
        response = self.client.patch(
            f"{sessions.router.prefix}/{self.homework_session_id}", json=payload
        )
        assert response.status_code == 200
        response = self.client.get(
            f"{sessions.router.prefix}/{self.homework_session_id}"
        )
        session = response.json()

        # ensure that `has_quiz_ended` has been updated
        assert session["events"][-1]["event_type"] == EventType.end_quiz
        assert session["has_quiz_ended"] is True

    def test_create_session_with_invalid_quiz_id(self):
        response = self.client.post(
            sessions.router.prefix + "/", json={"quiz_id": "00", "user_id": 1}
        )
        assert response.status_code == 404
        response = response.json()
        assert (
            response["detail"] == "Quiz/Review 00 not found while creating the session"
        )

    def test_create_session_with_valid_quiz_id_and_first_session(self):
        data = open("app/tests/dummy_data/homework_quiz.json")
        quiz_data = json.load(data)
        response = self.client.post(quizzes.router.prefix + "/", json=quiz_data)
        quiz_id = json.loads(response.content)["id"]
        quiz = self.client.get(quizzes.router.prefix + f"/{quiz_id}").json()
        response = self.client.post(
            sessions.router.prefix + "/", json={"quiz_id": quiz["_id"], "user_id": 1}
        )
        assert response.status_code == 201
        session = json.loads(response.content)
        assert session["is_first"] is True
        assert len(session["session_answers"]) == sum(
            len(qset["questions"]) for qset in quiz_data["question_sets"]
        )

    def test_create_session_with_previous_session_and_no_event(self):
        # second session with no start-quiz event in first session
        response = self.client.post(
            sessions.router.prefix + "/",
            json={"quiz_id": self.timed_quiz["_id"], "user_id": 1},
        ).json()

        assert len(response["events"]) == 0
        assert response["is_first"] is True
        assert response["omr_mode"] is False

    def test_create_session_with_previous_session_and_change_in_omr_mode(self):
        # second session with no start-quiz event in first session
        # but with a different omr_mode value
        response = self.client.post(
            sessions.router.prefix + "/",
            json={"quiz_id": self.timed_quiz["_id"], "user_id": 1, "omr_mode": True},
        ).json()

        assert len(response["events"]) == 0
        assert response["is_first"] is True
        assert response["omr_mode"] is True
        # despite change in omr_mode, since no event has occurred, same session is returned

    def test_create_session_with_previous_session_and_start_event(self):
        session_updates = {"event": EventType.start_quiz.value}
        response = self.client.patch(
            f"{sessions.router.prefix}/{self.timed_quiz_session_id}",
            json=session_updates,
        )
        # second session with start-quiz event in first session
        response = self.client.post(
            sessions.router.prefix + "/",
            json={"quiz_id": self.timed_quiz["_id"], "user_id": 1},
        ).json()

        assert len(response["events"]) > 0
        assert response["is_first"] is False

    def test_create_session_with_valid_quiz_id_and_previous_session(self):
        self.session_id = self.homework_session["_id"]
        self.session_answers = self.homework_session["session_answers"]
        self.session_answer_position_index = 0
        self.session_answer = self.session_answers[0]
        self.session_answer_id = self.session_answer["_id"]
        new_answer = [0, 1, 2]
        response = self.client.patch(
            f"{session_answers.router.prefix}/{self.session_id}/{self.session_answer_position_index}",
            json={"answer": new_answer},
        )
        response = self.client.post(
            sessions.router.prefix + "/",
            json={
                "quiz_id": self.homework_session["quiz_id"],
                "user_id": self.homework_session["user_id"],
            },
        )
        assert response.status_code == 201
        session = json.loads(response.content)
        assert session["has_quiz_ended"] is False
        assert session["session_answers"][0]["answer"] == new_answer

    def test_time_remaining_for_first_session(self):
        quiz_id = self.timed_quiz_session["quiz_id"]
        quiz = self.client.get(quizzes.router.prefix + f"/{quiz_id}").json()
        assert self.timed_quiz_session["is_first"] is True
        assert self.timed_quiz_session["time_remaining"] == quiz["time_limit"]["max"]

    def test_quiz_start_time_key_after_start_event(self):
        session_updates = {"event": EventType.start_quiz.value}
        response = self.client.patch(
            f"{sessions.router.prefix}/{self.timed_quiz_session_id}",
            json=session_updates,
        )

        quiz_id = self.timed_quiz_session["quiz_id"]
        quiz = self.client.get(quizzes.router.prefix + f"/{quiz_id}").json()

        assert "time_remaining" in json.loads(response.content)
        assert (
            json.loads(response.content)["time_remaining"] == quiz["time_limit"]["max"]
        )

        updated_session = self.client.get(
            f"{sessions.router.prefix}/{self.timed_quiz_session_id}"
        ).json()

        assert updated_session["events"][0]["event_type"] == EventType.start_quiz
        assert (
            datetime.fromisoformat(updated_session["events"][0]["created_at"])
            < datetime.utcnow()
        )  # should be comparable

        assert updated_session["time_remaining"] == quiz["time_limit"]["max"]

    def test_time_remaining_in_new_session_with_quiz_start(self):
        # second session -- quiz hasn't started in first session
        response = self.client.post(
            sessions.router.prefix + "/",
            json={"quiz_id": self.timed_quiz["_id"], "user_id": 1},
        )
        session = json.loads(response.content)
        session_id = session["_id"]

        # first update, quiz started
        session_updates = {"event": EventType.start_quiz.value}
        response = self.client.patch(
            f"{sessions.router.prefix}/{session_id}", json=session_updates
        )

        quiz_id = self.timed_quiz_session["quiz_id"]
        quiz = self.client.get(quizzes.router.prefix + f"/{quiz_id}").json()

        # is the same as max, because quiz started in this second session
        assert (
            json.loads(response.content)["time_remaining"] == quiz["time_limit"]["max"]
        )

        updated_session = self.client.get(
            f"{sessions.router.prefix}/{session_id}"
        ).json()

        assert updated_session["events"][0]["event_type"] == EventType.start_quiz
        assert (
            datetime.fromisoformat(updated_session["events"][0]["created_at"])
            < datetime.utcnow()
        )  # should be comparable

        assert updated_session["time_remaining"] == quiz["time_limit"]["max"]

    def test_time_remaining_in_new_session_with_quiz_resume(self):
        # start quiz in first session
        session_updates = {"event": EventType.start_quiz.value}
        response = self.client.patch(
            f"{sessions.router.prefix}/{self.timed_quiz_session_id}",
            json=session_updates,
        )

        # same user+quiz opens new session
        response = self.client.post(
            sessions.router.prefix + "/",
            json={"quiz_id": self.timed_quiz["_id"], "user_id": 1},
        )
        resumed_session = json.loads(response.content)
        resumed_session_id = resumed_session["_id"]

        time.sleep(2)  # wait for few seconds
        # click resume quiz now
        session_updates = {"event": EventType.resume_quiz.value}
        response = self.client.patch(
            f"{sessions.router.prefix}/{resumed_session_id}", json=session_updates
        )

        quiz_id = self.timed_quiz_session["quiz_id"]
        quiz = self.client.get(quizzes.router.prefix + f"/{quiz_id}").json()

        updated_resumed_session = self.client.get(
            f"{sessions.router.prefix}/{resumed_session_id}"
        ).json()

        # because time has passed between both sessions
        assert updated_resumed_session["time_remaining"] < quiz["time_limit"]["max"]

    def test_two_or_more_successive_dummy_events_squashed_to_one(self):
        # start quiz
        session_updates = {"event": EventType.start_quiz.value}
        response = self.client.patch(
            f"{sessions.router.prefix}/{self.timed_quiz_session_id}",
            json=session_updates,
        )
        # wait for 2 seconds
        time.sleep(2)
        # send a dummy event
        session_updates = {"event": EventType.dummy_event.value}
        response = self.client.patch(
            f"{sessions.router.prefix}/{self.timed_quiz_session_id}",
            json=session_updates,
        )
        # wait for 2 seconds
        time.sleep(2)
        # send another dummy event
        session_updates = {"event": EventType.dummy_event.value}
        response = self.client.patch(
            f"{sessions.router.prefix}/{self.timed_quiz_session_id}",
            json=session_updates,
        )
        # wait for 2 seconds
        time.sleep(2)
        # send third dummy event
        session_updates = {"event": EventType.dummy_event.value}
        response = self.client.patch(
            f"{sessions.router.prefix}/{self.timed_quiz_session_id}",
            json=session_updates,
        )

        # resume session now with same user+quiz id
        response = self.client.post(
            sessions.router.prefix + "/",
            json={"quiz_id": self.timed_quiz["_id"], "user_id": 1},
        )
        resumed_session = json.loads(response.content)

        # the event array should now be [start-quiz, dummy-event]
        # instead of [start-quiz, dummy-event, dummy-event, dummy-event]
        assert len(resumed_session["events"]) == 2
