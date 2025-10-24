from fastapi import APIRouter, status, HTTPException, Query
from database import client
from models import GetQuizResponse
from schemas import QuizType
from settings import Settings
from logger_config import get_logger

router = APIRouter(prefix="/form", tags=["Form"])
settings = Settings()
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
        logger.warning(
            f"Item {form_id} is not a form (quiz_type: {quiz.get('metadata', {}).get('quiz_type', 'unknown')})"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"form {form_id} not found"
        )

    # Handle single page mode with full text (non-OMR)
    if single_page_mode and not omr_mode:
        logger.info(
            f"Single page mode with full text enabled for form: {form_id}, fetching all questions"
        )
        # Fetch all questions with full details for each question set
        for question_set_index, question_set in enumerate(quiz["question_sets"]):
            all_questions = list(
                client.quiz.questions.find(
                    {"question_set_id": question_set["_id"]}
                ).sort("_id", 1)
            )
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
        question_set_ids = [
            question_set["_id"] for question_set in quiz["question_sets"]
        ]

        # find questions with given question set ids
        # count number of options for each question in a qset id
        # group them together into an optionsArray
        options_count_across_sets = list(
            client.quiz.questions.aggregate(
                [
                    {"$match": {"question_set_id": {"$in": question_set_ids}}},
                    {"$sort": {"_id": 1}},  # sort questions based on question_id
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
                    {"$sort": {"_id": 1}},  # sort sets based on question_set_id
                    {"$project": {"_id": 0, "options_count_per_set": 1}},
                ]
            )
        )
        for question_set_index, question_set in enumerate(quiz["question_sets"]):
            updated_subset_without_details = []
            options_count_per_set = options_count_across_sets[question_set_index][
                "options_count_per_set"
            ]
            for question_index, question in enumerate(question_set["questions"]):
                if question_index < settings.subset_size:
                    continue

                # options_count will be zero for subbjective/numerical questions
                question["options"] = [
                    {"text": "", "image": None}
                ] * options_count_per_set[question_index]
                updated_subset_without_details.append(question)

            quiz["question_sets"][question_set_index]["questions"][
                settings.subset_size :
            ] = updated_subset_without_details

    logger.info(f"Finished getting form: {form_id}")
    return quiz
