"""Form-builder definitions: the editable forms quiz-creator's builder saves (collection
`form_definitions`). A session's quiz is built from one by POST /quiz/from-form-definition
(routers/quizzes.py), which also locks it. Decisions: docs/form-builder/decisions.md
(D10 storage, D13 lock, D14 list, D16 no auth — like the rest of this API).
"""

import re
from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import get_quiz_db
from logger_config import get_logger
from models import FormDefinition, FormDefinitionWrite
from schemas import QuizSource
from services.form_definition_build import (
    completeness_errors,
    structure_errors,
    summary_counts,
)

router = APIRouter(prefix="/form-definitions", tags=["Form definitions"])
logger = get_logger()

# What the list returns per form (everything except the sections).
_SUMMARY_FIELDS = (
    "title",
    "languages",
    "locked_at",
    "question_count",
    "conditional_count",
    "ready",
    "created_by",
    "created_at",
    "updated_by",
    "updated_at",
)


def _checked_content(request: FormDefinitionWrite) -> dict:
    """The request's content as a stored-document fragment, with derived fields. Rejects an
    inconsistent definition (422); an incomplete one is saved with ready=False."""
    content = request.model_dump(exclude={"actor"})
    errors = structure_errors(content)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=errors
        )
    return {
        **content,
        **summary_counts(content),
        "ready": not completeness_errors(content),
    }


@router.get("/")
async def list_form_definitions(
    search: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ready_only: bool = False,
):
    """Forms, most recently updated first. `search` matches the title (case-insensitive,
    anywhere in it); `ready_only` keeps only forms a session can use (the session picker).
    """
    db = get_quiz_db()
    query: dict = {}
    if search and search.strip():
        query["title"] = {"$regex": re.escape(search.strip()), "$options": "i"}
    if ready_only:
        query["ready"] = True
    cursor = (
        db.form_definitions.find(query, {field: 1 for field in _SUMMARY_FIELDS})
        .sort([("updated_at", -1), ("_id", -1)])
        .skip(offset)
        .limit(limit + 1)
    )
    rows = await cursor.to_list(length=None)
    return {"items": jsonable_encoder(rows[:limit]), "has_more": len(rows) > limit}


@router.get("/{definition_id}")
async def get_form_definition(definition_id: str):
    definition = await get_quiz_db().form_definitions.find_one({"_id": definition_id})
    if definition is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"form definition {definition_id} not found",
        )
    return jsonable_encoder(definition)


@router.get("/{definition_id}/sessions")
async def list_form_definition_sessions(definition_id: str):
    """The quizzes built from this form, one per session, oldest first. Each quiz's title is
    the session name (sessionCreator sets it)."""
    cursor = get_quiz_db().quizzes.find(
        {
            "metadata.source": QuizSource.form_builder.value,
            "metadata.source_id": definition_id,
        },
        {"title": 1},
    )
    quizzes = await cursor.to_list(length=None)
    sessions = [
        {
            "quiz_id": quiz["_id"],
            "title": quiz.get("title"),
            # quiz ids are ObjectId strings, so they carry their creation time
            "created_at": ObjectId(quiz["_id"]).generation_time
            if ObjectId.is_valid(quiz["_id"])
            else None,
        }
        for quiz in quizzes
    ]
    sessions.sort(key=lambda row: str(row["quiz_id"]))
    return jsonable_encoder(sessions)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_form_definition(request: FormDefinitionWrite):
    content = _checked_content(request)
    definition = jsonable_encoder(
        FormDefinition(**content, created_by=request.actor, updated_by=request.actor)
    )
    # jsonable_encoder turns datetimes into strings; store real dates.
    now = datetime.utcnow()
    definition.update(created_at=now, updated_at=now, locked_at=None)
    await get_quiz_db().form_definitions.insert_one(definition)
    logger.info(f"Created form definition {definition['_id']} by {request.actor}")
    return JSONResponse(
        status_code=status.HTTP_201_CREATED, content={"id": definition["_id"]}
    )


async def _locked_or_missing(definition_id: str) -> HTTPException:
    """Why a conditional write on an unlocked definition matched nothing."""
    exists = await get_quiz_db().form_definitions.find_one(
        {"_id": definition_id}, {"_id": 1}
    )
    if exists is None:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"form definition {definition_id} not found",
        )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="This form was used in a session and can't be changed. Duplicate it to "
        "make changes.",
    )


@router.put("/{definition_id}")
async def save_form_definition(definition_id: str, request: FormDefinitionWrite):
    """Replace the content of an unlocked definition (last save wins, decision D18)."""
    content = _checked_content(request)
    result = await get_quiz_db().form_definitions.update_one(
        # the lock check is part of the write, so a session locking the form at the same
        # moment can't be overwritten
        {"_id": definition_id, "locked_at": None},
        {
            "$set": {
                **content,
                "updated_by": request.actor,
                "updated_at": datetime.utcnow(),
            }
        },
    )
    if result.matched_count == 0:
        raise await _locked_or_missing(definition_id)
    logger.info(f"Saved form definition {definition_id} by {request.actor}")
    return {"id": definition_id}


@router.delete("/{definition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_form_definition(definition_id: str):
    """Delete a definition that no session has used. A used (locked) one can't be deleted:
    its sessions' quizzes point back at it."""
    result = await get_quiz_db().form_definitions.delete_one(
        {"_id": definition_id, "locked_at": None}
    )
    if result.deleted_count == 0:
        raise await _locked_or_missing(definition_id)
    logger.info(f"Deleted form definition {definition_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
