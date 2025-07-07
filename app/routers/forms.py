from fastapi import APIRouter, status, HTTPException
from database import client
from models import GetQuizResponse
from schemas import QuizType
from logger_config import get_logger

router = APIRouter(prefix="/form", tags=["Form"])
logger = get_logger()


@router.get("/{form_id}", response_model=GetQuizResponse)
async def get_form(form_id: str):
    """
    Get a form by ID. Unlike the quiz endpoint, this validates that the item is actually a form.
    Forms do not support OMR mode, so no omr_mode parameter is needed.
    """
    logger.info(f"Starting to get form: {form_id}")
    quiz_collection = client.quiz.quizzes

    if (quiz := quiz_collection.find_one({"_id": form_id})) is None:
        logger.warning(f"Requested form {form_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"form {form_id} not found"
        )

    # Validate that this is actually a form
    if (
        "metadata" not in quiz
        or quiz["metadata"] is None
        or "quiz_type" not in quiz["metadata"]
        or quiz["metadata"]["quiz_type"] != QuizType.form.value
    ):
        logger.warning(f"Item {form_id} is not a form (quiz_type: {quiz.get('metadata', {}).get('quiz_type', 'unknown')})")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"form {form_id} not found"
        )

    logger.info(f"Finished getting form: {form_id}")
    return quiz 