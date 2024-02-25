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


@router.post("/", response_model=SessionResponse)
async def create_session(session: Session):
    logger.info(
        f"Creating new session for user: {session.user_id} and quiz: {session.quiz_id}"
    )
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
            logger.error(error_message)
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
        # cache_data(previous_two_session_ids_cache_key, [s["_id"] for s in previous_two_sessions])
        # [cache_data(f"session_{previous_two_sessions[i]['_id']}", previous_two_sessions[i]) for i in range(len(previous_two_sessions))]

        if len(previous_two_sessions) == 0:
            pass
        elif len(previous_two_sessions) == 1:
            logger.info(f"xxx caching previous two sessions for user: {current_session['user_id']} and quiz: {current_session['quiz_id']}, session ids: {previous_two_sessions[0]['_id']} in create_session at line 76")
            cache_data(
                previous_two_session_ids_cache_key, 
                [previous_two_sessions[0]["_id"]]
            )
            logger.info(f"xxx caching session_{previous_two_sessions[0]['_id']} in create_session at line 81")
            cache_data(f"session_{previous_two_sessions[0]['_id']}", previous_two_sessions[0])
        elif len(previous_two_sessions) == 2:
            logger.info(f"xxx caching previous two sessions for user: {current_session['user_id']} and quiz: {current_session['quiz_id']}, session ids: {previous_two_sessions[0]['_id']} and {previous_two_sessions[1]['_id']} in create_session at line 84")
            cache_data(
                previous_two_session_ids_cache_key, 
                [
                    previous_two_sessions[0]["_id"],
                    previous_two_sessions[1]["_id"]
                ]
            )
            logger.info(f"xxx caching session_{previous_two_sessions[0]['_id']} in create_session at line 92")
            cache_data(f"session_{previous_two_sessions[0]['_id']}", previous_two_sessions[0])
            logger.info(f"xxx caching session_{previous_two_sessions[1]['_id']} in create_session at line 94")
            cache_data(f"session_{previous_two_sessions[1]['_id']}", previous_two_sessions[1])
    else:
        previous_two_sessions = [get_cached_data(f"session_{sid}") for sid in cached_previous_two_session_ids]

    last_session, second_last_session = None, None
    # only one session exists
    if len(previous_two_sessions) == 1:
        logger.info("Only one previous session exists for this user-quiz combo")
        last_session = previous_two_sessions[0]
        # cache_data(
        #     previous_two_session_ids_cache_key,
        #     [last_session["_id"]]
        # )
        # cache_data(f"session_{last_session['_id']}", last_session)
    # two previous sessions exist
    elif len(previous_two_sessions) == 2:
        logger.info("Two previous sessions exists for this user-quiz combo")
        last_session, second_last_session = previous_two_sessions  # unpack
        # cache_data(
        #     previous_two_session_ids_cache_key,
        #     [last_session["_id"], second_last_session["_id"]]
        # )
        # cache_data(f"session_{last_session['_id']}", last_session)
        # cache_data(f"session_{second_last_session['_id']}", second_last_session)

    session_answers = []
    if last_session is None:
        logger.info("No previous session exists for this user-quiz combo")
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
            logger.info(
                f"No meaningful event has occurred in last_session. Returning this session which has id {last_session['_id']}"
            )
            return JSONResponse(
                status_code=status.HTTP_201_CREATED, content=last_session
            )

        # we reach here because some meaningful event (start/resume/end) has occurred in last_session
        # so, we HAVE to distinguish between current_session and last_session by creating
        # a new session for current_session
        logger.info(
            f"Some meaningful event has occurred in last_session, creating new session for user: {session.user_id} and quiz: {session.quiz_id}"
        )
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

    logger.info(f"xxx caching session_id_to_insert_{current_session['_id']} in create_session at line 189")
    cache_data(f"session_id_to_insert_{current_session['_id']}", "x")
    logger.info(f"xxx caching session_{current_session['_id']} in create_session at line 191")
    cache_data(f"session_{current_session['_id']}", current_session)
    if previous_two_sessions is None or len(previous_two_sessions) == 0:
        logger.info(f"xxx caching previous two sessions for user: {current_session['user_id']} and quiz: {current_session['quiz_id']}, session ids: {current_session['_id']} in create_session at line 194")
        cache_data(
            previous_two_session_ids_cache_key, 
            [current_session["_id"]]
        )
    elif len(previous_two_sessions) == 1 or len(previous_two_sessions) == 2:
        logger.info(f"xxx caching previous two sessions for user: {current_session['user_id']} and quiz: {current_session['quiz_id']}, session ids: {current_session['_id']} and {last_session['_id']} in create_session at line 200")
        cache_data(
            previous_two_session_ids_cache_key, 
            [
                current_session["_id"],
                last_session["_id"]
            ]
        )
        if len(previous_two_sessions) == 2:
            # send to db then invalidate
            result = client.quiz.sessions.replace_one(
                {"_id": second_last_session["_id"]}, second_last_session, upsert=True
            )
            if result.acknowledged:
                logger.info(
                    f"Sent session with id {second_last_session['_id']} for user: {session.user_id} and quiz: {session.quiz_id} to the db"
                )
                logger.info(f"yyy invalidating cache for session with id {second_last_session['_id']} in create_session at line 217")
                invalidate_cache(f"session_{second_last_session['_id']}")
                # if this session was created in cache itself, then invalidate it
                if get_cached_data(f"session_id_to_insert_{second_last_session['_id']}") is not None:
                    logger.info(f"yyy invalidating cache for session_id_to_insert_{second_last_session['_id']} in create_session at line 221")
                    invalidate_cache(f"session_id_to_insert_{second_last_session['_id']}")
                logger.info(f"invalidated cache for session with id {second_last_session['_id']}")
            else:
                log_message = f"Failed to insert second last session with id {second_last_session['_id']} for user: {session.user_id} and quiz: {session.quiz_id} to db"
                logger.error(log_message)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=log_message,
                )

    logger.info(
        f"InCache: Created new session for user: {session.user_id} and quiz: {session.quiz_id}"
    )

    # result = client.quiz.sessions.insert_one(current_session)
    # if result.acknowledged:
    #     logger.info(
    #         f"Created new session with id {result.inserted_id} for user: {session.user_id} and quiz: {session.quiz_id}"
    #     )
    # else:
    #     logger.error(
    #         f"Failed to insert new session for user: {session.user_id} and quiz: {session.quiz_id}"
    #     )
    #     raise HTTPException(
    #         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #         detail="Failed to insert new session",
    #     )

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
            logger.error(
                f"Received session update request, but session_id {session_id} not found"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"session {session_id} not found",
            )
        logger.info(f"xxx caching session_{session_id} in update_session at line 286")
        cache_data(f"session_{session_id}", session)

    
    user_id, quiz_id = session["user_id"], session["quiz_id"]
    log_message += f", for user: {user_id} and quiz: {quiz_id}"
    logger.info(log_message)

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
    logger.info(f"xxx caching session_{session_id} in update_session at line 390")
    cache_data(f"session_{session_id}", session)
    if (get_cached_data(f"session_id_to_insert_{session_id}") is None):
        logger.info(f"xxx caching session_id_to_update_{session_id} in update_session at line 393")
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

    logger.info(
        f"InCache: Updated session with id {session_id} for user: {user_id} and quiz: {quiz_id}"
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=response_content)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    logger.info(f"Fetching session with id {session_id}")
    session = None
    cached_session = get_cached_data(f"session_{session_id}")
    if cached_session:
        session = cached_session
        logger.info(f"InCache: Found session with id {session_id}")
    else:
        logger.info(f"Session with id {session_id} not found in cache")
        session = client.quiz.sessions.find_one({"_id": session_id})
        if session is None:
            logger.error(f"Session {session_id} not found in db")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"session {session_id} not found"
            )
        logger.info(f"xxx caching session_{session_id} in get_session at line 427")
        cache_data(f"session_{session_id}", session)
    
    logger.info(f"InCache: Found session with id {session_id}")
    return session