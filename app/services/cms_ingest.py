"""
CMS -> quiz mapping for the LMS session-creation flow.

The new CMS (nex-gen-cms) owns test content and exposes an assembled-test JSON at
GET /api/service/test?id=&curriculum_id=&grade_id= (bearer-auth). This module fetches
that JSON and maps it into the quiz format this service stores (quiz.quizzes /
quiz.questions), so Gurukul renders a CMS-sourced test like any other quiz.

Contract (locked with the CMS owner — see task lms-cms-tests):
- Assembled shape: {"test": Test, "problems": [Problem, ...]}. `test.type_params` carries
  the structure (subjects -> sections -> problem refs) and marks at four levels
  (test / subject / section / problem). `problems` is a flat list of fully-resolved
  problems (text, options, answer, paragraph) joined to their refs by id.
- Answers are 1-based option numbers; the quiz engine wants 0-based indices.
- Marks cascade problem -> section -> subject -> test; the lowest level that sets marks
  wins. `pos_marks[0]` -> correct, `neg_marks[0]` -> wrong (as a negative).
- Multi-choice partial marking uses the standard JEE-Adv preset (+1 per correct option
  selected, no wrong selected; full marks handled by exact-match in the grader). A single
  uniform partial list works per set regardless of each question's correct-count, because
  the grader awards partial only for strict subsets keyed on num_correct_selected.
- numerical_answer: single value -> scalar; 2-entry [low, high] range is not gradeable by
  the engine today (scalar only), so we store the low bound and surface a warning.
"""

from typing import Any, Dict, List, Optional, Tuple

import requests

from schemas import QuizSource
from settings import Settings

settings = Settings()

# CMS problem subtype -> quiz-engine question type. numerical_answer resolves to
# numerical-integer/float at map time based on the answer value.
CHOICE_TYPE_MAP = {
    "mcq_single_answer": "single-choice",
    "mcq_multiple_answer": "multi-choice",
    "matrix_match": "single-choice",  # single-answer; table baked into the question HTML
    "comprehension": "single-choice",  # 1:1, paragraph self-carried on the problem
}


class CmsIngestError(Exception):
    """Raised when the CMS assembled-test JSON cannot be fetched or is unusable."""


