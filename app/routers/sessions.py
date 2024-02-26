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
from logger_config import get_logger
from cache import cache_data, get_cached_data, get_cached_data_local, cache_data_local, invalidate_cache


def str_to_datetime(datetime_str: str) -> datetime:
    """converts string to datetime format"""
    return datetime.fromisoformat(datetime_str)


router = APIRouter(prefix="/sessions", tags=["Sessions"])
logger = get_logger()
MAX_SESSIONS_TO_CACHE_FOR_A_USER_QUIZ_PAIR = 5

@router.post("/", response_model=SessionResponse)
async def create_session(session: Session):
    log_message = f"New session for user: {session.user_id} and quiz: {session.quiz_id}"
    current_session = jsonable_encoder(session)
    # get quiz from cache or db
    quiz = None
    quiz_cache_key = f"quiz_{current_session['quiz_id']}"
    cached_quiz = get_cached_data_local(quiz_cache_key)
    if not cached_quiz:
        quiz = client.quiz.quizzes.find_one({"_id": current_session["quiz_id"]})
        if quiz is None:
            error_message = (
                f"Quiz {current_session['quiz_id']} not found while creating the session"
            )
            logger.error(log_message + " " + error_message)
            raise HTTPException(
                status_code=404,
                detail=error_message,
            )
        cache_data_local(quiz_cache_key, quiz)
    else:
        quiz = cached_quiz

    # try to get the previous two sessions of a user+quiz pair if they exist
    previous_two_sessions = None
    previous_two_session_ids_cache_key = f"previous_two_session_ids_{current_session['user_id']}_{current_session['quiz_id']}"
    cached_previous_two_session_ids = get_cached_data(previous_two_session_ids_cache_key)
    if cached_previous_two_session_ids is None:
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

        if len(previous_two_sessions) == 0:
            pass
        elif len(previous_two_sessions) == 1:
            cache_data(
                previous_two_session_ids_cache_key, 
                [previous_two_sessions[0]["_id"]]
            )
            cache_data(f"session_{previous_two_sessions[0]['_id']}", previous_two_sessions[0])
        elif len(previous_two_sessions) == 2:
            cache_data(
                previous_two_session_ids_cache_key, 
                [
                    previous_two_sessions[0]["_id"],
                    previous_two_sessions[1]["_id"]
                ]
            )
            cache_data(f"session_{previous_two_sessions[0]['_id']}", previous_two_sessions[0])
            cache_data(f"session_{previous_two_sessions[1]['_id']}", previous_two_sessions[1])
    else:
        previous_two_sessions = [get_cached_data(f"session_{sid}") for sid in cached_previous_two_session_ids]

    last_session, second_last_session = None, None
    # only one session exists
    if len(previous_two_sessions) == 1:
        log_message += f", only one previous session exists for this user-quiz combo"
        last_session = previous_two_sessions[0]
    # two previous sessions exist
    elif len(previous_two_sessions) == 2:
        log_message += f", two previous sessions exist for this user-quiz combo"
        last_session, second_last_session = previous_two_sessions  # unpack

    session_answers = []
    if last_session is None:
        log_message += f", no previous session exists for this user-quiz combo"
        current_session["is_first"] = True
        if quiz["time_limit"] is not None:
            current_session["time_remaining"] = quiz["time_limit"][
                "max"
            ]  # ignoring min for now

        if "question_sets" in quiz and quiz["question_sets"]:
            for question_set_index, question_set in enumerate(quiz["question_sets"]):
                for question_index, question in enumerate(question_set["questions"]):
                    session_answers.append(
                        jsonable_encoder(
                            SessionAnswer.parse_obj({"question_id": question["_id"]})
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
            log_message += f", no meaningful event has occurred in last_session. Returning session with id {last_session['_id']}"
            logger.info(log_message)
            return JSONResponse(
                status_code=status.HTTP_201_CREATED, content=last_session
            )

        # we reach here because some meaningful event (start/resume/end) has occurred in last_session
        # so, we HAVE to distinguish between current_session and last_session by creating
        # a new session for current_session
        log_message += f", some meaningful event has occurred in last_session, creating new session"
        current_session["is_first"] = False
        current_session["events"] = last_session.get("events", [])
        current_session["time_remaining"] = last_session.get("time_remaining", None)
        current_session["has_quiz_ended"] = last_session.get("has_quiz_ended", False)

        # restore the answers from the last (previous) sessions
        session_answers_of_the_last_session = last_session["session_answers"]

        for _, session_answer in enumerate(session_answers_of_the_last_session):
            # note: we retain created_at key in session_answer
            for key in ["_id", "session_id"]:
                if key in session_answer:
                    session_answer.pop(key)

            # append with new session_answer "_id" keys
            session_answers.append(
                jsonable_encoder(SessionAnswer.parse_obj(session_answer))
            )

    current_session["session_answers"] = session_answers

    cache_data(f"session_id_to_insert_{current_session['_id']}", "x")
    cache_data(f"session_{current_session['_id']}", current_session)

    previous_two_sessions.insert(0, current_session)
    if len(previous_two_sessions) > MAX_SESSIONS_TO_CACHE_FOR_A_USER_QUIZ_PAIR:
        # send to db then invalidate
        _session = previous_two_sessions[-1]
        _session_id = _session["_id"]
        result = client.quiz.sessions.replace_one(
            {"_id": _session_id}, _session, upsert=True
        )
        if result.acknowledged:
            previous_two_sessions.pop()
            invalidate_cache(f"session_{_session_id}")
            # if this session was created in cache itself, then invalidate it
            if get_cached_data(f"session_id_to_insert_{_session_id}") is not None:
                invalidate_cache(f"session_id_to_insert_{_session_id}")
        else:
            log_message += f", failed to insert last session with id {_session_id} to db"
            logger.error(log_message)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=log_message,
            )
    
    cache_data(
        previous_two_session_ids_cache_key, 
        [s["_id"] for s in previous_two_sessions]
    )
    log_message += f", created new session with id {current_session['_id']}"
    logger.info(log_message)
    # return the created session
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=current_session)


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
    log_message = f"Updating session with id {session_id} and event {new_event}"
    session_update_query = {}

    # if new_event == EventType.dummy_event:
    #     return JSONResponse(
    #         status_code=status.HTTP_200_OK, content={"time_remaining": None}
    #     )

    session = None
    cached_session = get_cached_data(f"session_{session_id}")
    if cached_session:
        session = cached_session
    else:
        session = client.quiz.sessions.find_one({"_id": session_id})
        if session is None:
            log_message += f", session_id {session_id} not found in db"
            logger.error(log_message)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"session {session_id} not found",
            )

    
    log_message += f", for user: {session['user_id']} and quiz: {session['quiz_id']}"

    new_event_obj = jsonable_encoder(Event.parse_obj({"event_type": new_event}))
    if session["events"] is None:
        session["events"] = [new_event_obj]
        # if "$set" not in session_update_query:
        #     session_update_query["$set"] = {"events": [new_event_obj]}
        # else:
        #     session_update_query["$set"].update({"events": [new_event_obj]})
    else:
        if (
            new_event == EventType.dummy_event
            and session["events"][-1]["event_type"] == EventType.dummy_event
        ):
            # if previous event is dummy, just change the updated_at time of previous event
            last_event_index = len(session["events"]) - 1
            session["events"][last_event_index]["updated_at"] = new_event_obj["created_at"]
            # last_event_update_query = {
            #     "events."
            #     + str(last_event_index)
            #     + ".updated_at": new_event_obj["created_at"]
            # }
            # if "$set" not in session_update_query:
            #     session_update_query["$set"] = last_event_update_query
            # else:
            #     session_update_query["$set"].update(last_event_update_query)

        else:
            session["events"].append(new_event_obj)
            # if "$push" not in session_update_query:
            #     session_update_query["$push"] = {"events": new_event_obj}
            # else:
            #     session_update_query["$push"].update({"events": new_event_obj})

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

            # subtract times of last dummy event and last non dummy event
            dummy_found = False
            last_dummy_event, last_non_dummy_event = None, None
            for ev in session["events"][::-1][1:]:
                if not dummy_found and ev["event_type"] == EventType.dummy_event:
                    last_dummy_event = ev
                    dummy_found = True
                    continue

                if not dummy_found and ev["event_type"] != EventType.dummy_event:
                    # two quick non-dummy events, ignore
                    break

                if dummy_found and ev["event_type"] != EventType.dummy_event:
                    last_non_dummy_event = ev
                    break

            if dummy_found:
                time_elapsed = (
                    str_to_datetime(last_dummy_event["updated_at"])
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
        time_remaining = max(0, session["time_remaining"] - time_elapsed)
        session["time_remaining"] = time_remaining
        # if "$set" not in session_update_query:
        #     session_update_query["$set"] = {"time_remaining": time_remaining}
        # else:
        #     session_update_query["$set"].update({"time_remaining": time_remaining})
        response_content = {"time_remaining": time_remaining}

    # update the document in the sessions collection
    if new_event == EventType.end_quiz:
        session["has_quiz_ended"] = True
        # if "$set" not in session_update_query:
        #     session_update_query["$set"] = {"has_quiz_ended": True}
        # else:
        #     session_update_query["$set"].update({"has_quiz_ended": True})
    cache_data(f"session_{session_id}", session)
    if (get_cached_data(f"session_id_to_insert_{session_id}") is None):
        cache_data(f"session_id_to_update_{session_id}", "x")
    # update_result = client.quiz.sessions.update_one(
    #     {"_id": session_id}, session_update_query
    # )
    # if update_result.modified_count == 0:
    #     logger.error(f"Failed to update session with id {session_id}")
    #     raise HTTPException(
    #         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #         detail=f"Failed to update session with id {session_id}",
    #     )

    log_message += f", success!"
    logger.info(log_message)
    
    return JSONResponse(status_code=status.HTTP_200_OK, content=response_content)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    session = None
    cached_session = get_cached_data(f"session_{session_id}")
    if cached_session:
        session = cached_session
    else:
        session = client.quiz.sessions.find_one({"_id": session_id})
        if session is None:
            logger.error(f"Session {session_id} not found in db")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"session {session_id} not found"
            )
        cache_data(f"session_{session_id}", session)    
    return session