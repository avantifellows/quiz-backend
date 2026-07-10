from typing import Optional

from fastapi import APIRouter, status, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from database import client
from models import Quiz, GetQuizResponse, CreateQuizResponse
from settings import Settings
from schemas import QuizType
from services.cms_ingest import (
    fetch_assembled_test,
    map_cms_test_to_quiz,
    CmsIngestError,
)
from services.quiz_time import answer_visibility_end_time
from logger_config import get_logger

router = APIRouter(prefix="/quiz", tags=["Quiz"])
settings = Settings()
logger = get_logger()


def _hide_answers_in_quiz_in_place(quiz: dict) -> None:
    """
    Hide answers/solutions from base quiz endpoint.
    Keep payload shape stable but ensure correct_answer/solution do not contain real data.
    """
    for question_set in quiz.get("question_sets") or []:
        for question in question_set.get("questions") or []:
            question["correct_answer"] = None
            question["solution"] = []


def _clear_solutions_in_place(quiz: dict) -> None:
    """Respect display_solution=False without sanitizing correct_answer."""
    for question_set in quiz.get("question_sets") or []:
        for question in question_set.get("questions") or []:
            question["solution"] = []


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


def _aggregate_question_set_subset(question_set_id) -> list:
    """Build the question list a quiz doc stores for one set: the first `subset_size`
    questions in full detail plus the rest projected to grading-only fields. The questions
    themselves live in full in the `questions` collection; this is the denormalized subset
    embedded on the quiz. Shared by create and regenerate so both produce the same shape.

    Questions are ordered by `_id`, which preserves authored order because ids are assigned
    in list order at insert time — the create and regenerate paths rely on this to keep the
    embedded subset aligned with the authored question order.
    """
    subset_with_details = client.quiz.questions.aggregate(
        [
            {"$match": {"question_set_id": question_set_id}},
            {"$sort": {"_id": 1}},
            {"$limit": settings.subset_size},
        ]
    )
    subset_without_details = client.quiz.questions.aggregate(
        [
            {"$match": {"question_set_id": question_set_id}},
            {"$sort": {"_id": 1}},
            {"$skip": settings.subset_size},
            {
                "$project": {
                    "graded": 1,
                    "force_correct": 1,
                    "type": 1,
                    "matrix_rows": 1,
                    "correct_answer": 1,
                    "question_set_id": 1,
                    "marking_scheme": 1,
                }
            },
        ]
    )
    return list(subset_with_details) + list(subset_without_details)


def _insert_quiz_with_questions(quiz: dict) -> str:
    """Insert a quiz (already jsonable-encoded) and its questions into Mongo, returning
    the new quiz id. Shared by the direct create endpoint and the CMS-ingest endpoint.
    """
    log_message = "Starting quiz creation"
    log_with_source = ""
    log_with_source_id = ""
    if "metadata" in quiz and quiz["metadata"] and "source" in quiz["metadata"]:
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

        quiz["question_sets"][question_set_index][
            "questions"
        ] = _aggregate_question_set_subset(question_set["_id"])

    new_quiz_result = client.quiz.quizzes.insert_one(quiz)
    if not new_quiz_result.acknowledged:
        error_message = f"Failed to insert quiz{log_with_source}{log_with_source_id}"
        logger.error(error_message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_message,
        )
    logger.info("Finished creating quiz with id: " + str(new_quiz_result.inserted_id))
    return new_quiz_result.inserted_id


class CmsQuizIngestRequest(BaseModel):
    """Body for POST /quiz/from-cms and PUT /quiz/{id}/from-cms — identifies a chapter test
    in the new CMS, plus the optional session window end used to derive answer-visibility.
    """

    test_id: int
    curriculum_id: int
    grade_id: int
    quiz_type: str = QuizType.assessment.value
    # Raw session window-end as an ISO wall-clock string (IST), e.g. "2026-04-15T14:00:00".
    # The stored metadata.session_end_time is this PLUS the quiz duration (see
    # services.quiz_time) so students still mid-test don't get early answer access. Optional:
    # untimed quizzes / callers that don't gate review can omit it.
    session_end_time: Optional[str] = None

    class Config:
        schema_extra = {
            "example": {
                "test_id": 504,
                "curriculum_id": 1,
                "grade_id": 1,
                "quiz_type": "assessment",
                "session_end_time": "2026-04-15T14:00:00",
            }
        }


