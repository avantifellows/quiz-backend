from fastapi import APIRouter, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from database import client
from models import UpdateSessionAnswer
from utils import remove_optional_unset_args
from logger_config import get_logger
from typing import List, Tuple
from cache.cache import cache_data, get_cached_data
from cache.cache_keys import CacheKeys

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
    session = None
    cached_session = get_cached_data(CacheKeys.SESSION_.value + session_id)
    if cached_session:
        session = cached_session
    else:
        session = client.quiz.sessions.find_one({"_id": session_id})
        if session is None:
            log_message += f", provided session with id {session_id} not found in db"
            logger.error(log_message)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=log_message,
            )

    log_message += f" (user: {session['user_id']}, quiz: {session['quiz_id']})"

    if "session_answers" not in session or session["session_answers"] is None:
        log_message += ", No session answers found in the session"
        logger.error(log_message)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=log_message,
        )

    positions, session_answers = zip(*positions_and_answers)
    if any(pos > len(session["session_answers"]) for pos in positions):
        log_message += (
            ", provided position indices are out of bounds of the session answers array"
        )
        logger.error(log_message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=log_message,
        )

    input_session_answers = [
        jsonable_encoder(remove_optional_unset_args(session_answer))
        for session_answer in session_answers
    ]

    # setQuery = {
    #     f"session_answers.{position_index}.{key}": value
    #     for position_index, session_answer in zip(positions, input_session_answers)
    #     for key, value in session_answer.items()
    # }

    for position_index, session_answer in zip(positions, input_session_answers):
        for key, value in session_answer.items():
            session["session_answers"][position_index][key] = value

    cache_data(CacheKeys.SESSION_.value + session_id, session)
    if get_cached_data(CacheKeys.SESSION_ID_TO_INSERT_.value + session_id) is None:
        cache_data(CacheKeys.SESSION_ID_TO_UPDATE_.value + session_id, "x")

    # result = client.quiz.sessions.update_one({"_id": session_id}, {"$set": setQuery})
    # if result.modified_count == 0:
    #     error_message = f"Failed to update multiple session answers for session: {session_id} (user: {user_id} and quiz: {quiz_id})"
    #     logger.error(error_message)
    #     raise HTTPException(
    #         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #         detail=error_message,
    #     )

    log_message += ", success!"
    logger.info(log_message)
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
    session = None
    cached_session = get_cached_data(CacheKeys.SESSION_.value + session_id)
    if cached_session:
        session = cached_session
    else:
        session = client.quiz.sessions.find_one({"_id": session_id})
        if session is None:
            log_message += ", provided session not found in db"
            logger.error(log_message)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=log_message,
            )

    # get user_id and quiz_id for logging
    # Note: every session must have these keys
    log_message += f" (user: {session['user_id']}, quiz: {session['quiz_id']})"

    # check if the session has session answers key
    if "session_answers" not in session or session["session_answers"] is None:
        log_message += ", No session answers found in the session"
        logger.error(log_message)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No session answers found in the session with id {session_id}",
        )

    # check if the session answer index that we're trying to access is out of bounds or not
    if position_index > len(session["session_answers"]):
        log_message += (
            ", provided position index is out of bounds of the session answers array"
        )
        logger.error(log_message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provided position index {position_index} is out of bounds of length of the session answers array",
        )

    # constructing the $set query for mongodb
    # setQuery = {}
    # for key, value in session_answer.items():
    #     setQuery[f"session_answers.{position_index}.{key}"] = value
    for key, value in session_answer.items():
        session["session_answers"][position_index][key] = value

    # update the document in the session_answers collection
    # result = client.quiz.sessions.update_one({"_id": session_id}, {"$set": setQuery})
    cache_data(CacheKeys.SESSION_.value + session_id, session)
    if get_cached_data(CacheKeys.SESSION_ID_TO_INSERT_.value + session_id) is None:
        cache_data(CacheKeys.SESSION_ID_TO_UPDATE_.value + session_id, "x")

    # if result.modified_count == 0:
    #     logger.error(
    #         f"Failed to update session answer for session: {session_id} (user: {user_id} and quiz: {quiz_id}), position: {position_index}"
    #     )
    #     raise HTTPException(
    #         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #         detail=f"Failed to update session answer for session: {session_id}, position: {position_index}",
    #     )
    log_message += ", success!"
    logger.info(log_message)
    return JSONResponse(status_code=status.HTTP_200_OK, content=None)


@router.get("/{session_id}/{position_index}", response_model=None)
async def get_session_answer_from_a_session(session_id: str, position_index: int):
    log_message = (
        f"Getting session answer for session: {session_id}, position: {position_index}"
    )
    # pipeline = [
    #     {
    #         "$match": {  # match the session with the provided session_id
    #             "_id": session_id
    #         }
    #     },
    #     {
    #         "$project": {  # project the required element from session_answers array
    #             "_id": 0,
    #             "session_answer": {
    #                 "$arrayElemAt": ["$session_answers", position_index]
    #             },
    #         }
    #     },
    # ]
    # aggregation_result = list(client.quiz.sessions.aggregate(pipeline))

    # if len(aggregation_result) == 0:
    #     logger.error(
    #         f"Either session_id {session_id} is wrong or position_index {position_index} is out of bounds"
    #     )
    #     raise HTTPException(
    #         status_code=status.HTTP_400_BAD_REQUEST,
    #         detail=f"Either session_id {session_id} is wrong or position_index {position_index} is out of bounds",
    #     )

    session = None
    cached_session = get_cached_data(CacheKeys.SESSION_.value + session_id)
    if cached_session:
        session = cached_session
    else:
        session = client.quiz.sessions.find_one({"_id": session_id})
        if session is None:
            log_message += ", provided session not found in db"
            logger.error(log_message)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=log_message,
            )
        cache_data(CacheKeys.SESSION_.value + session_id, session)

    if "session_answers" not in session or session["session_answers"] is None:
        log_message += ", No session answers found in the session"
        logger.error(log_message)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=log_message,
        )

    if position_index > len(session["session_answers"]):
        log_message += (
            ", provided position index is out of bounds of the session answers array"
        )
        logger.error(log_message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=log_message,
        )

    result = session["session_answers"][position_index]
    log_message += ", success!"
    logger.info(log_message)
    return JSONResponse(status_code=status.HTTP_200_OK, content=result)