def fetch_assembled_test(
    test_id: int, curriculum_id: int, grade_id: int
) -> Dict[str, Any]:
    """Fetch the assembled-test JSON from the new CMS. Raises CmsIngestError on failure."""
    if not settings.cms_service_endpoint or not settings.cms_service_token:
        raise CmsIngestError(
            "CMS_SERVICE_ENDPOINT / CMS_SERVICE_TOKEN are not configured"
        )

    url = settings.cms_service_endpoint.rstrip("/") + "/api/service/test"
    try:
        response = requests.get(
            url,
            params={
                "id": test_id,
                "curriculum_id": curriculum_id,
                "grade_id": grade_id,
            },
            headers={"Authorization": f"Bearer {settings.cms_service_token}"},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise CmsIngestError(f"error calling CMS: {exc}") from exc

    if response.status_code != 200:
        raise CmsIngestError(
            f"CMS returned {response.status_code} for test {test_id}: {response.text[:200]}"
        )
    return response.json()


def _pos_marks(level: Optional[Dict[str, Any]]) -> List[int]:
    return (level or {}).get("pos_marks") or []


def _neg_marks(level: Optional[Dict[str, Any]]) -> List[int]:
    return (level or {}).get("neg_marks") or []


def _cascade_marks(
    ref: Optional[Dict[str, Any]],
    section: Optional[Dict[str, Any]],
    subject: Optional[Dict[str, Any]],
    test_type_params: Optional[Dict[str, Any]],
) -> Tuple[float, float]:
    """Resolve (correct, wrong) marks by cascading problem -> section -> subject -> test;
    the lowest (most specific) level that defines pos_marks wins. Returns (correct, wrong)
    where wrong is already negated. Defaults to (1, 0) if nothing is set."""
    for level in (ref, section, subject, test_type_params):
        pos = _pos_marks(level)
        if pos:
            neg = _neg_marks(level)
            return float(pos[0]), -float(neg[0]) if neg else 0.0
    return 1.0, 0.0


def _inline_paragraph(problem: Dict[str, Any], text: str) -> str:
    """Comprehension problems self-carry their passage in `paragraph`; inline it."""
    paragraph = problem.get("paragraph")
    if paragraph and paragraph.get("body"):
        return f"{paragraph['body']}{text}"
    return text


def _solutions(meta_data: Dict[str, Any]) -> List[str]:
    out = []
    for solution in meta_data.get("solutions") or []:
        value = solution.get("value") if isinstance(solution, dict) else solution
        if value:
            out.append(str(value))
    return out


def _problem_metadata(problem: Dict[str, Any], subject_name: str) -> Dict[str, Any]:
    return {
        # subject_name is the plain, resolved subject name from the test structure;
        # the problem's own `Subject.name` is a multilingual list, so we don't use it.
        "subject": subject_name or None,
        "grade": str(problem["grade_id"]) if problem.get("grade_id") else None,
        "chapter_id": str(problem["chapter_id"]) if problem.get("chapter_id") else None,
        "topic_id": str(problem["topic_id"]) if problem.get("topic_id") else None,
        "difficulty": problem.get("difficulty_level") or None,
    }


def _map_problem(
    problem: Dict[str, Any], subject_name: str = ""
) -> Tuple[Dict[str, Any], List[str]]:
    """Map one resolved CMS problem to a quiz Question dict (without marking_scheme,
    which is set at the set level by the caller). Returns (question, warnings)."""
    warnings: List[str] = []
    meta = problem.get("meta_data") or {}
    subtype = problem.get("subtype") or ""
    answers = meta.get("answer") or []
    problem_id = problem.get("id")

    question: Dict[str, Any] = {
        "text": _inline_paragraph(problem, meta.get("text") or ""),
        "options": [],
        "correct_answer": None,
        "graded": True,
        "solution": _solutions(meta),
        "metadata": _problem_metadata(problem, subject_name),
        "source": QuizSource.nex_gen_cms.value,
        "source_id": str(problem_id),
    }

    # numerical_answer and integer_type are both free-numeric-entry (no options); the CMS
    # stores the answer as a single value (integer_type is always an integer). Map both to
    # numerical-integer/float from the answer value.
    if subtype in ("numerical_answer", "integer_type"):
        if not answers:
            warnings.append(
                f"problem {problem_id}: numerical with no answer -> ungraded"
            )
            question["type"] = "numerical-integer"
            question["graded"] = False
            return question, warnings
        if len(answers) >= 2 and str(answers[0]) != str(answers[1]):
            warnings.append(
                f"problem {problem_id}: numerical range [{answers[0]}, {answers[1]}] "
                "is not gradeable as a range by the engine; stored the low bound only"
            )
        value = str(answers[0])
        if "." in value:
            question["type"] = "numerical-float"
            question["correct_answer"] = float(value)
        else:
            question["type"] = "numerical-integer"
            question["correct_answer"] = int(value)
        return question, warnings

    question_type = CHOICE_TYPE_MAP.get(subtype)
    if question_type is None:
        warnings.append(
            f"problem {problem_id}: unknown subtype '{subtype}', defaulting to single-choice"
        )
        question_type = "single-choice"
    question["type"] = question_type
    question["options"] = [
        {"text": str(option), "image": None} for option in (meta.get("options") or [])
    ]

    if not answers:
        warnings.append(f"problem {problem_id}: no answer -> ungraded")
        question["graded"] = False
    else:
        # CMS answers are 1-based option numbers; the engine wants 0-based indices.
        question["correct_answer"] = [int(answer) - 1 for answer in answers]

    return question, warnings


def _partial_scheme(max_options: int) -> List[Dict[str, Any]]:
    """Standard JEE-Adv multi-choice partial ladder: +k for k correct options selected
    (no wrong selected). Uniform across the set — the grader only awards partial for
    strict subsets keyed on num_correct_selected, and full marks come from exact-match.
    """
    return [
        {"conditions": [{"num_correct_selected": k}], "marks": k}
        for k in range(1, max(max_options, 1))
    ]


def _test_name(test: Dict[str, Any]) -> str:
    for name in test.get("name") or []:
        if name.get("lang_code") == "en":
            return name.get("resource") or ""
    names = test.get("name") or []
    return names[0].get("resource", "") if names else ""


def map_cms_test_to_quiz(
    assembled: Dict[str, Any], quiz_type: str = "assessment"
) -> Tuple[Dict[str, Any], List[str]]:
    """Map an assembled CMS test into a quiz dict ready for insertion. Returns
    (quiz, warnings). One question set per CMS section; per-set marking resolved via the
    marks cascade, with the JEE-Adv partial ladder on sets containing multi-choice."""
    test = assembled.get("test") or {}
    problems_by_id = {p.get("id"): p for p in (assembled.get("problems") or [])}
    type_params = test.get("type_params") or {}

    warnings: List[str] = []
    question_sets: List[Dict[str, Any]] = []
    num_graded_questions = 0
    max_marks = 0.0

    for subject in type_params.get("subjects") or []:
        subject_name = subject.get("Name") or ""
        for section_index, section in enumerate(subject.get("sections") or []):
            compulsory = (section.get("compulsory") or {}).get("problems") or []
            optional = section.get("optional") or {}
            optional_problems = optional.get("problems") or []
            refs = list(compulsory) + list(optional_problems)

            questions: List[Dict[str, Any]] = []
            has_multi_choice = False
            max_options = 0
            for ref in refs:
                problem = problems_by_id.get(ref.get("id"))
                if problem is None:
                    warnings.append(
                        f"problem {ref.get('id')} referenced by test but not resolved"
                    )
                    continue
                question, question_warnings = _map_problem(problem, subject_name)
                warnings.extend(question_warnings)
                if question["type"] == "multi-choice":
                    has_multi_choice = True
                    max_options = max(max_options, len(question.get("options") or []))
                questions.append(question)
                if question.get("graded", True):
                    num_graded_questions += 1

            if not questions:
                continue

            if optional_problems:
                warnings.append(
                    f"section '{section.get('name') or section_index}' has optional "
                    "problems; mandatory_count limits are not applied in v1 (all included)"
                )

            correct, wrong = _cascade_marks(None, section, subject, type_params)
            marking_scheme: Dict[str, Any] = {
                "correct": correct,
                "wrong": wrong,
                "skipped": 0.0,
                "partial": _partial_scheme(max_options) if has_multi_choice else None,
            }
            # Apply the set marking scheme to each question too (legacy parity: the grader
            # reads the set-level scheme, but single-page/other paths read question-level).
            for question in questions:
                question["marking_scheme"] = marking_scheme

            section_name = section.get("name")
            if subject_name and section_name:
                title = f"{subject_name} - {section_name}"
            else:
                title = subject_name or section_name or f"Section {section_index + 1}"

            question_sets.append(
                {
                    "title": title,
                    "questions": questions,
                    "max_questions_allowed_to_attempt": len(questions),
                    "marking_scheme": marking_scheme,
                }
            )
            max_marks += correct * len(questions)

    if not question_sets:
        raise CmsIngestError(
            f"test {test.get('id')} produced no question sets (no resolvable problems)"
        )

    first_subject = None
    for subject in type_params.get("subjects") or []:
        if subject.get("Name"):
            first_subject = subject.get("Name")
            break

    quiz = {
        "title": _test_name(test),
        "question_sets": question_sets,
        "max_marks": int(round(max_marks)),
        "num_graded_questions": num_graded_questions,
        "shuffle": False,
        "metadata": {
            "quiz_type": quiz_type,
            "test_format": test.get("subtype"),
            "grade": None,
            "subject": first_subject,
            "source": QuizSource.nex_gen_cms.value,
            "source_id": str(test.get("id")),
        },
    }
    return quiz, warnings