@router.post("/", response_model=CreateQuizResponse)
async def create_quiz(quiz: Quiz):
    quiz = jsonable_encoder(quiz)
    quiz_id = _insert_quiz_with_questions(quiz)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content={"id": quiz_id})


@router.post("/from-cms", status_code=status.HTTP_201_CREATED)
async def create_quiz_from_cms(request: CmsQuizIngestRequest):
    """Fetch an assembled chapter test from the new CMS, map it into a native quiz, and
    store it. Returns the new quiz id plus any non-fatal mapping warnings."""
    logger.info(
        f"CMS ingest: test {request.test_id} (curriculum {request.curriculum_id}, "
        f"grade {request.grade_id})"
    )
    try:
        assembled = fetch_assembled_test(
            request.test_id, request.curriculum_id, request.grade_id
        )
        quiz_dict, warnings = map_cms_test_to_quiz(
            assembled, quiz_type=request.quiz_type
        )
    except CmsIngestError as exc:
        logger.error(f"CMS ingest failed for test {request.test_id}: {exc}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    # Answer-visibility time = window end + quiz duration (see services.quiz_time). Set here
    # at create so a CMS session with review_immediate=false defers review correctly; without
    # it the quiz doc has no session_end_time and the frontend never gates review.
    if request.session_end_time:
        quiz_dict.setdefault("metadata", {})[
            "session_end_time"
        ] = answer_visibility_end_time(
            request.session_end_time, quiz_dict.get("time_limit")
        )

    # Validate + fill defaults (ids, etc.) through the same model the direct endpoint uses.
    quiz = jsonable_encoder(Quiz(**quiz_dict))
    quiz_id = _insert_quiz_with_questions(quiz)

    if warnings:
        logger.warning(
            f"CMS ingest for test {request.test_id} produced warnings: {warnings}"
        )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "id": quiz_id,
            "source_id": str(request.test_id),
            "warnings": warnings,
        },
    )


# Session-editable settings that live on the quiz doc (not the CMS source). Regenerate must
# preserve these across a re-ingest — they were set by the LMS session-edit flow, not by the
# test content, so re-pulling the test must not reset them.
_SESSION_EDITABLE_QUIZ_FIELDS = ("title", "shuffle", "show_scores", "review_immediate")
_SESSION_EDITABLE_METADATA_FIELDS = ("grade", "single_page_header_text")


