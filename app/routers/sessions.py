from fastapi import APIRouter, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
import pymongo
from database import client
from models import Session, SessionAnswer, SessionResponse, UpdateSession

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.post("/", response_model=SessionResponse)
async def create_session(session: Session):
    session = jsonable_encoder(session)

    quiz = client.quiz.quizzes.find_one({"_id": session["quiz_id"]})

    if quiz is None:
        raise HTTPException(
            status_code=404, detail=f"quiz {session['quiz_id']} not found"
        )

    previous_session = client.quiz.sessions.find_one(
        {"quiz_id": session["quiz_id"], "user_id": session["user_id"]},
        sort=[("_id", pymongo.DESCENDING)],
    )

    session_answers = []
    if previous_session is None:
        session["is_first"] = True

        if "question_sets" in quiz and quiz["question_sets"]:
            question_set_ids = [qset["_id"] for qset in quiz["question_sets"]]
            questions = []
            for qset_id in question_set_ids:
                questions.extend(
                    client.quiz.questions.find(
                        {"question_set_id": qset_id}, sort=[("_id", pymongo.ASCENDING)]
                    )
                )

            if questions:
                for question in questions:
                    session_answers.append(
                        jsonable_encoder(
                            SessionAnswer.parse_obj(
                                {
                                    "question_id": question["_id"],
                                }
                            )
                        )
                    )
    else:
        session["is_first"] = False
        session["has_quiz_ended"] = previous_session.get("has_quiz_ended", False)

        # restore the answers from the previous session
        previous_session_answers = list(
            client.quiz.session_answers.find(
                {"session_id": previous_session["_id"]},
                sort=[("_id", pymongo.ASCENDING)],
            )
        )
        session_answers = []
        for index, session_answer in enumerate(previous_session_answers):
            for key in ["_id", "session_id"]:
                session_answer.pop(key)

            session_answers.append(
                jsonable_encoder(SessionAnswer.parse_obj(session_answer))
            )

    session["session_answers"] = session_answers

    new_session = client.quiz.sessions.insert_one(session)
    created_session = client.quiz.sessions.find_one({"_id": new_session.inserted_id})

    for index, _ in enumerate(session_answers):
        session_answers[index]["session_id"] = new_session.inserted_id

    client.quiz.session_answers.insert_many(session_answers)

    return JSONResponse(status_code=status.HTTP_201_CREATED, content=created_session)


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(session_id: str, session: UpdateSession):
    session = jsonable_encoder(session)

    if (client.quiz.sessions.find_one({"_id": session_id})) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session {session_id} not found",
        )

    # update the document in the sessions collection
    client.quiz.sessions.update_one({"_id": session_id}, {"$set": session})

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=client.quiz.sessions.find_one({"_id": session_id}),
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    if (session := client.quiz.sessions.find_one({"_id": session_id})) is not None:
        return session

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"session {session_id} not found"
    )
