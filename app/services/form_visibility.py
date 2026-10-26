"""Conditional question display for forms: the single backend evaluator of which questions
a student is shown. Used by the session routes (required-answer check on end-quiz) and by
scoring (session metrics), so both always agree."""

from typing import Any, Dict, List, Optional


def answer_option_indices(
    answer: Any, question_type: Optional[str] = None
) -> List[int]:
    """Selected 0-based option indices from a choice answer. Single/multi-choice store a
    list of indices; single-choice-other stores {"selected": [...], "other_text": ...}.
    Other answer shapes (matrix dicts, numerical values) cannot drive a display_condition,
    so they contribute no indices. The question type is needed because matrix answers are
    dicts too."""
    if question_type == "single-choice-other":
        answer = answer.get("selected") if isinstance(answer, dict) else None
    if isinstance(answer, list):
        return [index for index in answer if isinstance(index, int)]
    return []


def compute_form_question_visibility(
    flat_questions: List[Dict[str, Any]], session_answers: List[Dict[str, Any]]
) -> List[bool]:
    """Visibility of every question by flat position — the single source of truth for the
    conditional-display rule on the backend.

    A question with no `display_condition` is always visible. Otherwise it is visible only
    when its trigger question is itself visible AND the trigger's submitted answer selects
    one of the required `option_indices`. Visibility is transitive: a dependent of a hidden
    trigger is hidden. Triggers always precede their dependents (validated at creation), so
    a single forward pass that reads earlier positions' visibility resolves whole chains. A
    condition whose `source_position` is missing, out of range, or points at/after the
    dependent itself can never be satisfied, so the question stays hidden.
    """
    visibility: List[bool] = []
    for question in flat_questions:
        condition = question.get("display_condition")
        if not condition:
            visibility.append(True)
            continue
        source_position = condition.get("source_position")
        option_indices = condition.get("option_indices") or []
        if (
            not isinstance(source_position, int)
            or source_position < 0
            or source_position >= len(visibility)
            or not visibility[source_position]
        ):
            visibility.append(False)
            continue
        answer = (
            session_answers[source_position].get("answer")
            if source_position < len(session_answers)
            else None
        )
        trigger_type = flat_questions[source_position].get("type")
        selected = set(answer_option_indices(answer, trigger_type))
        visibility.append(bool(selected.intersection(option_indices)))
    return visibility