@router.put("/{quiz_id}/from-cms")
async def regenerate_quiz_from_cms(quiz_id: str, request: CmsQuizIngestRequest):
    """Re-ingest the (corrected) CMS test into an EXISTING quiz in place: the quiz keeps its
    _id and every question-set / question _id, so the session and any submitted attempts stay
    linked. Refreshes question content, answer key, marking, marks, timing and content
    metadata (test_format/subject); preserves the session-editable settings on the quiz doc
    (title, shuffle, show_scores, review_immediate, grade, single_page_header_text, and
    session_end_time unless a new window end is supplied). Mirrors the legacy sessionCreator
    regenerate path (patch_quiz_in_mongo, Mode B).

    Refuses with 409 if the regenerated test's structure differs from the existing quiz
    (different number of question sets, or a different question count in any set): the
    positional _id mapping that keeps attempts linked would otherwise silently misalign.
    """
    logger.info(
        f"CMS regenerate: quiz {quiz_id} from test {request.test_id} "
        f"(curriculum {request.curriculum_id}, grade {request.grade_id})"
    )
    quiz_collection = client.quiz.quizzes
    existing = quiz_collection.find_one({"_id": quiz_id})
    if existing is None:
        logger.warning(f"Requested quiz {quiz_id} not found for regenerate")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"quiz {quiz_id} not found"
        )

    try:
        assembled = fetch_assembled_test(
            request.test_id, request.curriculum_id, request.grade_id
        )
        new_quiz, warnings = map_cms_test_to_quiz(
            assembled, quiz_type=request.quiz_type
        )
    except CmsIngestError as exc:
        logger.error(f"CMS regenerate failed for test {request.test_id}: {exc}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    # Validate + fill defaults through the same model create uses (fresh set/question ids,
    # which we then overwrite positionally with the existing ones below).
    new_quiz = jsonable_encoder(Quiz(**new_quiz))

    # The regenerated test must line up POSITIONALLY with the existing quiz, or the _id
    # reuse below would remap answer keys onto the wrong questions and silently mis-score
    # submitted attempts. Validate fully BEFORE any write: same set count, same per-set
    # question count, and — the subtle one — the same question at each position. A
    # delete+add or a reorder keeps the counts but changes identity; anchor on the CMS
    # source_id (present on both sides for CMS quizzes) to catch it. Cache the fetched
    # existing question docs so the write pass doesn't re-read them.
    old_sets = existing.get("question_sets") or []
    new_sets = new_quiz["question_sets"]
    mismatch = None
    existing_questions = {}  # (set_index, question_index) -> full existing question doc
    if len(new_sets) != len(old_sets):
        mismatch = f"question-set count changed ({len(old_sets)} -> {len(new_sets)})"
    else:
        for i, (old_s, new_s) in enumerate(zip(old_sets, new_sets)):
            old_qs = old_s.get("questions") or []
            new_qs = new_s.get("questions") or []
            if len(old_qs) != len(new_qs):
                mismatch = f"question count in set {i} changed ({len(old_qs)} -> {len(new_qs)})"
                break
            for j, (old_q, new_q) in enumerate(zip(old_qs, new_qs)):
                existing_q = client.quiz.questions.find_one({"_id": old_q["_id"]}) or {}
                existing_questions[(i, j)] = existing_q
                old_src = existing_q.get("source_id")
                new_src = new_q.get("source_id")
                if old_src and new_src and str(old_src) != str(new_src):
                    mismatch = (
                        f"question {j} in set {i} is a different problem "
                        f"(source_id {old_src} -> {new_src})"
                    )
                    break
            if mismatch:
                break
    if mismatch:
        logger.warning(f"Regenerate refused for quiz {quiz_id}: {mismatch}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"regenerated test differs from the existing quiz: {mismatch}. Regenerate "
                "preserves attempt links by position and cannot remap a reshaped or "
                "reordered test; create a new session for it instead."
            ),
        )

    # Preserve the quiz _id and every set/question _id positionally, and refresh each question
    # doc in the questions collection in place (back-filling any keys the new mapping drops).
    # NOTE: this is not atomic — questions are replaced before the quiz doc, so a mid-loop
    # failure leaves refreshed questions with a stale embedded grading subset. Tracked as debt
    # (needs a replica-set transaction to fix); acceptable for a rare admin-triggered action.
    new_quiz["_id"] = quiz_id
    for i, new_s in enumerate(new_sets):
        old_s = old_sets[i]
        new_s["_id"] = old_s["_id"]
        for j, new_q in enumerate(new_s["questions"]):
            question_id = old_s["questions"][j]["_id"]
            new_q["_id"] = question_id
            new_q["question_set_id"] = new_s["_id"]
            existing_q = existing_questions.get((i, j)) or {}
            for key, value in existing_q.items():
                if key not in new_q:
                    new_q[key] = value
            client.quiz.questions.replace_one({"_id": question_id}, new_q)
        # Re-derive the embedded subset from the refreshed question docs.
        new_s["questions"] = _aggregate_question_set_subset(new_s["_id"])

    # Preserve session-editable settings the LMS set on the quiz doc (content comes from CMS).
    for field in _SESSION_EDITABLE_QUIZ_FIELDS:
        if field in existing:
            new_quiz[field] = existing[field]

    new_meta = new_quiz.get("metadata") or {}
    old_meta = existing.get("metadata") or {}
    for field in _SESSION_EDITABLE_METADATA_FIELDS:
        if old_meta.get(field) is not None:
            new_meta[field] = old_meta[field]
    if request.session_end_time:
        new_meta["session_end_time"] = answer_visibility_end_time(
            request.session_end_time, new_quiz.get("time_limit")
        )
    elif old_meta.get("session_end_time") is not None:
        new_meta["session_end_time"] = old_meta["session_end_time"]
    new_quiz["metadata"] = new_meta

    # Back-fill any other top-level keys the old doc carried but the new one lacks (legacy
    # parity — don't drop engine-added fields).
    for key, value in existing.items():
        if key not in new_quiz:
            new_quiz[key] = value

    result = quiz_collection.replace_one({"_id": quiz_id}, new_quiz)
    if not result.acknowledged:
        error_message = f"Failed to regenerate quiz {quiz_id}"
        logger.error(error_message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_message
        )

    if warnings:
        logger.warning(
            f"CMS regenerate for test {request.test_id} produced warnings: {warnings}"
        )
    logger.info(f"Regenerated quiz {quiz_id} from CMS test {request.test_id}")
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "id": quiz_id,
            "source_id": str(request.test_id),
            "warnings": warnings,
            "regenerated": True,
        },
    )


