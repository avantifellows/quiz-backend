from fastapi import APIRouter, status, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from database import client
from models import Quiz, GetQuizResponse, CreateQuizResponse
from settings import Settings
from schemas import QuizType
from logger_config import get_logger

router = APIRouter(prefix="/quiz", tags=["Quiz"])
settings = Settings()
logger = get_logger()


def update_quiz_for_backwards_compatibility(quiz_collection, quiz_id, quiz):
    """
    if given quiz contains question sets that do not have max_questions_allowed_to_attempt key,
    update the question sets (in-place) with the key and value as len(questions) in that set.
    Additionally, add a default title and marking scheme for the set.
    Finally, add quiz to quiz_collection
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
    update_result = quiz_collection.update_one({"_id": quiz_id}, {"$set": quiz})

    if not update_result.acknowledged:
        logger.error("Failed to update quiz for backwards compatibility")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update quiz for backwards compatibility",
        )

    logger.info("Quiz updated for backwards compatibility")


@router.post("/", response_model=CreateQuizResponse)
async def create_quiz(quiz: Quiz):
    quiz = jsonable_encoder(quiz)

    log_message = "Starting quiz creation"
    log_with_source = ""
    log_with_source_id = ""
    if "metadata" in quiz and "source" in quiz["metadata"]:
        log_with_source = f" with source {quiz['metadata']['source']}"
        log_message += log_with_source
        if "source_id" in quiz["metadata"]:
            log_with_source_id = f" and source id {quiz['metadata']['source_id']}"
            log_message += log_with_source_id

    logger.info(log_message)

    for question_set_index, question_set in enumerate(quiz["question_sets"]):
        questions = question_set["questions"]
        for question_index, _ in enumerate(questions):
            questions[question_index]["question_set_id"] = question_set["_id"]

        result = client.quiz.questions.insert_many(questions)
        if result.acknowledged:
            logger.info(
                f"Inserted {len(questions)} questions for quiz{log_with_source}{log_with_source_id}"
            )
        else:
            error_message = f"Failed to insert questions for quiz{log_with_source}{log_with_source_id}"
            logger.error(error_message)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_message,
            )

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

    new_quiz_result = client.quiz.quizzes.insert_one(quiz)
    if not new_quiz_result.acknowledged:
        error_message = f"Failed to insert quiz{log_with_source}{log_with_source_id}"
        logger.error(error_message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_message,
        )
    logger.info("Finished creating quiz with id: " + str(new_quiz_result.inserted_id))

    return JSONResponse(
        status_code=status.HTTP_201_CREATED, content={"id": new_quiz_result.inserted_id}
    )


@router.get("/{quiz_id}", response_model=GetQuizResponse)
async def get_quiz(
    quiz_id: str, omr_mode: bool = Query(False), single_page_mode: bool = Query(False)
):
    logger.info(
        f"Starting to get quiz: {quiz_id} with omr_mode={omr_mode}, single_page_mode={single_page_mode}"
    )
    quiz_collection = client.quiz.quizzes

    if (quiz := quiz_collection.find_one({"_id": quiz_id})) is None:
        logger.warning(f"Requested quiz {quiz_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"quiz {quiz_id} not found"
        )

    # Validate that this is not a form (forms should use /form endpoint)
    if (
        "metadata" in quiz
        and quiz["metadata"] is not None
        and "quiz_type" in quiz["metadata"]
        and quiz["metadata"]["quiz_type"] == QuizType.form.value
    ):
        logger.warning(
            f"Item {quiz_id} is a form (quiz_type: {quiz['metadata']['quiz_type']}), should use /form endpoint"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"quiz {quiz_id} not found"
        )

    update_quiz_for_backwards_compatibility(quiz_collection, quiz_id, quiz)

    # Handle single page mode with full text (non-OMR)
    if single_page_mode and not omr_mode:
        logger.info(
            f"Single page mode with full text enabled for quiz: {quiz_id}, fetching all questions"
        )
        # Fetch all questions with full details for each question set
        for question_set_index, question_set in enumerate(quiz["question_sets"]):
            all_questions = list(
                client.quiz.questions.find(
                    {"question_set_id": question_set["_id"]}
                ).sort("_id", 1)
            )
            quiz["question_sets"][question_set_index]["questions"] = all_questions
        logger.info(f"Finished fetching all questions for single page mode: {quiz_id}")
        return quiz

    if omr_mode is False and (
        "metadata" not in quiz
        or quiz["metadata"] is None
        or "quiz_type" not in quiz["metadata"]
        or quiz["metadata"]["quiz_type"] != QuizType.omr.value
    ):
        logger.warning(
            f"omr_mode is False and Quiz {quiz_id} does not have metadata or is not an OMR quiz, skipping option count calculation"
        )

    else:
        logger.info(
            f"Quiz has to be rendered in OMR Mode, calculating options count for quiz: {quiz_id}"
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

    logger.info(f"Finished getting quiz: {quiz_id}")
    return quiz
