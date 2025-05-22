from fastapi import APIRouter, status, HTTPException
import random
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
from typing import Dict
from settings import Settings


def str_to_datetime(datetime_str: str) -> datetime:
    """converts string to datetime format"""
    return datetime.fromisoformat(datetime_str)


def shuffle_question_order(question_sets):
    question_order = []
    bucket_size = Settings().subset_size

    global_index = 0  # Track global index across all questions
    logger.info(question_sets)
    # Iterate over each question set
    for question_set in question_sets:
        total_questions = len(
            question_set["questions"]
        )  # Get total number of questions in the current set
        num_blocks = (
            total_questions + bucket_size - 1
        ) // bucket_size  # Equivalent to Math.ceil(total_questions / subset_size)

        # For each block (subset of questions)
        for block in range(num_blocks):
            # Get the start and end index for the current block
            start = block * bucket_size
            end = min(start + bucket_size, total_questions)
            block_indices = list(range(global_index, global_index + (end - start)))

            # Shuffle the current block using Fisher-Yates algorithm
            random.shuffle(block_indices)

            # Append the shuffled indices to question_order
            question_order.extend(block_indices)

            # Update global index for the next set of questions
            global_index += len(block_indices)

    return question_order


router = APIRouter(prefix="/sessions", tags=["Sessions"])
logger = get_logger()


