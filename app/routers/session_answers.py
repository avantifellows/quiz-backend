from fastapi import APIRouter, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from database import client
from models import UpdateSessionAnswer
from utils import remove_optional_unset_args
from logger_config import get_logger
from typing import List, Tuple
from datetime import datetime, timedelta

router = APIRouter(prefix="/session_answers", tags=["Session Answers"])
logger = get_logger()


@router.patch("/{session_id}/update-multiple-answers", response_model=None)
async def update_session_answers_at_specific_positions(
    session_id: str, positions_and_answers: List[Tuple[int, UpdateSessionAnswer]]
):
    """
    Update session answers in a session at specific position indices.

    Path Params:
    session_id - the id of the session

    Function Params:
    positions_and_answers - a list of tuples that contain the position index and the corresponding session answer object.
    """
    log_message = f"Updating multiple session answers for session: {session_id}"
    session = client.quiz.sessions.find_one({"_id": session_id})
    if session is None:
        session_id_error_message = f"Received multiple session_answer update request, but provided session with id {session_id} not found"
        logger.error(session_id_error_message)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=session_id_error_message,
        )

    user_id, quiz_id = session["user_id"], session["quiz_id"]
    log_message += f"(user: {user_id}, quiz: {quiz_id})"
    logger.info(log_message)

    if "session_answers" not in session or session["session_answers"] is None:
        no_session_answer_error_message = f"No session answers found in the session with id {session_id}, for user: {user_id} and quiz: {quiz_id}"
        logger.error(no_session_answer_error_message)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=no_session_answer_error_message,
        )

    positions, session_answers = zip(*positions_and_answers)
    if any(pos > len(session["session_answers"]) for pos in positions):
        error_message = "One or more provided position indices are out of bounds of the session answers array"
        logger.error(error_message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message,
        )

    input_session_answers = [
        jsonable_encoder(remove_optional_unset_args(session_answer))
        for session_answer in session_answers
    ]

    setQuery = {
        f"session_answers.{position_index}.{key}": value
        for position_index, session_answer in zip(positions, input_session_answers)
        for key, value in session_answer.items()
    }

    result = client.quiz.sessions.update_one({"_id": session_id}, {"$set": setQuery})
    if result.modified_count == 0:
        error_message = f"Failed to update multiple session answers for session: {session_id} (user: {user_id} and quiz: {quiz_id})"
        logger.error(error_message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_message,
        )

    logger.info(
        f"Updated multiple session answers for session: {session_id} (user: {user_id} and quiz: {quiz_id})"
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=None)


@router.patch("/{session_id}/{position_index}", response_model=None)
async def update_session_answer_in_a_session(
    session_id: str, position_index: int, session_answer: UpdateSessionAnswer
):
    """
    Update a session answer in a session by its position index in the session answers array
    Path Params:
    session_id - the id of the session
    position_index - the position index of the session answer in the session answers array. This corresponds to the position of the question in the quiz
    """
    log_message = f"Updating session answer for session: {session_id} at position: {position_index}. The answer is {session_answer.answer}. Visited is {session_answer.visited}. Time spent is {session_answer.time_spent} seconds. Marked for review status is {session_answer.marked_for_review}."
    session_answer = remove_optional_unset_args(session_answer)
    session_answer = jsonable_encoder(session_answer)

    # check if the session exists
    session = client.quiz.sessions.find_one({"_id": session_id})
    if session is None:
        logger.error(
            f"Received session_answer update request, but provided session with id {session_id} not found"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Received session_answer update request, but provided session with id {session_id} not found",
        )

    # get user_id and quiz_id for logging
    # Note: every session must have these keys
    user_id, quiz_id = session["user_id"], session["quiz_id"]
    log_message += f"(user: {user_id}, quiz: {quiz_id})"
    logger.info(log_message)

    # check if the session has session answers key
    if "session_answers" not in session or session["session_answers"] is None:
        logger.error(
            f"No session answers found in the session with id {session_id}, for user: {user_id} and quiz: {quiz_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No session answers found in the session with id {session_id}",
        )

    # check if the session answer index that we're trying to access is out of bounds or not
    if position_index > len(session["session_answers"]):
        logger.error(
            f"Provided position index {position_index} is out of bounds of length of the session answers array"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provided position index {position_index} is out of bounds of length of the session answers array",
        )

    # constructing the $set query for mongodb
    setQuery = {}
    for key, value in session_answer.items():
        setQuery[f"session_answers.{position_index}.{key}"] = value

    # update the document in the session_answers collection
    result = client.quiz.sessions.update_one({"_id": session_id}, {"$set": setQuery})
    if result.modified_count == 0:
        logger.error(
            f"Failed to update session answer for session: {session_id} (user: {user_id} and quiz: {quiz_id}), position: {position_index}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session answer for session: {session_id}, position: {position_index}",
        )

    logger.info(
        f"Updated session answer for session: {session_id} (user: {user_id} and quiz: {quiz_id}), position: {position_index}"
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=None)


@router.get("/{session_id}/{position_index}", response_model=None)
async def get_session_answer_from_a_session(session_id: str, position_index: int):
    logger.info(
        f"Getting session answer for session: {session_id}, position: {position_index}"
    )

    session_data = client["quiz"].sessions.find_one(
        {"_id": session_id}, {"quiz_id": 1, "created_at": 1}
    )
    if not session_data or "quiz_id" not in session_data:
        logger.error(f"Quiz ID not found for session {session_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Quiz ID not found"
        )

    quiz_id = session_data["quiz_id"]
    quiz_data = client["quiz"]["quizzes"].find_one(
        {"_id": quiz_id}, {"review_delay": 1}
    )

    if not quiz_data or "review_delay" not in quiz_data:
        logger.error(f"Review delay not found for session {session_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Review delay not found",
        )

    review_delay = quiz_data.get("review_delay", {})
    delay_days = review_delay.get("days", 0)
    delay_hours = review_delay.get("hours", 0)
    delay_minutes = review_delay.get("minutes", 0)

    # Calculate the release time
    created_at = session_data.get("created_at")
    if not created_at:
        logger.error(f"Session {session_id} does not have a creation timestamp")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session data missing creation time",
        )

    created_at = datetime.fromisoformat(
        created_at
    )  # Ensure this format matches the stored format
    release_time = created_at + timedelta(
        days=delay_days, hours=delay_hours, minutes=delay_minutes
    )

    # Check if answer can be released
    current_time = datetime.utcnow()
    if current_time < release_time:
        time_remaining = release_time - current_time
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "message": "Answer not available yet",
                "time_remaining": str(time_remaining),
            },
        )

    pipeline = [
        {
            "$match": {  # match the session with the provided session_id
                "_id": session_id
            }
        },
        {
            "$project": {  # project the required element from session_answers array
                "_id": 0,
                "session_answer": {
                    "$arrayElemAt": ["$session_answers", position_index]
                },
            }
        },
    ]
    aggregation_result = list(client["quiz"].sessions.aggregate(pipeline))
    if len(aggregation_result) == 0:
        logger.error(
            f"Either session_id {session_id} is wrong or position_index {position_index} is out of bounds"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Either session_id {session_id} is wrong or position_index {position_index} is out of bounds",
        )

    logger.info(
        f"Retrieved session answer for session: {session_id}, position: {position_index}"
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=aggregation_result[0]["session_answer"]["answer"],
    )
