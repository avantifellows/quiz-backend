from copy import deepcopy

from fastapi import APIRouter, status, HTTPException, Query
from database import get_quiz_db
from models import GetQuizResponse
from schemas import QuizType
from logger_config import get_logger
from cache import get_cached_quiz, cache_get, cache_set, cache_key
from services.omr import aggregate_and_apply_omr_options

router = APIRouter(prefix="/form", tags=["Form"])
logger = get_logger()


@router.get("/{form_id}", response_model=GetQuizResponse)
async def get_form(
    form_id: str, omr_mode: bool = Query(False), single_page_mode: bool = Query(False)
):
    """
    Get a form by ID. Unlike the quiz endpoint, this validates that the item is actually a form.
    Forms support both OMR mode and single page mode with full text.
    """
    logger.info(
        f"Starting to get form: {form_id} with omr_mode={omr_mode}, single_page_mode={single_page_mode}"
    )

    quiz = await get_cached_quiz(form_id)
    if quiz is None:
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
        logger.warning(
            f"Item {form_id} is not a form (quiz_type: {quiz.get('metadata', {}).get('quiz_type', 'unknown')})"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"form {form_id} not found"
        )

    quiz = deepcopy(quiz)

    # Handle single page mode with full text (non-OMR)
    if single_page_mode and not omr_mode:
        logger.info(
            f"Single page mode with full text enabled for form: {form_id}, fetching all questions"
        )
        db = get_quiz_db()
        for question_set_index, question_set in enumerate(quiz["question_sets"]):
            qset_id = question_set["_id"]
            qset_cache_key = cache_key("questions", "qset", qset_id)
            cached_questions = await cache_get(qset_cache_key)
            if cached_questions is not None:
                all_questions = cached_questions
            else:
                all_questions = (
                    await db.questions.find({"question_set_id": qset_id})
                    .sort("_id", 1)
                    .to_list(length=None)
                )
                await cache_set(qset_cache_key, all_questions, ttl_seconds=3600)
            quiz["question_sets"][question_set_index]["questions"] = all_questions
        logger.info(f"Finished fetching all questions for single page mode: {form_id}")
        return quiz

    if omr_mode is False and (
        "metadata" not in quiz
        or quiz["metadata"] is None
        or "quiz_type" not in quiz["metadata"]
        or quiz["metadata"]["quiz_type"] != QuizType.omr.value
    ):
        logger.warning(
            f"omr_mode is False and Form {form_id} does not have metadata or is not an OMR form, skipping option count calculation"
        )

    else:
        logger.info(
            f"Form has to be rendered in OMR Mode, calculating options count for form: {form_id}"
        )
        await aggregate_and_apply_omr_options(quiz, form_id)

    logger.info(f"Finished getting form: {form_id}")
    return quiz
