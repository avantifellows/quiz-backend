from fastapi import APIRouter, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from database import client
from models import SessionAnswerResponse, UpdateSessionAnswer

router = APIRouter(prefix="/session_answers", tags=["Session Answers"])


@router.patch("/{session_answer_id}", response_model=SessionAnswerResponse)
async def update_session_answer(
    session_answer_id: str, session_answer: UpdateSessionAnswer
):
    session_answer = jsonable_encoder(session_answer)

    if "answer" not in session_answer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No value provided for 'answer'",
        )

    if (client.quiz.session_answers.find_one({"_id": session_answer_id})) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session_answer {session_answer_id} not found",
        )

    # update the document in the session_answers collection
    client.quiz.session_answers.update_one(
        {"_id": session_answer_id}, {"$set": session_answer}
    )

    updated_session_answer = client.quiz.session_answers.find_one(
        {"_id": session_answer_id}
    )

    # update the document in the sessions collection if this answer
    # is present in the subset of session answers we store in the document
    # corresponding to the session
    session_to_update = client.quiz.sessions.find_one(
        {"_id": updated_session_answer["session_id"]}
    )

    session_answers = list(session_to_update["session_answers"])
    update_session = False
    for index, _ in enumerate(session_answers):
        if session_answers[index]["_id"] == session_answer_id:
            session_answers[index].update(session_answer)
            update_session = True
            break

    if update_session:
        client.quiz.sessions.update_one(
            {"_id": session_to_update["_id"]},
            {"$set": {"session_answers": session_answers}},
        )

    return JSONResponse(status_code=status.HTTP_200_OK, content=updated_session_answer)


@router.get("/{session_answer_id}", response_model=SessionAnswerResponse)
async def get_session_answer(session_answer_id: str):
    if (
        session_answer := client.quiz.session_answers.find_one(
            {"_id": session_answer_id}
        )
    ) is not None:
        return session_answer

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"session_answer {session_answer_id} not found",
    )
