from fastapi import APIRouter, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from database import client
from models import Quiz, GetQuizResponse, CreateQuizResponse
from settings import Settings
from schemas import QuizType
from logger_config import get_logger
from cache import cache_data_local, get_cached_data_local

router = APIRouter(prefix="/quiz", tags=["Quiz"])
settings = Settings()
logger = get_logger()


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
async def get_quiz(quiz_id: str):
    logger.info(f"Starting to get quiz: {quiz_id}")
    cache_key = f"quiz_{quiz_id}"
    quiz_collection = client.quiz.quizzes

    cached_data = get_cached_data_local(cache_key)
    if cached_data:
        logger.info(f"Finished getting quiz from cache: {quiz_id}")
        return cached_data

    logger.info(f"Fetching quiz from database: {quiz_id}")
    if (quiz := quiz_collection.find_one({"_id": quiz_id})) is None:
        logger.warning(f"Requested quiz {quiz_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"quiz {quiz_id} not found"
        )

    if (
        "metadata" not in quiz
        or quiz["metadata"] is None
        or "quiz_type" not in quiz["metadata"]
        or quiz["metadata"]["quiz_type"] != QuizType.omr.value
    ):
        logger.warning(
            f"Quiz {quiz_id} does not have metadata or is not an OMR quiz, skipping option count calculation"
        )

    else:
        logger.info(
            f"Quiz is an OMR type, calculating options count for quiz: {quiz_id}"
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

                # options_count will be zero for subjective/numerical questions
                question["options"] = [
                    {"text": "", "image": None}
                ] * options_count_per_set[question_index]
                updated_subset_without_details.append(question)

            quiz["question_sets"][question_set_index]["questions"][
                settings.subset_size :
            ] = updated_subset_without_details

    cache_data_local(cache_key, quiz)

    logger.info(f"Finished getting quiz: {quiz_id}")
    return quiz
