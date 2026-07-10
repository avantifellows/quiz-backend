"""
Answer-visibility time computation for quiz sessions.

The quiz-taking frontend defers answer/solution review until the wall-clock passes
`quiz.metadata.session_end_time` (Player.vue, when review_immediate is false). To stop a
student who is still mid-test from seeing answers, that stored time must be the moment the
LAST possible attempt could finish: the session window end PLUS the quiz duration
(`time_limit.max`), NOT the raw window end.

This mirrors the legacy sessionCreator exactly (etl-data-flow
flows/sessionCreator/SessionCreator.py `_quiz_answer_visibility_end_time`), which this
service's create/patch/regenerate paths replace. Ported verbatim so a session edited or
regenerated here stores the same value the legacy Lambda would have.
"""

from datetime import datetime, timedelta
from typing import Any, Optional

from logger_config import get_logger

logger = get_logger()

# Non-ISO wall-clock formats we accept, in addition to datetime.fromisoformat. The 12-hour
# "%I:%M:%S %p" form is what the quiz doc has historically stored (and what the LMS emits
# today), so it must parse or the duration offset would be silently dropped.
_FALLBACK_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %I:%M:%S %p")


def parse_quiz_end_time(end_time: Any) -> Optional[datetime]:
    """Parse a window-end value (ISO string, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %I:%M:%S %p", or
    datetime) into a naive datetime (tz stripped, microseconds zeroed). None if unparseable.
    """
    if not end_time:
        return None

    if isinstance(end_time, datetime):
        parsed = end_time
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
        return parsed.replace(microsecond=0)

    if not isinstance(end_time, str):
        return None

    normalized = end_time
    if normalized.endswith("Z"):
        normalized = normalized.replace("Z", "+00:00")

    parsed = None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in _FALLBACK_FORMATS:
            try:
                parsed = datetime.strptime(normalized, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None

    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)

    return parsed.replace(microsecond=0)


def quiz_duration_seconds(time_limit: Any) -> int:
    """The quiz duration in seconds from a time_limit {min, max} dict. 0 if unset/untimed."""
    if not isinstance(time_limit, dict):
        return 0
    try:
        return int(time_limit.get("max") or 0)
    except (TypeError, ValueError):
        return 0


def answer_visibility_end_time(window_end: Any, time_limit: Any) -> Optional[str]:
    """Answer-visibility moment = window_end + quiz duration, as an isoformat string.

    Returns None if `window_end` is falsy, or the original value (unchanged) if it cannot be
    parsed — matching legacy, which never fabricates a time it can't derive."""
    if not window_end:
        return None
    parsed = parse_quiz_end_time(window_end)
    if parsed is None:
        # Can't derive the visibility offset — store the value as given (legacy behaviour),
        # but make the dropped offset visible rather than a silent early-answer hole.
        logger.warning(
            f"session window end {window_end!r} is unparseable; storing without the "
            "quiz-duration offset (answer review may open at the window end, not later)"
        )
        return window_end
    return (parsed + timedelta(seconds=quiz_duration_seconds(time_limit))).isoformat()
