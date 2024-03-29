from fastapi import APIRouter, status, HTTPException
from database import client
from models import QuestionResponse
from logger_config import get_logger

router = APIRouter(prefix="/questions", tags=["Questions"])
logger = get_logger()


@router.get("/{question_id}", response_model=QuestionResponse)
async def get_question(question_id: str):
    logger.info(f"Fetching question with ID: {question_id}")
    if (question := client.quiz.questions.find_one({"_id": question_id})) is not None:
        logger.info(f"Found question with ID: {question_id}")
        return question

    logger.error(f"Question {question_id} not found")
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Question {question_id} not found",
    )


@router.get("/")
async def get_questions(question_set_id: str, skip: int = None, limit: int = None):
    logger.info(
        f"Fetching questions with question_set_id: {question_set_id} with skip: {skip} and limit: {limit}"
    )
    pipeline = [
        {"$match": {"question_set_id": question_set_id}},
        {"$sort": {"_id": 1}},
    ]

    if skip:
        pipeline.append({"$skip": skip})

    if limit:
        pipeline.append({"$limit": limit})

    if (questions := list(client.quiz.questions.aggregate(pipeline))) is not None:
        logger.info(
            f"Found {len(questions)} questions with question_set_id: {question_set_id}"
        )
        return questions

    error_message = (
        f"No questions found belonging to question_set_id: {question_set_id}"
    )
    logger.error(error_message)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=error_message,
    )
