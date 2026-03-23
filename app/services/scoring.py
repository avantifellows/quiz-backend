from typing import Any, Dict, Optional


NUMERICAL_FLOAT_TOLERANCE = 0.05

DEFAULT_MARKING_SCHEME_ASSESSMENT = {
    "correct": 4.0,
    "wrong": -1.0,
    "skipped": 0.0,
    "partial": None,
}
DEFAULT_MARKING_SCHEME_HOMEWORK = {
    "correct": 1.0,
    "wrong": 0.0,
    "skipped": 0.0,
    "partial": None,
}


def _get_quiz_type(quiz: Dict[str, Any]) -> Optional[str]:
    metadata = quiz.get("metadata") or {}
    return metadata.get("quiz_type")


def _get_marking_scheme(question_set: Dict[str, Any], quiz_type: Optional[str]):
    marking_scheme = question_set.get("marking_scheme")
    if marking_scheme is None:
        questions = question_set.get("questions") or []
        if questions:
            marking_scheme = questions[0].get("marking_scheme")
    if marking_scheme is None:
        if quiz_type in ["assessment", "omr-assessment"]:
            marking_scheme = DEFAULT_MARKING_SCHEME_ASSESSMENT.copy()
        else:
            marking_scheme = DEFAULT_MARKING_SCHEME_HOMEWORK.copy()
    if "partial" not in marking_scheme:
        marking_scheme = {**marking_scheme, "partial": None}
    return marking_scheme


def _answers_equal(user_answer: Any, correct_answer: Any) -> bool:
    if isinstance(user_answer, list) and isinstance(correct_answer, list):
        return sorted(user_answer) == sorted(correct_answer)
    return user_answer == correct_answer


def _is_subset(user_answer: Any, correct_answer: Any) -> bool:
    if not isinstance(user_answer, list) or not isinstance(correct_answer, list):
        return False
    return all(option in correct_answer for option in user_answer)


def _evaluate_answer(
    question_details: Dict[str, Any],
    user_answer: Any,
    does_partial_marking_exist: bool,
) -> Dict[str, Any]:
    result = {
        "valid": False,
        "answered": False,
        "is_correct": None,
        "is_partially_correct": False,
    }

    if question_details.get("graded", True):
        result["valid"] = True
        question_type = question_details.get("type")
        correct_answer = question_details.get("correct_answer")

        # invalid format: if a number is submitted for choice/matrix-match, mark wrong
        if isinstance(user_answer, (int, float)) and question_type in [
            "single-choice",
            "multi-choice",
            "matrix-match",
        ]:
            result["answered"] = True
            result["is_correct"] = False
            return result

        if user_answer is not None and not isinstance(user_answer, (int, float)):
            result["answered"] = True
            if question_type == "single-choice":
                result["is_correct"] = _answers_equal(user_answer, correct_answer)
            elif question_type == "multi-choice":
                if _answers_equal(user_answer, correct_answer):
                    result["is_correct"] = True
                elif (
                    does_partial_marking_exist
                    and isinstance(user_answer, list)
                    and isinstance(correct_answer, list)
                    and len(user_answer) > 0
                    and _is_subset(user_answer, correct_answer)
                ):
                    result["is_correct"] = False
                    result["is_partially_correct"] = True
                else:
                    result["is_correct"] = False
            elif question_type == "matrix-match":
                if _answers_equal(user_answer, correct_answer):
                    result["is_correct"] = True
                elif (
                    does_partial_marking_exist
                    and isinstance(user_answer, list)
                    and isinstance(correct_answer, list)
                    and len(user_answer) > 0
                    and _is_subset(user_answer, correct_answer)
                ):
                    result["is_correct"] = False
                    result["is_partially_correct"] = True
                else:
                    result["is_correct"] = False
            elif question_type == "matrix-rating":
                result["is_correct"] = _answers_equal(user_answer, correct_answer)
            elif question_type == "matrix-numerical":
                result["is_correct"] = _answers_equal(user_answer, correct_answer)
            elif question_type == "matrix-subjective":
                # NOTE: Matching legacy FE/ETL behavior: any non-empty response counts as correct.
                if isinstance(user_answer, dict):
                    has_response = any(
                        isinstance(val, str) and val.strip() != ""
                        for val in user_answer.values()
                    )
                    result["is_correct"] = has_response
                else:
                    result["is_correct"] = False
            elif question_type == "subjective":
                # NOTE: Matching legacy FE/ETL behavior: any non-empty response counts as correct.
                if isinstance(user_answer, str) and user_answer.strip() != "":
                    result["is_correct"] = True
                else:
                    result["is_correct"] = False
            else:
                result["is_correct"] = False
            return result

        if question_type in ["numerical-integer", "numerical-float"] and isinstance(
            user_answer, (int, float)
        ):
            result["answered"] = True
            if (
                question_type == "numerical-float"
                and isinstance(correct_answer, (int, float))
                and abs(user_answer - correct_answer)
                < NUMERICAL_FLOAT_TOLERANCE  # tolerance for float comparison
            ):
                result["is_correct"] = True
            elif (
                question_type == "numerical-integer"
                and correct_answer is not None
                and user_answer == correct_answer
            ):
                result["is_correct"] = True
            else:
                result["is_correct"] = False
            return result

        return result

    if user_answer is not None:
        result["answered"] = True
    return result


