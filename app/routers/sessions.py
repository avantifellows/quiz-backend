from fastapi import APIRouter, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from app.database import client
from app.models import Session, SessionAnswer, SessionResponse

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
        {"quiz_id": session["quiz_id"], "user_id": session["user_id"]}
    )

    session_answers = []
    if previous_session is None:
        session["is_first"] = True

        # since we know that there is going to be only one question set for now
        if "question_sets" in quiz and quiz["question_sets"]:
            question_set_id = quiz["question_sets"][0]["_id"]
            questions = client.quiz.questions.find({"question_set_id": question_set_id})
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

        # restore the answers from the previous sessions
        session_answers = list(
            client.quiz.session_answers.find({"session_id": previous_session["_id"]})
        )
        for index, session_answer in enumerate(session_answers):
            for key in ["_id", "session_id"]:
                session_answer.pop(key)

            session_answers[index] = jsonable_encoder(
                SessionAnswer.parse_obj(session_answer)
            )

    session["session_answers"] = session_answers

    new_session = client.quiz.sessions.insert_one(session)
    created_session = client.quiz.sessions.find_one({"_id": new_session.inserted_id})

    for index, _ in enumerate(session_answers):
        session_answers[index]["session_id"] = new_session.inserted_id

    client.quiz.session_answers.insert_many(session_answers)

    return JSONResponse(status_code=status.HTTP_201_CREATED, content=created_session)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    if (session := client.quiz.sessions.find_one({"_id": session_id})) is not None:
        return session

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"session {session_id} not found"
    )
