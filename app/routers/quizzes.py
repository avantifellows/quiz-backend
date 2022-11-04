from fastapi import APIRouter, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from database import client
from models import Quiz, GetQuizResponse, CreateQuizResponse
from settings import Settings

router = APIRouter(prefix="/quiz", tags=["Quiz"])
settings = Settings()


@router.post("/", response_model=CreateQuizResponse)
async def create_quiz(quiz: Quiz):
    quiz = jsonable_encoder(quiz)

    for question_set_index, question_set in enumerate(quiz["question_sets"]):
        questions = question_set["questions"]
        for question_index, _ in enumerate(questions):
            questions[question_index]["question_set_id"] = question_set["_id"]

        client.quiz.questions.insert_many(questions)

        subset_with_details = client.quiz.questions.aggregate(
            [
                {"$match": {"question_set_id": question_set["_id"]}},
                {"$limit": settings.subset_size},
            ]
        )

        subset_without_details = client.quiz.questions.aggregate(
            [
                {"$match": {"question_set_id": question_set["_id"]}},
                {"$skip": settings.subset_size},
                {
                    "$project": {
                        "graded": 1,
                        "type": 1,
                        "correct_answer": 1,
                        "question_set_id": 1,
                    }
                },
            ]
        )

        aggregated_questions = list(subset_with_details) + list(subset_without_details)
        quiz["question_sets"][question_set_index]["questions"] = aggregated_questions

    new_quiz = client.quiz.quizzes.insert_one(quiz)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED, content={"id": new_quiz.inserted_id}
    )


@router.get("/{quiz_id}", response_model=GetQuizResponse)
async def get_quiz(quiz_id: str):
    if (quiz := client.quiz.quizzes.find_one({"_id": quiz_id})) is not None:
        return quiz

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"quiz {quiz_id} not found"
    )
