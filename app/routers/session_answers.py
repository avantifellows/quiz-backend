from fastapi import APIRouter, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from database import client
from models import UpdateSessionAnswer
from utils import remove_optional_unset_args
from logger_config import get_logger
from typing import List

router = APIRouter(prefix="/session_answers", tags=["Session Answers"])
logger = get_logger()


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
    log_message = f"Updating session answer for session: {session_id} at position: {position_index}. The answer is {session_answer.answer}. Visited is {session_answer.visited}"
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


@router.patch("/{session_id}", response_model=None)
async def update_all_session_answers_in_a_session(
    session_id: str, session_answers: List[UpdateSessionAnswer]
):
    """
    Update all session answers in a session in the session answers array
    Path Params:
    session_id - the id of the session

    function params:
    session_answers - list of session answers for the session
    """
    log_message = f"Updating all session answers for session: {session_id}"
    input_session_answers = [
        jsonable_encoder(remove_optional_unset_args(session_answer))
        for session_answer in session_answers
    ]

    # check if the session exists
    session = client.quiz.sessions.find_one({"_id": session_id})
    if session is None:
        logger.error(
            f"Received all session_answer update request, but provided session with id {session_id} not found"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Received all session_answer update request, but provided session with id {session_id} not found",
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

    # check if session_answers array in session that we're trying to update is equal to input_session_answers array length
    if len(input_session_answers) != len(session["session_answers"]):
        logger.error(
            f"Provided input_session_answers array length not equal to length of array in session in db"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provided input_session_answers array length not equal to length of array in session in db",
        )

    # constructing the $set query for mongodb
    setQuery = {}
    for position_index, session_answer in enumerate(input_session_answers):
        for key, value in session_answer.items():
            setQuery[f"session_answers.{position_index}.{key}"] = value

    # update the document in the session_answers collection
    result = client.quiz.sessions.update_one({"_id": session_id}, {"$set": setQuery})
    if result.modified_count == 0:
        logger.error(
            f"Failed to update session answers for session: {session_id} (user: {user_id} and quiz: {quiz_id})"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session answers for session: {session_id}",
        )

    logger.info(
        f"Updated all session answers for session: {session_id} (user: {user_id} and quiz: {quiz_id})"
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=None)


@router.get("/{session_id}/{position_index}", response_model=None)
async def get_session_answer_from_a_session(session_id: str, position_index: int):
    logger.info(
        f"Getting session answer for session: {session_id}, position: {position_index}"
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
    aggregation_result = list(client.quiz.sessions.aggregate(pipeline))
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
        status_code=status.HTTP_200_OK, content=aggregation_result[0]["session_answer"]
    )
