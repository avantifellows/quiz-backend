from fastapi import APIRouter, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from database import client
from models import Quiz, GetQuizResponse, CreateQuizResponse
from settings import Settings

router = APIRouter(prefix="/quiz", tags=["Quiz"])
settings = Settings()


def update_quiz_for_backwards_compatibility(quiz_collection, quiz_id, quiz):
    """
    if given quiz contains question sets that do not have max_questions_allowed_to_attempt key,
    update the question sets (in-place) with the key and value as len(questions) in that set.
    Additionally, add a default title and marking scheme for the set.
    Finally, add quiz to quiz_collection
    (NOTE: this is a primitive form of versioning)
    """
    for question_set_index, question_set in enumerate(quiz["question_sets"]):
        if "max_questions_allowed_to_attempt" not in question_set:
            question_set["max_questions_allowed_to_attempt"] = len(
                question_set["questions"]
            )
            question_set["title"] = "Section A"

        if "marking_scheme" not in question_set:
            question_marking_scheme = question_set["questions"][0]["marking_scheme"]
            if question_marking_scheme is not None:
                question_set["marking_scheme"] = question_marking_scheme
            else:
                question_set["marking_scheme"] = {
                    "correct": 1,
                    "wrong": 0,
                    "skipped": 0,
                }  # default

    quiz_collection.update_one({"_id": quiz_id}, {"$set": quiz})


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
                {"$sort": {"_id": 1}},
                {"$limit": settings.subset_size},
            ]
        )

        subset_without_details = client.quiz.questions.aggregate(
            [
                {"$match": {"question_set_id": question_set["_id"]}},
                {"$sort": {"_id": 1}},
                {"$skip": settings.subset_size},
                {
                    "$project": {
                        "graded": 1,
                        "type": 1,
                        "correct_answer": 1,
                        "question_set_id": 1,
                        "marking_scheme": 1,
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
    quiz_collection = client.quiz.quizzes
    if (quiz := quiz_collection.find_one({"_id": quiz_id})) is not None:
        update_quiz_for_backwards_compatibility(quiz_collection, quiz_id, quiz)
        return quiz

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"quiz {quiz_id} not found"
    )
