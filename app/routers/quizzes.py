from fastapi import APIRouter, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from database import client
from models import Quiz, QuizResponse

router = APIRouter(prefix="/quiz", tags=["Quiz"])


@router.post("/")
async def create_quiz(quiz: Quiz):
    """Returns the ID of created quiz in a dictionary with key as 'quiz_id'"""
    quiz = jsonable_encoder(quiz)
    new_quiz = client.quiz.quizzes.insert_one(quiz)
    created_quiz = client.quiz.quizzes.find_one({"_id": new_quiz.inserted_id})

    for question_set in created_quiz["question_sets"]:
        questions = question_set["questions"]
        for index, _ in enumerate(questions):
            questions[index]["question_set_id"] = question_set["_id"]

        client.quiz.questions.insert_many(questions)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED, content={"quiz_id": new_quiz.inserted_id}
    )


@router.get("/{quiz_id}", response_model=QuizResponse)
async def get_quiz(quiz_id: str):
    if (quiz := client.quiz.quizzes.find_one({"_id": quiz_id})) is not None:
        return quiz

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"quiz {quiz_id} not found"
    )
