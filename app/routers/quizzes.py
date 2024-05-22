from fastapi import APIRouter, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from database import client
from models import (
    Quiz,
    GetQuizResponse,
    CreateQuizResponse,
    GenerateReviewQuiz,
    ReviewQuiz,
)
from settings import Settings
from schemas import QuizType, ReviewQuizType
from logger_config import get_logger
import json
import boto3
import os

sns_client = boto3.client(
    "sns",
    region_name="ap-south-1",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)

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
async def get_quiz(quiz_id: str):
    logger.info(f"Starting to get quiz: {quiz_id}")
    quiz_collection = client.quiz.quizzes

    if (quiz := quiz_collection.find_one({"_id": quiz_id})) is None:
        logger.warning(f"Requested quiz {quiz_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"quiz {quiz_id} not found"
        )

    update_quiz_for_backwards_compatibility(quiz_collection, quiz_id, quiz)

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


@router.get("/generate-review")
async def generate_review_quiz(review_params: GenerateReviewQuiz):
    review_params = jsonable_encoder(review_params)
    quiz_id = review_params["quiz_id"]

    quiz = client.quiz.quizzes.find_one({"_id": quiz_id})

    if quiz is None:
        print("No quiz exists for given id")
        return

    if (
        "is_review_quiz_requested" not in quiz
        or quiz["is_review_quiz_requested"] is False
    ):
        # trigger sns
        message = {
            "action": "review_quiz",
            "review_type": ReviewQuizType.review_quiz.value,
            "quiz_id": quiz_id,
            "environment": "staging",
        }
        response = sns_client.publish(
            TargetArn="arn:aws:sns:ap-south-1:111766607077:etl-assessments",
            Message=json.dumps(message),
            MessageStructure="string",
        )
        if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
            print(
                "Requested For Review Quiz Generation. Please wait for a few minutes."
            )
            quiz["is_review_quiz_requested"] = True
            client.quiz.quizzes.update_one({"_id": quiz_id}, {"$set": quiz})
        else:
            print("Request failed.")
    elif (
        "is_review_quiz_requested" in quiz and quiz["is_review_quiz_requested"] is True
    ):
        review_quiz = client.quiz.review_quizzes.find_one(
            {"review_type": ReviewQuizType.review_session.value, "quiz_id": quiz_id}
        )

        if review_quiz is not None:
            return review_quiz["_id"]
        else:
            print(f"Review quiz for {quiz_id} is still being generated. Please wait.")


@router.post("/review", response_model=CreateQuizResponse)
async def create_review_quiz(review_quiz: ReviewQuiz):
    review_quiz = jsonable_encoder(review_quiz)

    for question_set_index, question_set in enumerate(review_quiz["question_sets"]):
        questions = question_set["questions"]
        for question_index, _ in enumerate(questions):
            questions[question_index]["question_set_id"] = question_set["_id"]

        result = client.quiz.questions.insert_many(questions)
        if not result.acknowledged:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Review Questions Insertion Error",
            )

        review_quiz["question_sets"][question_set_index]["questions"] = questions

    new_quiz_result = client.quiz.review_quizzes.insert_one(review_quiz)
    if not new_quiz_result.acknowledged:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Review Quiz Insertion Error",
        )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED, content={"id": new_quiz_result.inserted_id}
    )


@router.get("/review/{quiz_id}", response_model=GetQuizResponse)
async def get_review_quiz(quiz_id: str):
    review_quiz_collection = client.quiz.review_quizzes

    if (quiz := review_quiz_collection.find_one({"_id": quiz_id})) is None:
        logger.warning(f"Requested quiz {quiz_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"quiz {quiz_id} not found"
        )

    return quiz