@router.post("/", response_model=SessionResponse)
async def create_session(session: Session):
    logger.info(
        f"Creating new session for user: {session.user_id} and quiz: {session.quiz_id}"
    )
    current_session = jsonable_encoder(session)

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
        logger.info("Only one previous session exists for this user-quiz combo")
        last_session = previous_two_sessions[0]
    # two previous sessions exist
    elif len(previous_two_sessions) == 2:
        logger.info("Two previous sessions exists for this user-quiz combo")
        last_session, second_last_session = previous_two_sessions  # unpack

    session_answers = []
    if last_session is None:
        logger.info("No previous session exists for this user-quiz combo")
        current_session["is_first"] = True
        if not session.omr_mode:
            question_order = shuffle_question_order(quiz["question_sets"])
            current_session["question_order"] = question_order
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
            # copy the omr mode value if changed (changes when toggled in UI)
            if (
                "omr_mode" not in last_session
                or last_session["omr_mode"] != session.omr_mode
            ):
                last_session["omr_mode"] = session.omr_mode
                logger.info("Updating omr_mode value in last_session")
                update_result = client.quiz.sessions.update_one(
                    {"_id": last_session["_id"]}, {"$set": last_session}
                )
                if not update_result.acknowledged:
                    logger.error("Failed to update last session's omr_mode value")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to update last session's omr_mode value",
                    )

            return JSONResponse(
                status_code=status.HTTP_201_CREATED, content=last_session
            )

        # we reach here because some meaningful event (start/resume/end) has occurred in last_session
        # so, we HAVE to distinguish between current_session and last_session by creating
        # a new session for current_session
        logger.info(
            f"Some meaningful event has occurred in last_session, creating new session for user: {session.user_id} and quiz: {session.quiz_id} with {session.omr_mode} as omr_mode"
        )
        current_session["is_first"] = False
        current_session["events"] = last_session.get("events", [])
        current_session["time_remaining"] = last_session.get("time_remaining", None)
        current_session["has_quiz_ended"] = last_session.get("has_quiz_ended", False)
        current_session["metrics"] = last_session.get("metrics", None)
        current_session["question_order"] = last_session["question_order"]

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

    # insert current session into db
    result = client.quiz.sessions.insert_one(current_session)
    if result.acknowledged:
        logger.info(
            f"Created new session with id {result.inserted_id} for user: {session.user_id} and quiz: {session.quiz_id} with {session.omr_mode} as omr_mode"
        )
    else:
        logger.error(
            f"Failed to insert new session for user: {session.user_id} and quiz: {session.quiz_id} and omr_mode: {session.omr_mode}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to insert new session",
        )

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

    when end-quiz event is sent, session_updates also contains netrics
    """
    new_event = jsonable_encoder(session_updates)["event"]
    log_message = f"Updating session with id {session_id} and event {new_event}"
    session_update_query = {}

    # if new_event == EventType.dummy_event:
    #     return JSONResponse(
    #         status_code=status.HTTP_200_OK, content={"time_remaining": None}
    #     )

    session = client.quiz.sessions.find_one({"_id": session_id})
    if session is None:
        logger.error(
            f"Received session update request, but session_id {session_id} not found"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session {session_id} not found",
        )
    user_id, quiz_id = session["user_id"], session["quiz_id"]
    log_message += f", for user: {user_id} and quiz: {quiz_id}"
    logger.info(log_message)

    new_event_obj = jsonable_encoder(Event.parse_obj({"event_type": new_event}))
    if session["events"] is None:
        session["events"] = [new_event_obj]
        if "$set" not in session_update_query:
            session_update_query["$set"] = {"events": [new_event_obj]}
        else:
            session_update_query["$set"].update({"events": [new_event_obj]})
    else:
        if (
            new_event == EventType.dummy_event
            and session["events"][-1]["event_type"] == EventType.dummy_event
        ):
            # if previous event is dummy, just change the updated_at time of previous event
            last_event_index = len(session["events"]) - 1
            last_event_update_query = {
                "events."
                + str(last_event_index)
                + ".updated_at": new_event_obj["created_at"]
            }
            if "$set" not in session_update_query:
                session_update_query["$set"] = last_event_update_query
            else:
                session_update_query["$set"].update(last_event_update_query)

        else:
            session["events"].append(new_event_obj)
            if "$push" not in session_update_query:
                session_update_query["$push"] = {"events": new_event_obj}
            else:
                session_update_query["$push"].update({"events": new_event_obj})

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
        if "$set" not in session_update_query:
            session_update_query["$set"] = {"time_remaining": time_remaining}
        else:
            session_update_query["$set"].update({"time_remaining": time_remaining})
        response_content = {"time_remaining": time_remaining}

    # update the document in the sessions collection
    if new_event == EventType.end_quiz:
        session_metrics = jsonable_encoder(session_updates)["metrics"]

        if "$set" not in session_update_query:
            session_update_query["$set"] = {
                "has_quiz_ended": True,
                "metrics": session_metrics,
            }
        else:
            session_update_query["$set"].update(
                {"has_quiz_ended": True, "metrics": session_metrics}
            )

    update_result = client.quiz.sessions.update_one(
        {"_id": session_id}, session_update_query
    )
    if update_result.modified_count == 0:
        logger.error(f"Failed to update session with id {session_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session with id {session_id}",
        )

    logger.info(
        f"Updated session with id {session_id} for user: {user_id} and quiz: {quiz_id}"
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=response_content)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    logger.info(f"Fetching session with id {session_id}")
    if (session := client.quiz.sessions.find_one({"_id": session_id})) is not None:
        logger.info(f"Found session with id {session_id}")
        return session

    logger.error(f"Session {session_id} not found")
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"session {session_id} not found"
    )


@router.get("/user/{user_id}/quiz-attempts", response_model=Dict[str, bool])
async def check_all_quiz_status(user_id: str) -> Dict[str, bool]:
    """
    Check the end status of all quizzes attempted by the user.
    Args:
    - user_id (str): The ID of the user.
    Returns:
    - Dict[str, bool]: A dictionary with quiz IDs as keys and `has_quiz_ended` as boolean values.
    """
    logger.info(f"Fetching all quiz attempts for user {user_id}")

    user_latest_sessions = client.quiz.sessions.aggregate(
        [
            {"$match": {"user_id": user_id}},
            {"$sort": {"_id": -1}},
            {
                "$group": {
                    "_id": "$quiz_id",
                    "has_quiz_ended": {"$first": "$has_quiz_ended"},
                }
            },
        ]
    )

    # Create a dictionary of quiz end statuses for easy lookup
    latest_sessions_dict = {
        session["_id"]: session["has_quiz_ended"] for session in user_latest_sessions
    }

    logger.info(f"Quiz end statuses for user {user_id}: {latest_sessions_dict}")
    return latest_sessions_dict
