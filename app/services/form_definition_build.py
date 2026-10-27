"""Build a form quiz from a form-builder definition (pure logic, no DB).

A definition (models.FormDefinitionContent) keeps text per language and refers to questions
and options by stable ids. The quiz the student takes is positional: questions are addressed
by flat position across all sets and conditions by {source_position, option_indices}. This
module is the ONE place that materialises a definition into that runtime shape, so quiz
creation (POST /quiz/from-form-definition) and regenerate produce identical quizzes.

The output mirrors what Google-Sheet forms produce today (sessionCreator GsheetInterface):
ungraded questions, 500-char limits on free text and on the "Other" box, matrix-rating scale
as options + rows as matrix_rows, and bilingual text stacked as "English\\nHindi".
"""

from typing import Dict, List, Optional

from schemas import QuestionType, QuizSource, QuizType, TestFormat

# Fixed label of the last option of a single-choice-other question (same as sheets).
OTHER_OPTION_TEXT = "Other"
# Character limits, matching the sheet flow.
OTHER_MAX_CHARS = 500
SUBJECTIVE_MAX_CHARS = 500
# Forms are ungraded; an explicit zero scheme keeps scoring from falling back to a default.
FORM_MARKING_SCHEME = {"correct": 0, "wrong": 0, "skipped": 0}

_CHOICE_TYPES = (
    QuestionType.single_choice.value,
    QuestionType.single_choice_other.value,
    QuestionType.multi_choice.value,
)


class FormBuildError(ValueError):
    """The definition can't be turned into a quiz; `errors` lists every problem."""

    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _questions(definition: dict) -> List[dict]:
    return [
        question
        for section in definition.get("sections") or []
        for question in section.get("questions") or []
    ]


def _label(question: dict, position: int) -> str:
    text = ((question.get("text") or {}).get("en") or "").strip()
    return (
        f'question {position + 1} ("{text[:40]}")'
        if text
        else f"question {position + 1}"
    )


def structure_errors(definition: dict) -> List[str]:
    """Problems that make a definition inconsistent; checked on every save. A draft may still
    be incomplete (empty text, a section without questions) — see `completeness_errors`.
    """
    errors = []
    questions = _questions(definition)
    positions: Dict[str, int] = {}
    for position, question in enumerate(questions):
        if question["id"] in positions:
            errors.append(f"duplicate question id {question['id']!r}")
        positions[question["id"]] = position
    section_ids = [section["id"] for section in definition.get("sections") or []]
    if len(section_ids) != len(set(section_ids)):
        errors.append("duplicate section ids")

    for position, question in enumerate(questions):
        where = _label(question, position)
        option_ids = [option["id"] for option in question.get("options") or []]
        if len(option_ids) != len(set(option_ids)):
            errors.append(f"{where}: duplicate option ids")
        if question["type"] == QuestionType.single_choice_other.value:
            options = question.get("options") or []
            last = ((options[-1]["text"].get("en") if options else "") or "").strip()
            if last.lower() != OTHER_OPTION_TEXT.lower():
                errors.append(f'{where}: the last option must be "{OTHER_OPTION_TEXT}"')

        show_if = question.get("show_if")
        if not show_if:
            continue
        source = positions.get(show_if["question_id"])
        if source is None or source >= position:
            errors.append(f"{where}: its trigger must be an earlier question")
            continue
        trigger = questions[source]
        if trigger["type"] not in _CHOICE_TYPES:
            errors.append(f"{where}: its trigger must be a choice question")
            continue
        trigger_option_ids = {option["id"] for option in trigger.get("options") or []}
        if not set(show_if.get("option_ids") or []) <= trigger_option_ids:
            errors.append(f"{where}: it refers to an option its trigger doesn't have")
    return errors


def completeness_errors(definition: dict) -> List[str]:
    """What still has to be filled in before a session can use the form."""
    errors = []
    if not (definition.get("title") or "").strip():
        errors.append("the form has no title")
    questions = _questions(definition)
    if not questions:
        errors.append("the form has no questions")
    for index, section in enumerate(definition.get("sections") or []):
        if not section.get("questions"):
            errors.append(f"section {index + 1} has no questions")
    for position, question in enumerate(questions):
        where = _label(question, position)
        if not ((question.get("text") or {}).get("en") or "").strip():
            errors.append(f"{where}: missing English text")
        show_if = question.get("show_if")
        if show_if and not show_if.get("option_ids"):
            # a follow-up just added in the builder: the author still has to pick the
            # option(s) that reveal it
            errors.append(f"{where}: no trigger option chosen for its condition")
        if question["type"] in _CHOICE_TYPES:
            options = question.get("options") or []
            if len(options) < 2:
                errors.append(f"{where}: needs at least two options")
            if any(not (option["text"].get("en") or "").strip() for option in options):
                errors.append(f"{where}: an option has no English text")
        if question["type"] == QuestionType.matrix_rating.value:
            if not question.get("rows") or any(
                not (row["text"].get("en") or "").strip() for row in question["rows"]
            ):
                errors.append(f"{where}: every rating row needs English text")
            if not _split_scale(question.get("scale") or {}, None):
                errors.append(f"{where}: the rating scale is empty")
    return errors


