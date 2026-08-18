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


def session_answers_meta_projection() -> Dict[str, Any]:
    """The ``$project`` fragment both answer-update paths need before writing: the number of
    session answers, without loading the (~33 KB) array itself.

    ``num_answers`` is the array length, or ``None`` when ``session_answers`` isn't a proper
    array — that ``None`` is the single "no valid answers array" signal consumed by
    ``validate_answer_update_bounds``.
    """
    return {
        "num_answers": {
            "$cond": [
                {"$isArray": "$session_answers"},
                {"$size": "$session_answers"},
                None,
            ]
        }
    }


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
    num_answers: Optional[int],
    session_id: str,
) -> None:
    """Checks that need the session's answer-array shape (from a lightweight projection): the
    array exists (404) and every position is within bounds (400, position == length is rejected).
    """
    if num_answers is None:
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
    positions_and_answers: List[Tuple[int, UpdateSessionAnswer]],
    *,
    drop_updated_at_for_timing_only_items: bool = False,
) -> Dict[str, Any]:
    """Build the Mongo ``$set`` fields (``session_answers.{pos}.{field}``) for the given updates.

    Per-answer ``updated_at`` records when a student last modified that answer.
    ``remove_optional_unset_args`` always keeps it (``default_factory``), so it is present on
    the cleaned model without the client having to send it, and genuine answer-save paths
    (the batch end-of-test flush) keep it — that is the default.

    The heartbeat fold passes ``drop_updated_at_for_timing_only_items=True``. It fires every 20s
    and normally carries only ``time_spent``: for an item that touched *exactly* ``time_spent``
    (a timer tick, not an answer edit) ``updated_at`` is dropped, since bumping it would be write
    amplification on the hot path and would misrepresent a tick as an edit. Any other business
    field (``answer``/``visited``/``marked_for_review``) makes it a real edit, so ``updated_at``
    is kept — otherwise the stored timestamp would say "not touched" about an answer that was.
    (Empty items never reach here — they are rejected by validate_answer_updates_before_read —
    so the ``== {"time_spent"}`` gate is exact rather than treating a no-op item as a tick.)
    """
    set_fields: Dict[str, Any] = {}
    for position, answer in positions_and_answers:
        cleaned = jsonable_encoder(remove_optional_unset_args(answer))
        touched_fields = answer.model_fields_set & BUSINESS_FIELDS
        if drop_updated_at_for_timing_only_items and touched_fields == {"time_spent"}:
            cleaned.pop("updated_at", None)
        for key, value in cleaned.items():
            set_fields[f"session_answers.{position}.{key}"] = value
    return set_fields
