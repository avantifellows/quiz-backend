"""Shared validation + $set building for positional session-answer updates.

Both the batch endpoint (`PATCH /session_answers/{id}/update-multiple-answers`) and the folded
heartbeat path (`answer_updates` on `PATCH /sessions/{id}`) apply the same positional updates to
`session_answers.{pos}.{field}`. Keeping the logic here means both enforce the same contract
(same 400/404s) instead of drifting per endpoint.
"""

from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder

from models import UpdateSessionAnswer
from utils import remove_optional_unset_args

# A session-answer update must set at least one of these; used to reject no-op payloads.
BUSINESS_FIELDS = {"answer", "visited", "time_spent", "marked_for_review"}


def validate_answer_updates_before_read(
    positions_and_answers: List[Tuple[int, UpdateSessionAnswer]]
) -> None:
    """Payload-only checks that need no DB read (so callers can reject before touching Mongo):
    negative index, duplicate positions, and empty per-item payload — each a 400.

    Does not handle the empty-batch case; callers differ (the batch endpoint 400s on it, while
    the heartbeat simply has nothing to fold).
    """
    positions = [position for position, _ in positions_and_answers]

    if any(position < 0 for position in positions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more provided position indices are negative",
        )

    if len(positions) != len(set(positions)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate position indices are not allowed in a single batch update request",
        )

    for position, answer in positions_and_answers:
        if not (answer.model_fields_set & BUSINESS_FIELDS):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Empty payload at position {position}: at least one business field "
                    "(answer, visited, time_spent, marked_for_review) must be provided"
                ),
            )


def validate_answer_update_bounds(
    positions_and_answers: List[Tuple[int, UpdateSessionAnswer]],
    *,
    session_answers_is_array: bool,
    num_answers: Optional[int],
    session_id: str,
) -> None:
    """Checks that need the session's answer-array shape (from a lightweight projection): the
    array exists (404) and every position is within bounds (400, position == length is rejected).
    """
    if not session_answers_is_array or num_answers is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No session answers found in the session with id {session_id}",
        )

    if any(position >= num_answers for position, _ in positions_and_answers):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more provided position indices are out of bounds of the session answers array",
        )


def build_answer_update_set(
    positions_and_answers: List[Tuple[int, UpdateSessionAnswer]]
) -> Dict[str, Any]:
    """Build the Mongo ``$set`` fields (``session_answers.{pos}.{field}``) for the given updates.

    Per-answer ``updated_at`` is intentionally dropped: nothing reads it, and
    ``remove_optional_unset_args`` always keeps it (``default_factory``), which would otherwise
    double the field writes on the hot heartbeat path. The session-level ``updated_at`` bump is
    the caller's responsibility.
    """
    set_fields: Dict[str, Any] = {}
    for position, answer in positions_and_answers:
        cleaned = jsonable_encoder(remove_optional_unset_args(answer))
        cleaned.pop("updated_at", None)
        for key, value in cleaned.items():
            set_fields[f"session_answers.{position}.{key}"] = value
    return set_fields
