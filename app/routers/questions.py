from fastapi import APIRouter, status, HTTPException
from database import client
from models import QuestionResponse
from logger_config import get_logger
from cache import cache_data_local, get_cached_data_local

router = APIRouter(prefix="/questions", tags=["Questions"])
logger = get_logger()


@router.get("/{question_id}", response_model=QuestionResponse)
async def get_question(question_id: str):
    logger.info(f"Fetching question with ID: {question_id}")
    cache_key = f"question_{question_id}"
    cached_data = get_cached_data_local(cache_key)
    if cached_data:
        logger.info(f"Found question with ID: {question_id} in cache")
        return cached_data

    if (question := client.quiz.questions.find_one({"_id": question_id})) is not None:
        logger.info(f"Found question with ID: {question_id}")
        cache_data_local(cache_key, question)
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

    cache_key = f"questions_in_qset_{question_set_id}_skip_{skip}_limit_{limit}"
    cached_data = get_cached_data_local(cache_key)
    if cached_data:
        logger.info(f"Found questions with question_set_id: {question_set_id} in cache")
        return cached_data

    # if not cached, fetch from database
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
        cache_data_local(cache_key, questions)
        return questions

    error_message = (
        f"No questions found belonging to question_set_id: {question_set_id}"
    )
    logger.error(error_message)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=error_message,
    )