class QuizPatchRequest(BaseModel):
    """Body for PATCH /quiz/{quiz_id} — field-scoped update of the session-editable
    settings on an existing quiz doc. Only the fields that are sent are changed; the
    LMS session-edit flow decides which to send."""

    title: Optional[str] = None
    shuffle: Optional[bool] = None
    show_scores: Optional[bool] = None
    # "show answers immediately after submission" (off during concurrent testing)
    review_immediate: Optional[bool] = None
    # Raw session window-end (ISO wall-clock, e.g. "2026-04-15T14:00:00"). Stored as
    # metadata.session_end_time PLUS the quiz duration (answer-visibility time); see
    # services.quiz_time.
    session_end_time: Optional[str] = None


@router.patch("/{quiz_id}")
async def patch_quiz(quiz_id: str, request: QuizPatchRequest):
    """Patch session-editable settings on an existing quiz in place (same _id).

    Called by the LMS when a quiz session is edited so the display/scoring settings
    on the quiz doc stay in sync, without rebuilding the quiz or its questions.
    """
    quiz_collection = client.quiz.quizzes

    existing = quiz_collection.find_one(
        {"_id": quiz_id}, {"_id": 1, "metadata": 1, "time_limit": 1}
    )
    if existing is None:
        logger.warning(f"Requested quiz {quiz_id} not found for patch")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"quiz {quiz_id} not found"
        )

    set_ops = {}
    updated = []
    for field in ("title", "shuffle", "show_scores", "review_immediate"):
        value = getattr(request, field)
        if value is not None:
            set_ops[field] = value
            updated.append(field)
    if request.session_end_time is not None:
        updated.append("session_end_time")
        # Store the answer-visibility time (window end + quiz duration), reading the duration
        # off the existing quiz doc — matches legacy sessionCreator; see services.quiz_time.
        visibility_time = answer_visibility_end_time(
            request.session_end_time, existing.get("time_limit")
        )
        # A dotted $set ("metadata.session_end_time") raises when metadata is
        # explicitly null (Mongo can't traverse a null intermediate), so write the
        # whole subdoc in that case. An absent metadata is fine with dot-notation.
        if existing.get("metadata") is None:
            set_ops["metadata"] = {"session_end_time": visibility_time}
        else:
            set_ops["metadata.session_end_time"] = visibility_time

    if not set_ops:
        return JSONResponse(
            status_code=status.HTTP_200_OK, content={"id": quiz_id, "updated": []}
        )

    result = quiz_collection.update_one({"_id": quiz_id}, {"$set": set_ops})
    if not result.acknowledged:
        error_message = f"Failed to patch quiz {quiz_id}"
        logger.error(error_message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_message
        )
    if result.matched_count == 0:
        # Deleted between the existence check and the write.
        logger.warning(f"Quiz {quiz_id} vanished before patch could apply")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"quiz {quiz_id} not found"
        )
    logger.info(f"Patched quiz {quiz_id}: {updated}")
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"id": quiz_id, "updated": updated},
    )


@router.get("/{quiz_id}", response_model=GetQuizResponse)
async def get_quiz(
    quiz_id: str,
    omr_mode: bool = Query(False),
    single_page_mode: bool = Query(False),
    include_answers: bool = Query(False),
):
    logger.info(
        f"Starting to get quiz: {quiz_id} with omr_mode={omr_mode}, single_page_mode={single_page_mode}, include_answers={include_answers}"
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
        if quiz.get("display_solution", True) is False:
            _clear_solutions_in_place(quiz)
        if not include_answers:
            _hide_answers_in_quiz_in_place(quiz)
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

    if quiz.get("display_solution", True) is False:
        _clear_solutions_in_place(quiz)

    # Base quiz endpoint must not return correct answers/solutions.
    # When include_answers=true, preserve correct_answer (and solutions if enabled).
    if not include_answers:
        _hide_answers_in_quiz_in_place(quiz)

    logger.info(f"Finished getting quiz: {quiz_id}")
    return quiz
