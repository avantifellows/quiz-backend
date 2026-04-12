from fastapi import status, HTTPException
from database import get_quiz_db
from logger_config import get_logger

logger = get_logger()


async def apply_quiz_backwards_compatibility_fixup(quiz_id, quiz):
    """
    if given quiz contains question sets that do not have max_questions_allowed_to_attempt key,
    update the question sets (in-place) with the key and value as len(questions) in that set.
    Additionally, add a default title and marking scheme for the set.
    Finally, update the quiz in the database.
    (NOTE: this is a primitive form of versioning)
    """
    is_backwards_compatibile = True
    for question_set_index, question_set in enumerate(quiz["question_sets"]):
        if "max_questions_allowed_to_attempt" not in question_set:
            is_backwards_compatibile = False
            question_set["max_questions_allowed_to_attempt"] = len(
                question_set["questions"]
            )
            question_set["title"] = "Section A"

        if (
            "marking_scheme" not in question_set
            or question_set["marking_scheme"] is None
        ):
            is_backwards_compatibile = False
            question_marking_scheme = question_set["questions"][0]["marking_scheme"]
            if question_marking_scheme is not None:
                question_set["marking_scheme"] = question_marking_scheme
            else:
                question_set["marking_scheme"] = {
                    "correct": 1,
                    "wrong": 0,
                    "skipped": 0,
                }  # default

    if is_backwards_compatibile:
        logger.info("Quiz is already backwards compatible")
        return

    logger.info("Starting update for backwards compatibility")
    db = get_quiz_db()
    update_result = await db.quizzes.update_one({"_id": quiz_id}, {"$set": quiz})

    if not update_result.acknowledged:
        logger.error("Failed to update quiz for backwards compatibility")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update quiz for backwards compatibility",
        )

    logger.info("Quiz updated for backwards compatibility")
