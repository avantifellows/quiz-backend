"""Shared OMR aggregation pipeline and option-count application."""

from fastapi import status, HTTPException
from database import get_quiz_db
from settings import Settings
from logger_config import get_logger

logger = get_logger()
settings = Settings()


async def aggregate_and_apply_omr_options(quiz: dict, entity_id: str) -> None:
    """Run the OMR option-count aggregation and apply results to quiz question sets.

    Modifies ``quiz["question_sets"]`` in place.  For each question beyond
    ``settings.subset_size``, replaces the ``options`` list with placeholder
    entries whose count matches the actual number of stored options.

    Raises:
        HTTPException(500): if a question_set_id present in the quiz has no
            matching aggregation result (data-integrity error).
    """
    db = get_quiz_db()

    question_set_ids = [
        question_set["_id"] for question_set in quiz["question_sets"]
    ]

    cursor = await db.questions.aggregate(
        [
            {"$match": {"question_set_id": {"$in": question_set_ids}}},
            {"$sort": {"_id": 1}},
            {
                "$project": {
                    "_id": 0,
                    "question_set_id": "$question_set_id",
                    "number_of_options": {"$size": "$options"},
                }
            },
            {
                "$group": {
                    "_id": "$question_set_id",
                    "options_count_per_set": {"$push": "$number_of_options"},
                }
            },
            {"$sort": {"_id": 1}},
            {"$project": {"_id": 1, "options_count_per_set": 1}},
        ]
    )
    raw_options_list = await cursor.to_list(length=None)
    options_count_across_sets = {
        item["_id"]: item["options_count_per_set"] for item in raw_options_list
    }

    for question_set_index, question_set in enumerate(quiz["question_sets"]):
        question_set_id = question_set["_id"]
        if question_set_id not in options_count_across_sets:
            logger.error(
                f"OMR option count missing for question_set_id={question_set_id} "
                f"in entity {entity_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OMR data integrity error",
            )
        options_count_per_set = options_count_across_sets[question_set_id]

        updated_subset_without_details = []
        for question_index, question in enumerate(question_set["questions"]):
            if question_index < settings.subset_size:
                continue

            # options_count will be zero for subjective/numerical questions
            question["options"] = [
                {"text": "", "image": None}
            ] * options_count_per_set[question_index]
            updated_subset_without_details.append(question)

        quiz["question_sets"][question_set_index]["questions"][
            settings.subset_size :
        ] = updated_subset_without_details
