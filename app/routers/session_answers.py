from fastapi import APIRouter, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from database import client
from models import SessionAnswerResponse, UpdateSessionAnswer
from utils import remove_optional_unset_args

router = APIRouter(prefix="/session_answers", tags=["Session Answers"])


@router.patch("/{session_id}/{position_index}", response_model=SessionAnswerResponse)
async def update_session_answer_in_a_session(
    session_id: str, position_index: int, session_answer: UpdateSessionAnswer
):
    """
    Update a session answer in a session by its position index in the session answers array
    Path Params:
    session_id - the id of the session
    position_index - the position index of the session answer in the session answers array. This corresponds to the position of the question in the quiz
    """
    session_answer = remove_optional_unset_args(session_answer)
    session_answer = jsonable_encoder(session_answer)

    # check if the session exists
    session = client.quiz.sessions.find_one({"_id": session_id})
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provided session with id {session_id} not found",
        )

    # check if the session has session answers key
    if "session_answers" not in session or session["session_answers"] is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No session answers found in the session with id {session_id}",
        )

    # check if the session answer index that we're trying to access is out of bounds or not
    if position_index > len(session["session_answers"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provided position index {position_index} is out of bounds of length of the session answers array",
        )

    # constructing the $set query for mongodb
    setQuery = {}
    for key, value in session_answer.items():
        setQuery[f"session_answers.{position_index}.{key}"] = value

    # update the document in the session_answers collection
    client.quiz.sessions.update_one({"_id": session_id}, {"$set": setQuery})

    return JSONResponse(status_code=status.HTTP_200_OK, content=session_answer)


@router.get("/{session_id}/{position_index}", response_model=SessionAnswerResponse)
async def get_session_answer_from_a_session(session_id: str, position_index: int):
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either session_id is wrong or position_index is out of bounds",
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK, content=aggregation_result[0]["session_answer"]
    )
