from fastapi import APIRouter, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
import pymongo
from database import client
from models import (
    Session,
    SessionAnswer,
    SessionResponse,
    UpdateSession,
    UpdateSessionResponse,
)
from datetime import datetime

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
        if quiz["time_limit"] is not None:
            session["time_remaining"] = quiz["time_limit"]["max"]

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
        session["has_quiz_started"] = previous_session.get("has_quiz_started", False)

        # restore the answers from the previous sessions
        previous_session_answers = list(
            client.quiz.session_answers.find(
                {"session_id": previous_session["_id"]},
                sort=[("_id", pymongo.ASCENDING)],
            )
        )
        session_answers = []
        for index, session_answer in enumerate(previous_session_answers):
            # note: we retain created_at key in session_answer
            for key in ["_id", "session_id"]:
                session_answer.pop(key)

            session_answers.append(
                jsonable_encoder(SessionAnswer.parse_obj(session_answer))
            )

        session["quiz_start_resume_time"] = previous_session.get(
            "quiz_start_resume_time", None
        )
        session["time_remaining"] = previous_session.get("time_remaining", None)
        # time_remaining will get updated when start/resume clicked

    session["session_answers"] = session_answers

    new_session = client.quiz.sessions.insert_one(session)
    created_session = client.quiz.sessions.find_one({"_id": new_session.inserted_id})

    for index, _ in enumerate(session_answers):
        session_answers[index]["session_id"] = new_session.inserted_id

    client.quiz.session_answers.insert_many(session_answers)

    return JSONResponse(status_code=status.HTTP_201_CREATED, content=created_session)


@router.patch("/{session_id}", response_model=UpdateSessionResponse)
async def update_session(session_id: str, session_updates: UpdateSession):
    session_updates = jsonable_encoder(session_updates)
    session = client.quiz.sessions.find_one({"_id": session_id})
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session {session_id} not found",
        )

    current_time = datetime.utcnow()
    time_elapsed = 0
    if not session_updates["has_quiz_started_first_time"]:
        # update time remaining based on current time (resume button clicked)
        time_elapsed = (
            current_time - datetime.fromisoformat(session["quiz_start_resume_time"])
        ).seconds
    else:
        # start button clicked; for the first time
        # time_remaining is the same as when session was created - no need to update
        session["has_quiz_started"] = True
    session["quiz_start_resume_time"] = current_time

    response_content = {}
    if "time_remaining" in session and session["time_remaining"] is not None:
        # if not here => there is no time limit set, no need to update
        session["time_remaining"] = max(0, session["time_remaining"] - time_elapsed)
        response_content = {"time_remaining": session["time_remaining"]}

    # update the document in the sessions collection
    session["has_quiz_ended"] = session_updates["has_quiz_ended"]
    client.quiz.sessions.update_one(
        {"_id": session_id}, {"$set": jsonable_encoder(session)}
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content=response_content)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    if (session := client.quiz.sessions.find_one({"_id": session_id})) is not None:
        return session

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"session {session_id} not found"
    )
