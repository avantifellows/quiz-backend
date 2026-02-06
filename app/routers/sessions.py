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
from typing import Dict, Optional
from settings import Settings


def str_to_datetime(value) -> Optional[datetime]:
    """
    Convert a datetime-like value to python datetime.
    - Accepts ISO strings (common via jsonable_encoder) or BSON datetimes from Mongo.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def shuffle_question_order(quiz, shuffle=False):
    """returns shuffled question order for a quiz if shuffle is True, else returns sequential order"""
    question_sets = quiz["question_sets"]
    question_order = []
    bucket_size = Settings().subset_size

    global_index = 0  # Track global index across all questions
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
            if shuffle is True:
                # Shuffle the block indices
                random.shuffle(block_indices)

            # Append the shuffled indices to question_order
            question_order.extend(block_indices)

            # Update global index for the next set of questions
            global_index += len(block_indices)
    return question_order


router = APIRouter(prefix="/sessions", tags=["Sessions"])
logger = get_logger()


def _time_elapsed_secs(dt_1, dt_2) -> float:
    d1 = str_to_datetime(dt_1)
    d2 = str_to_datetime(dt_2)
    if d1 is None or d2 is None:
        return 0
    return (d1 - d2).total_seconds()


def derive_time_remaining(time_limit_max: int, total_time_spent: int) -> int:
    """Clamp to avoid negative time_remaining due to polling/latency gaps."""
    return max(0, int(time_limit_max) - int(total_time_spent))


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
        if session.omr_mode:
            current_session["question_order"] = shuffle_question_order(
                quiz, shuffle=False
            )
        else:
            current_session["question_order"] = shuffle_question_order(
                quiz, shuffle=quiz["shuffle"]
            )
        if quiz["time_limit"] is not None:
            current_session["time_limit_max"] = quiz["time_limit"]["max"]

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
                now = datetime.utcnow()
                last_session["omr_mode"] = session.omr_mode
                last_session["updated_at"] = now
                logger.info("Updating omr_mode value in last_session")
                update_result = client.quiz.sessions.update_one(
                    {"_id": last_session["_id"]},
                    {"$set": {"omr_mode": session.omr_mode, "updated_at": now}},
                )
                if not update_result.acknowledged:
                    logger.error("Failed to update last session's omr_mode value")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to update last session's omr_mode value",
                    )

            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content=jsonable_encoder(last_session),
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
        current_session["time_limit_max"] = last_session.get("time_limit_max", None)
        # Keep precomputed timing fields consistent with copied events.
        current_session["start_quiz_time"] = last_session.get("start_quiz_time", None)
        current_session["end_quiz_time"] = last_session.get("end_quiz_time", None)
        current_session["total_time_spent"] = last_session.get("total_time_spent", None)

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

    # Derive time_remaining from time_limit_max and total_time_spent (if known).
    if current_session.get("time_limit_max") is not None:
        base_spent = current_session.get("total_time_spent")
        if base_spent is not None:
            current_session["time_remaining"] = derive_time_remaining(
                current_session["time_limit_max"], base_spent
            )
        elif current_session.get("time_remaining") is None:
            current_session["time_remaining"] = current_session["time_limit_max"]

    # Ensure updated_at is present and reflects the insert time
    current_session["updated_at"] = datetime.utcnow()

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

    # return the created session (ensure datetimes/ObjectIds are JSON-safe)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED, content=jsonable_encoder(current_session)
    )


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
    total_time_spent = session.get("total_time_spent", None)
    running_total = float(total_time_spent or 0)
    should_update_total_time_spent = total_time_spent is None
    has_started = session.get("start_quiz_time") is not None or (
        session.get("events")
        and session["events"][0].get("event_type") == EventType.start_quiz
    )
    if new_event == EventType.start_quiz:
        has_started = True
    has_ended = session.get("has_quiz_ended") is True

    gap_since_prev_event_end = 0.0
    if session["events"] is None:
        session["events"] = [new_event_obj]
        if "$set" not in session_update_query:
            session_update_query["$set"] = {"events": [new_event_obj]}
        else:
            session_update_query["$set"].update({"events": [new_event_obj]})
    else:
        last_event = session["events"][-1] if session.get("events") else None
        last_event_type = last_event.get("event_type") if last_event else None
        last_event_created_at = last_event.get("created_at") if last_event else None
        last_event_updated_at = last_event.get("updated_at") if last_event else None

        # Timing rules:
        # - Dummy events define active windows (count full duration).
        # - Resume events without a dummy in between get a capped gap (<= 20s).
        # - End always counts the final gap after the last event.
        if (
            new_event == EventType.dummy_event
            and last_event_type == EventType.dummy_event
        ):
            # We'll extend the previous dummy-event window by updating its updated_at.
            # We also use this to incrementally update session.total_time_spent without double-counting.
            prev_dummy_updated_at = last_event_updated_at
            # if previous event is dummy, just change the updated_at time of previous event
            last_event_index = len(session["events"]) - 1
            last_event_update_query = {
                "events."
                + str(last_event_index)
                + ".updated_at": new_event_obj["created_at"]
            }
            # mirror this update in-memory too (helps keep local state consistent)
            session["events"][-1]["updated_at"] = new_event_obj["created_at"]
            if "$set" not in session_update_query:
                session_update_query["$set"] = last_event_update_query
            else:
                session_update_query["$set"].update(last_event_update_query)

            # Increment total_time_spent by only the newly added dummy window extension:
            # new_updated_at - old_updated_at
            if has_started and not has_ended:
                delta = _time_elapsed_secs(
                    new_event_obj.get("created_at"), prev_dummy_updated_at
                )
                if delta > 0:
                    running_total += float(delta)
                    should_update_total_time_spent = True

        else:
            # Not a consecutive dummy; record the new event in the timeline.
            session["events"].append(new_event_obj)
            if "$push" not in session_update_query:
                session_update_query["$push"] = {"events": new_event_obj}
            else:
                session_update_query["$push"].update({"events": new_event_obj})

            # elapsed time since the previous event "ended" (updated_at if present, else created_at)
            gap_since_prev_event_end = _time_elapsed_secs(
                new_event_obj.get("created_at"),
                last_event_updated_at or last_event_created_at,
            )

            # If this is the first dummy-event after some non-dummy event, we can increment
            # total_time_spent by:
            # (dummy.created_at - prev_event.end) + (dummy.updated_at - dummy.created_at)
            if new_event == EventType.dummy_event:
                if has_started and not has_ended:
                    delta = gap_since_prev_event_end
                    delta += _time_elapsed_secs(
                        new_event_obj.get("updated_at"), new_event_obj.get("created_at")
                    )
                    if delta > 0:
                        running_total += float(delta)
                        should_update_total_time_spent = True
            elif new_event == EventType.end_quiz:
                # End-quiz always counts the final gap since the last event ended.
                if has_started and not has_ended and gap_since_prev_event_end > 0:
                    running_total += float(gap_since_prev_event_end)
                    should_update_total_time_spent = True
            elif new_event == EventType.resume_quiz:
                # Resume updates: if there was no dummy window in between, cap the gap at 20s.
                # - previous event is dummy: dummy already captured elapsed time, so add 0 here
                # - previous event is start/resume: add up to 20s to avoid counting long idle gaps
                if (
                    has_started
                    and not has_ended
                    and last_event_type != EventType.dummy_event
                ):
                    delta = max(0, min(gap_since_prev_event_end, 20))
                    if delta > 0:
                        running_total += float(delta)
                        should_update_total_time_spent = True

    # Precompute and store session-level timing fields
    # - start_quiz_time: set once when start-quiz arrives
    # - end_quiz_time + total_time_spent: set when end-quiz arrives (event-based, matches ETL)
    if new_event == EventType.start_quiz and not session.get("start_quiz_time"):
        session_update_query.setdefault("$set", {}).update(
            {"start_quiz_time": new_event_obj.get("created_at")}
        )

    if should_update_total_time_spent:
        session_update_query.setdefault("$set", {}).update(
            {"total_time_spent": round(running_total, 2)}
        )

    # Derive time_remaining from time_limit_max and total_time_spent
    response_content = {}
    time_limit_max = session.get("time_limit_max")
    if time_limit_max is None:
        # no meaning of time remaining, we send time_remaining as None
        response_content = {"time_remaining": None}
    if time_limit_max is not None:
        # running_total may still be None if we haven't accumulated any timing yet.
        time_remaining = derive_time_remaining(time_limit_max, running_total or 0)
        session_update_query.setdefault("$set", {}).update(
            {"time_remaining": time_remaining}
        )
        response_content = {"time_remaining": time_remaining}

    # update the document in the sessions collection
    if new_event == EventType.end_quiz:
        session_metrics = jsonable_encoder(session_updates)["metrics"]
        session_update_query.setdefault("$set", {}).update(
            {
                "has_quiz_ended": True,
                "metrics": session_metrics,
                "end_quiz_time": new_event_obj.get("created_at"),
                "total_time_spent": round(running_total, 2),
            }
        )

    # Always bump session-level updated_at for any session change
    session_update_query.setdefault("$set", {}).update(
        {"updated_at": datetime.utcnow()}
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