def _is_form_answered(user_answer: Any) -> bool:
    return user_answer is not None and (
        (isinstance(user_answer, str) and user_answer.strip() != "")
        or (isinstance(user_answer, list) and len(user_answer) > 0)
        or isinstance(user_answer, (int, float))
        or (isinstance(user_answer, dict) and len(user_answer) > 0)
    )


def _compute_partial_marks(marking_scheme: Dict[str, Any], user_answer: Any) -> float:
    partial_rules = marking_scheme.get("partial")
    if not partial_rules or not isinstance(user_answer, list):
        return 0.0
    for partial_mark_rule in partial_rules:
        for condition in partial_mark_rule.get("conditions", []):
            if condition.get("num_correct_selected") == len(user_answer):
                return float(partial_mark_rule.get("marks", 0))
    return 0.0


def compute_session_metrics(
    session: Dict[str, Any], quiz: Dict[str, Any]
) -> Dict[str, Any]:
    quiz_type = _get_quiz_type(quiz)
    question_sets = quiz.get("question_sets") or []
    session_answers = session.get("session_answers") or []

    qset_metrics = []
    total_answered = 0
    total_skipped = 0
    total_correct = 0
    total_wrong = 0
    total_partially_correct = 0
    total_marked_for_review = 0
    total_marks = 0.0

    session_answer_index = 0
    for question_set in question_sets:
        questions = question_set.get("questions") or []
        qset_title = question_set.get("title")
        if qset_title is None:
            qset_title = ""
        qset_id = question_set.get("_id") or question_set.get("id")
        qset_id = str(qset_id) if qset_id is not None else ""
        marking_scheme = _get_marking_scheme(question_set, quiz_type)

        qset_num_answered = 0
        qset_num_correct = 0
        qset_num_wrong = 0
        qset_num_partially_correct = 0
        qset_num_marked_for_review = 0
        qset_num_ungraded = 0
        qset_partial_marks = 0.0

        for question in questions:
            if session_answer_index >= len(session_answers):
                break
            session_answer = session_answers[session_answer_index]
            session_answer_index += 1

            if session_answer.get("marked_for_review"):
                qset_num_marked_for_review += 1

            if quiz_type == "form":
                if _is_form_answered(session_answer.get("answer")):
                    qset_num_answered += 1
                continue

            if question.get("force_correct", False):
                qset_num_answered += 1
                qset_num_correct += 1
                continue

            if not question.get("graded", True):
                qset_num_ungraded += 1
                continue

            answer_eval = _evaluate_answer(
                question,
                session_answer.get("answer"),
                marking_scheme.get("partial") is not None,
            )

            if not answer_eval.get("valid"):
                continue

            if answer_eval.get("answered"):
                qset_num_answered += 1
                if answer_eval.get("is_correct"):
                    qset_num_correct += 1
                elif answer_eval.get("is_partially_correct"):
                    qset_num_partially_correct += 1
                    qset_partial_marks += _compute_partial_marks(
                        marking_scheme, session_answer.get("answer")
                    )
                else:
                    qset_num_wrong += 1

        if quiz_type == "form":
            max_questions_allowed = len(questions)
            qset_num_skipped = max_questions_allowed - qset_num_answered
            qset_marks_scored = 0.0
        else:
            max_questions_allowed = question_set.get("max_questions_allowed_to_attempt")
            if max_questions_allowed is None:
                max_questions_allowed = len(questions)
            max_questions_allowed = max(0, max_questions_allowed - qset_num_ungraded)
            qset_num_skipped = max(0, max_questions_allowed - qset_num_answered)
            qset_marks_scored = (
                float(marking_scheme.get("correct", 0)) * qset_num_correct
                + float(marking_scheme.get("wrong", 0)) * qset_num_wrong
                + float(marking_scheme.get("skipped", 0)) * qset_num_skipped
                + qset_partial_marks
            )

        attempt_rate = (
            qset_num_answered / max_questions_allowed
            if max_questions_allowed > 0
            else 0
        )
        accuracy_rate = (
            (qset_num_correct + 0.5 * qset_num_partially_correct) / qset_num_answered
            if qset_num_answered > 0
            else 0
        )

        qset_metrics.append(
            {
                "name": qset_title,
                "qset_id": qset_id,
                "marks_scored": round(qset_marks_scored, 2),
                "num_answered": qset_num_answered,
                "num_skipped": qset_num_skipped,
                "num_correct": qset_num_correct,
                "num_wrong": qset_num_wrong,
                "num_partially_correct": qset_num_partially_correct,
                "num_marked_for_review": qset_num_marked_for_review,
                "attempt_rate": round(attempt_rate, 4),
                "accuracy_rate": round(accuracy_rate, 4),
            }
        )

        total_answered += qset_num_answered
        total_skipped += qset_num_skipped
        total_correct += qset_num_correct
        total_wrong += qset_num_wrong
        total_partially_correct += qset_num_partially_correct
        total_marked_for_review += qset_num_marked_for_review
        total_marks += qset_marks_scored

    return {
        "qset_metrics": qset_metrics,
        "total_answered": total_answered,
        "total_skipped": total_skipped,
        "total_correct": total_correct,
        "total_wrong": total_wrong,
        "total_partially_correct": total_partially_correct,
        "total_marked_for_review": total_marked_for_review,
        "total_marks": round(total_marks, 2),
    }
