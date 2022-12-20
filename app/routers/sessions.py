from fastapi import APIRouter, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
import pymongo
from database import client
from schemas import EventType
from models import (
    Event,
    Session,
    SessionAnswer,
    SessionResponse,
    UpdateSession,
    UpdateSessionResponse,
)
from datetime import datetime


def str_to_datetime(datetime_str: str) -> datetime:
    """converts string to datetime format"""
    return datetime.fromisoformat(datetime_str)


router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.post("/", response_model=SessionResponse)
async def create_session(session: Session):
    current_session = jsonable_encoder(session)

    quiz = client.quiz.quizzes.find_one({"_id": current_session["quiz_id"]})

    if quiz is None:
        raise HTTPException(
            status_code=404, detail=f"quiz {current_session['quiz_id']} not found"
        )

    # try to get the previous two sessions of a user+quiz pair if they exist
    previous_two_sessions = list(
        client.quiz.sessions.find(
            {
                "quiz_id": current_session["quiz_id"],
                "user_id": current_session["user_id"],
            },
            sort=[("_id", pymongo.DESCENDING)],
            limit=2,
        )
    )
    last_session, second_last_session = None, None
    # only one session exists
    if len(previous_two_sessions) == 1:
        last_session = previous_two_sessions[0]
    # two previous sessions exist
    elif len(previous_two_sessions) == 2:
        last_session, second_last_session = previous_two_sessions  # unpack

    session_answers = []
    if last_session is None:
        current_session["is_first"] = True
        if quiz["time_limit"] is not None:
            current_session["time_remaining"] = quiz["time_limit"][
                "max"
            ]  # ignoring min for now

        if "question_sets" in quiz and quiz["question_sets"]:
            question_ids = []
            for question_set_index, question_set in enumerate(quiz["question_sets"]):
                for question_index, question in enumerate(question_set["questions"]):
                    question_ids.append(question["_id"])

            if question_ids:
                for question_id in question_ids:
                    session_answers.append(
                        jsonable_encoder(
                            SessionAnswer.parse_obj({"question_id": question_id})
                        )
                    )
    else:
        condition_to_return_last_session = (
            # checking "events" key for backward compatibility
            "events" in last_session
            and (
                # no event has occurred in any session (quiz has not started)
                len(last_session["events"]) == 0
                or (
                    # ensure second_last_session is there and
                    # no event occurred in last session (as compared to second_last_session
                    second_last_session is not None
                    and len(last_session["events"])
                    == len(second_last_session["events"])
                )
            )
        )

        if condition_to_return_last_session is True:
            return JSONResponse(
                status_code=status.HTTP_201_CREATED, content=last_session
            )

        # we reach here because some meaningful event (start/resume/end) has occurred in last_session
        # so, we HAVE to distinguish between current_session and last_session by creating
        # a new session for current_session
        current_session["is_first"] = False
        current_session["events"] = last_session.get("events", [])
        current_session["time_remaining"] = last_session.get("time_remaining", None)
        current_session["has_quiz_ended"] = last_session.get("has_quiz_ended", False)

        # restore the answers from the last (previous) sessions
        last_session_answers = list(
            client.quiz.session_answers.find(
                {"session_id": last_session["_id"]},
                sort=[("_id", pymongo.ASCENDING)],
            )
        )

        for index, session_answer in enumerate(last_session_answers):
            # note: we retain created_at key in session_answer
            for key in ["_id", "session_id"]:
                session_answer.pop(key)

            # append with new session_answer "_id" keys
            session_answers.append(
                jsonable_encoder(SessionAnswer.parse_obj(session_answer))
            )

    current_session["session_answers"] = session_answers

    # insert current session into db
    new_session = client.quiz.sessions.insert_one(current_session)
    created_session = client.quiz.sessions.find_one({"_id": new_session.inserted_id})

    # update with new session_id and insert to db
    for index, _ in enumerate(session_answers):
        session_answers[index]["session_id"] = new_session.inserted_id

    client.quiz.session_answers.insert_many(session_answers)

    # return the created session
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=created_session)


@router.patch("/{session_id}", response_model=UpdateSessionResponse)
async def update_session(session_id: str, session_updates: UpdateSession):
    """
    session is updated whenever
    * start button is clicked (start-quiz event)
    * resume button is clicked (resume-quiz event)
    * end button is clicked (end-quiz event)
    * dummy event logic added for JNV -- will be removed!
    """
    new_event = jsonable_encoder(session_updates)["event"]

    # if new_event == EventType.dummy_event:
    #     return JSONResponse(
    #         status_code=status.HTTP_200_OK, content={"time_remaining": None}
    #     )

    session = client.quiz.sessions.find_one({"_id": session_id})
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session {session_id} not found",
        )

    event_obj = jsonable_encoder(Event.parse_obj({"event_type": new_event}))
    if session["events"] is None:
        session["events"] = [event_obj]
    else:
        session["events"].append(event_obj)

    # diff between times of last two events
    time_elapsed = 0
    if new_event not in [EventType.start_quiz, EventType.dummy_event]:
        # time_elapsed = 0 for start-quiz event
        if len(session["events"]) >= 2:
            # [sanity check] ensure atleast two events have occured before computing elapsed time
            # time_elapsed = (
            #     str_to_datetime(session["events"][-1]["created_at"])
            #     - str_to_datetime(session["events"][-2]["created_at"])
            # ).seconds

            # only for jnv enable -- remove later!
            # subtract times of last dummy event and last non dummy event
            dummy_found = False
            last_dummy_event, last_non_dummy_event = None, None
            for ev in session["events"][::-1][1:]:
                if not dummy_found and ev["event_type"] == EventType.dummy_event:
                    last_dummy_event = ev
                    dummy_found = True
                    continue

                if not dummy_found and ev["event_type"] != EventType.dummy_event:
                    # two quick non-dummy events, ignore -- remove this after JNV enable!
                    break

                if dummy_found and ev["event_type"] != EventType.dummy_event:
                    last_non_dummy_event = ev
                    break

            if dummy_found:
                time_elapsed = (
                    str_to_datetime(last_dummy_event["created_at"])
                    - str_to_datetime(last_non_dummy_event["created_at"])
                ).seconds
            else:
                # if no dummy event at all!
                time_elapsed = (
                    str_to_datetime(session["events"][-1]["created_at"])
                    - str_to_datetime(session["events"][-2]["created_at"])
                ).seconds

    response_content = {}
    # added check for dummy event; dont update time_remaining for it
    if (
        new_event != EventType.dummy_event
        and "time_remaining" in session
        and session["time_remaining"] is not None
    ):
        # if `time_remaining` key is not present =>
        # no time limit is set, no need to respond with time_remaining
        session["time_remaining"] = max(0, session["time_remaining"] - time_elapsed)
        response_content = {"time_remaining": session["time_remaining"]}

    # update the document in the sessions collection
    if new_event == EventType.end_quiz:
        session["has_quiz_ended"] = True
    client.quiz.sessions.update_one(
        {"_id": session_id}, {"$set": jsonable_encoder(session)}
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content=response_content)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    if (session := client.quiz.sessions.find_one({"_id": session_id})) is not None:
        return session

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"session {session_id} not found"
    )