def _text(text: Optional[dict], lang_code: Optional[str]) -> str:
    """English, or English and the chosen language stacked on two lines (decision D15)."""
    text = text or {}
    english = (text.get("en") or "").strip()
    other = (text.get(lang_code) or "").strip() if lang_code else ""
    return f"{english}\n{other}" if other else english


def _split_scale(scale: dict, lang_code: Optional[str]) -> List[str]:
    """Comma-separated scale per language -> one label per point, stacked like _text."""

    def split(value: Optional[str]) -> List[str]:
        return [part.strip() for part in (value or "").split(",") if part.strip()]

    english = split(scale.get("en"))
    other = split(scale.get(lang_code)) if lang_code else []
    return [
        f"{label}\n{other[index]}" if index < len(other) else label
        for index, label in enumerate(english)
    ]


def build_quiz(definition: dict, definition_id: str, lang_code: Optional[str]) -> dict:
    """The quiz dict (input to models.Quiz) a session gets from this definition.

    `lang_code`: None = English only; "hi" = English + Hindi stacked. Raises FormBuildError
    when the definition is inconsistent or incomplete, or doesn't offer `lang_code`.
    """
    errors = structure_errors(definition) + completeness_errors(definition)
    if lang_code and lang_code not in (definition.get("languages") or []):
        errors.append(f"the form has no {lang_code!r} text")
    if errors:
        raise FormBuildError(errors)

    questions = _questions(definition)
    positions = {
        question["id"]: position for position, question in enumerate(questions)
    }

    def build_question(question: dict) -> dict:
        built = {
            "text": _text(question["text"], lang_code),
            "type": question["type"],
            "options": [],
            "graded": False,
            "correct_answer": None,
            "required": question.get("required", True),
            "marking_scheme": FORM_MARKING_SCHEME,
            "source": QuizSource.form_builder.value,
            # the definition's question id: stable across sessions (BigQuery joins on it)
            "source_id": question["id"],
        }
        if question["type"] in _CHOICE_TYPES:
            built["options"] = [
                {"text": _text(option["text"], lang_code)}
                for option in question["options"]
            ]
        if question["type"] == QuestionType.single_choice_other.value:
            built["max_char_limit"] = OTHER_MAX_CHARS
        if question["type"] == QuestionType.subjective.value:
            built["max_char_limit"] = SUBJECTIVE_MAX_CHARS
        if question["type"] == QuestionType.matrix_rating.value:
            built["options"] = [
                {"text": label} for label in _split_scale(question["scale"], lang_code)
            ]
            built["matrix_rows"] = [
                _text(row["text"], lang_code) for row in question["rows"]
            ]
        show_if = question.get("show_if")
        if show_if:
            trigger = questions[positions[show_if["question_id"]]]
            trigger_option_ids = [option["id"] for option in trigger["options"]]
            built["display_condition"] = {
                "source_position": positions[show_if["question_id"]],
                "option_indices": sorted(
                    trigger_option_ids.index(option_id)
                    for option_id in show_if["option_ids"]
                ),
            }
        return built

    question_sets = []
    for section in definition["sections"]:
        built_questions = [
            build_question(question) for question in section["questions"]
        ]
        question_sets.append(
            {
                "title": section.get("title") or "",
                "max_questions_allowed_to_attempt": len(built_questions),
                "marking_scheme": FORM_MARKING_SCHEME,
                "questions": built_questions,
            }
        )

    return {
        "title": definition["title"].strip(),
        "question_sets": question_sets,
        "max_marks": 0,
        "num_graded_questions": 0,
        "shuffle": False,
        # the runtime only honours per-question `required` when this is on
        "require_all_questions": any(q.get("required", True) for q in questions),
        "metadata": {
            "quiz_type": QuizType.form.value,
            "test_format": TestFormat.questionnaire.value,
            "source": QuizSource.form_builder.value,
            "source_id": definition_id,
            "lang_code": lang_code,
        },
    }


def summary_counts(definition: dict) -> Dict[str, int]:
    """Counts stored on the definition for the Forms list / details panel."""
    questions = _questions(definition)
    return {
        "question_count": len(questions),
        "conditional_count": sum(1 for q in questions if q.get("show_if")),
    }
