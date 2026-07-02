"""
CMS -> quiz mapping for the LMS session-creation flow.

The new CMS (nex-gen-cms) owns test content and exposes an assembled-test JSON at
GET /api/service/test?id=&curriculum_id=&grade_id= (bearer-auth). This module fetches
that JSON and maps it into the quiz format this service stores (quiz.quizzes /
quiz.questions), so Gurukul renders a CMS-sourced test like any other quiz.

This mapper replicates the behaviour of the legacy sessionCreator Lambda
(etl-data-flow flows/sessionCreator/QuizInterface.py) that it replaces, with two
deliberate, data-driven divergences the new CMS makes safe (see below).

Contract (locked with the CMS owner — see task lms-cms-tests):
- Assembled shape: {"test": Test, "problems": [Problem, ...]}. `test.type_params` carries
  the structure (subjects -> sections -> compulsory/optional problem refs) and marks at
  four levels (test / subject / section / problem). `problems` is a flat list of
  fully-resolved problems (text, options, answer, paragraph) joined to their refs by id.
- Answers are 1-based option numbers; the quiz engine wants 0-based indices.
- Marks cascade problem-ref -> section -> subject -> test; the lowest level that sets
  marks wins. `pos_marks[0]` -> correct, `neg_marks[0]` -> wrong (as a negative).

Replication of sessionCreator (QuizInterface.py):
- HOMOGENEOUS SETS: a Mongo question set must hold a single question type, because the
  grader reads marking at the *set* level (scoring.py) and applies one scheme + one
  partial flag to every question in the set. We split a section into contiguous
  same-type sub-sets (legacy `split_using_question_type`). New-CMS sections are already
  authored per-type, so this is a safety net, but it enforces the invariant.
- SET MARKING = first question's scheme (legacy parity), stamped onto every question.
- MULTI-CHOICE PARTIAL: the standard JEE-Adv ladder (+k for k correct options selected,
  no wrong). The CMS stores only a single achievable mark per problem (e.g. [4]), so it
  carries no partial signal — the preset is the only source, exactly as legacy did.
- MAX MARKS: correct * max_questions_allowed_to_attempt (honours optional attempt limits).
- DURATION -> time_limit {min:0, max:minutes*60}; None if the test has no duration.

Deliberate divergences from legacy (new-CMS data makes these strictly better):
- OPTIONAL LIMITS come from `section.optional.mandatory_count` in the data, not from
  legacy's hardcoded JEE/NEET/CUET presets (which reverse-engineered exactly this from
  the test name because the old CMS didn't carry it).
- NUMERICAL RANGE [low, high] stores the midpoint (low+high)/2 (the engine grades numerics
  with a fixed tolerance, so the midpoint is the least-biased point answer), not the low
  bound. True range grading is a later engine change.

Unknown problem subtypes fail the ingestion (like legacy's ValueError) rather than being
silently mapped to single-choice — a wrong question type in a live quiz is worse than a
loud failure at create time.
"""

from typing import Any, Dict, List, Optional, Tuple

import requests

from schemas import QuizSource
from settings import Settings

settings = Settings()

# CMS problem subtype -> quiz-engine question type. numerical_answer / integer_type
# resolve to numerical-integer/float at map time based on the answer value.
CHOICE_TYPE_MAP = {
    "mcq_single_answer": "single-choice",
    "mcq_multiple_answer": "multi-choice",
    "matrix_match": "single-choice",  # single-answer; table baked into the question HTML
    "comprehension": "single-choice",  # 1:1, paragraph self-carried on the problem
}
NUMERIC_SUBTYPES = ("numerical_answer", "integer_type")

# Instruction blurbs shown at the top of a question set, keyed on the set's question type
# (ported from QuizInterface.QUESTION_SET_TYPE_INSTRUCTION_MAPPING).
_SET_TYPE_INSTRUCTION = {
    "single-choice": "MCQs with SINGLE correct option",
    "multi-choice": "MCQs with ONE or MORE correct options",
    "numerical-integer": "Non-Negative Integer answer",
    "numerical-float": "Numerical Answer (rounded off to TWO decimal places)",
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
    """Resolve (correct, wrong) marks by cascading problem-ref -> section -> subject ->
    test; the lowest (most specific) level that defines pos_marks wins. Returns
    (correct, wrong) where wrong is already negated. Defaults to (1, 0) if nothing is set.
    """
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
    problem: Dict[str, Any],
    ref: Optional[Dict[str, Any]],
    section: Optional[Dict[str, Any]],
    subject: Optional[Dict[str, Any]],
    test_type_params: Optional[Dict[str, Any]],
    subject_name: str = "",
) -> Tuple[Dict[str, Any], List[str]]:
    """Map one resolved CMS problem to a quiz Question dict. The question carries its own
    base marking_scheme (correct/wrong from the marks cascade; no partial — that is set at
    the set level once the set's type is known). Returns (question, warnings)."""
    warnings: List[str] = []
    meta = problem.get("meta_data") or {}
    subtype = problem.get("subtype") or ""
    answers = meta.get("answer") or []
    problem_id = problem.get("id")

    correct, wrong = _cascade_marks(ref, section, subject, test_type_params)

    question: Dict[str, Any] = {
        "text": _inline_paragraph(problem, meta.get("text") or ""),
        "options": [],
        "correct_answer": None,
        "graded": True,
        "solution": _solutions(meta),
        "metadata": _problem_metadata(problem, subject_name),
        "source": QuizSource.nex_gen_cms.value,
        "source_id": str(problem_id),
        "marking_scheme": {
            "correct": correct,
            "wrong": wrong,
            "skipped": 0.0,
            "partial": None,
        },
    }

    # numerical_answer and integer_type are both free-numeric-entry (no options); the CMS
    # stores the answer as a single value or a [low, high] range. Map both to
    # numerical-integer/float from the answer value.
    if subtype in NUMERIC_SUBTYPES:
        if not answers:
            warnings.append(
                f"problem {problem_id}: numerical with no answer -> ungraded"
            )
            question["type"] = "numerical-integer"
            question["graded"] = False
            return question, warnings
        value = _numerical_answer(answers, problem_id, warnings)
        if isinstance(value, float):
            question["type"] = "numerical-float"
        else:
            question["type"] = "numerical-integer"
        question["correct_answer"] = value
        return question, warnings

    question_type = CHOICE_TYPE_MAP.get(subtype)
    if question_type is None:
        # Fail loud, like legacy's ValueError: a silently mis-typed question in a live
        # quiz (e.g. a matrix question flattened to single-choice) is worse than a clear
        # failure at create time.
        raise CmsIngestError(
            f"problem {problem_id}: unsupported subtype '{subtype}' — the mapper does not "
            "know how to render/grade this question type"
        )
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


def _numerical_answer(answers: List[Any], problem_id: Any, warnings: List[str]):
    """Resolve a numerical answer to a single graded value. A [low, high] range collapses
    to its midpoint (the engine grades numerics with a fixed tolerance, so the midpoint is
    the least-biased point answer); a single value is used as-is. Returns int or float.
    """
    if len(answers) >= 2 and str(answers[0]) != str(answers[1]):
        low, high = float(answers[0]), float(answers[1])
        midpoint = (low + high) / 2
        warnings.append(
            f"problem {problem_id}: numerical range [{answers[0]}, {answers[1]}] stored as "
            f"midpoint {midpoint} (engine grades a point +/- tolerance, not a range)"
        )
        return midpoint if midpoint != int(midpoint) else int(midpoint)
    value = str(answers[0])
    return float(value) if "." in value else int(value)


def _partial_scheme(max_options: int) -> List[Dict[str, Any]]:
    """Standard JEE-Adv multi-choice partial ladder: +k for k correct options selected
    (no wrong selected). Uniform across the set — the grader only awards partial for
    strict subsets keyed on num_correct_selected, and full marks come from exact-match.
    The CMS stores only a single achievable mark per problem, so it carries no partial
    signal; this preset is the sole source, matching legacy sessionCreator.
    """
    return [
        {"conditions": [{"num_correct_selected": k}], "marks": k}
        for k in range(1, max(max_options, 1))
    ]


def _finalize_marking(questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the set-level marking scheme (legacy: the first question's scheme, plus the
    partial ladder for a multi-choice set) and stamp it onto every question in the set,
    since the grader reads marking at the set level."""
    set_type = questions[0]["type"]
    base = questions[0]["marking_scheme"]
    partial = None
    if set_type == "multi-choice":
        max_options = max(len(q.get("options") or []) for q in questions)
        partial = _partial_scheme(max_options)
    scheme = {
        "correct": base["correct"],
        "wrong": base["wrong"],
        "skipped": 0.0,
        "partial": partial,
    }
    for question in questions:
        question["marking_scheme"] = scheme
    return scheme


def _description(set_type: str, scheme: Dict[str, Any]) -> str:
    """Marking-scheme instruction HTML shown at the top of a set (ported from
    QuizInterface.prepare_description: type blurb + a marking breakdown)."""
    instruction = f"<u>{_SET_TYPE_INSTRUCTION.get(set_type, 'Question Set')}</u>"
    correct = scheme["correct"]
    wrong = scheme["wrong"]
    skipped = scheme["skipped"]
    if scheme.get("partial"):
        rungs = " ".join(
            f"<span style='color: blue; font-weight: bold;'>+{rule['marks']}</span> "
            f"if {rule['conditions'][0]['num_correct_selected']} correct,"
            for rule in scheme["partial"]
        )
        instruction += (
            f"<br>ALL correct options are selected: "
            f"<span style='color: green; font-weight: bold;'>+{correct}</span>"
            f"<br>Partial marks awarded if no wrong option is selected and: {rungs}"
            f"<br>If ANY wrong option selected: "
            f"<span style='color: red; font-weight: bold;'>{wrong}</span>,    "
            f"Skipped: {skipped}"
        )
    else:
        instruction += (
            f"<br>Correct: <span style='color: green; font-weight: bold;'>+{correct}</span>, "
            f"Wrong: <span style='color: red; font-weight: bold;'>{wrong}</span>, "
            f"Skipped: {skipped}"
        )
    return instruction


def _split_by_type(questions: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Split a list of questions into contiguous runs of the same type (legacy
    `split_using_question_type`), so every resulting set is homogeneous."""
    runs: List[List[Dict[str, Any]]] = []
    for question in questions:
        if runs and runs[-1][0]["type"] == question["type"]:
            runs[-1].append(question)
        else:
            runs.append([question])
    return runs


def _set_title(subject_name: str, section_name: str, index: int) -> str:
    if subject_name and section_name:
        return f"{subject_name} - {section_name}"
    return subject_name or section_name or f"Section {index + 1}"


def _map_ref_list(
    refs: List[Dict[str, Any]],
    problems_by_id: Dict[Any, Dict[str, Any]],
    section: Dict[str, Any],
    subject: Dict[str, Any],
    type_params: Dict[str, Any],
    subject_name: str,
    warnings: List[str],
) -> List[Dict[str, Any]]:
    """Map a list of problem refs (compulsory or optional) to questions, in order."""
    questions: List[Dict[str, Any]] = []
    for ref in refs:
        problem = problems_by_id.get(ref.get("id"))
        if problem is None:
            warnings.append(
                f"problem {ref.get('id')} referenced by test but not resolved"
            )
            continue
        question, question_warnings = _map_problem(
            problem, ref, section, subject, type_params, subject_name
        )
        warnings.extend(question_warnings)
        questions.append(question)
    return questions


def _build_set(
    questions: List[Dict[str, Any]],
    title: str,
    max_questions_allowed_to_attempt: int,
) -> Dict[str, Any]:
    scheme = _finalize_marking(questions)
    return {
        "title": title,
        "questions": questions,
        "max_questions_allowed_to_attempt": max_questions_allowed_to_attempt,
        "marking_scheme": scheme,
        "description": _description(questions[0]["type"], scheme),
    }


def _test_name(test: Dict[str, Any]) -> str:
    for name in test.get("name") or []:
        if name.get("lang_code") == "en":
            return name.get("resource") or ""
    names = test.get("name") or []
    return names[0].get("resource", "") if names else ""


def _time_limit(type_params: Dict[str, Any]) -> Optional[Dict[str, int]]:
    """CMS stores the test duration as a string of minutes; convert to the engine's
    time_limit {min, max} in seconds (matches legacy CmsInterface). None if unset."""
    duration = str(type_params.get("duration") or "").strip()
    if not duration:
        return None
    try:
        minutes = int(float(duration))
    except ValueError:
        return None
    if minutes <= 0:
        return None
    return {"min": 0, "max": minutes * 60}


def map_cms_test_to_quiz(
    assembled: Dict[str, Any], quiz_type: str = "assessment"
) -> Tuple[Dict[str, Any], List[str]]:
    """Map an assembled CMS test into a quiz dict ready for insertion. Returns
    (quiz, warnings). Each CMS section becomes one or more homogeneous question sets
    (split by question type); optional problems become a set whose attempt limit is the
    section's mandatory_count."""
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
            section_name = section.get("name") or ""
            base_title = _set_title(subject_name, section_name, section_index)

            compulsory_refs = (section.get("compulsory") or {}).get("problems") or []
            optional = section.get("optional") or {}
            optional_refs = optional.get("problems") or []

            # Compulsory problems: split into homogeneous sets (safety net — CMS sections
            # are authored per-type), each fully attemptable.
            compulsory_qs = _map_ref_list(
                compulsory_refs,
                problems_by_id,
                section,
                subject,
                type_params,
                subject_name,
                warnings,
            )
            runs = _split_by_type(compulsory_qs)
            for run in runs:
                title = (
                    base_title if len(runs) == 1 else f"{base_title} ({run[0]['type']})"
                )
                question_sets.append(_build_set(run, title, len(run)))
                num_graded_questions += len(run)
                set_correct = run[0]["marking_scheme"]["correct"]
                max_marks += set_correct * len(run)

            # Optional problems: one set whose attempt limit is mandatory_count (data-driven,
            # replaces legacy's hardcoded JEE/NEET/CUET presets). Kept as a single set — the
            # attempt limit applies to the pool as a whole; warn if the pool mixes types.
            if optional_refs:
                optional_qs = _map_ref_list(
                    optional_refs,
                    problems_by_id,
                    section,
                    subject,
                    type_params,
                    subject_name,
                    warnings,
                )
                if optional_qs:
                    distinct_types = {q["type"] for q in optional_qs}
                    if len(distinct_types) > 1:
                        warnings.append(
                            f"section '{section_name or section_index}' optional pool mixes "
                            f"question types {sorted(distinct_types)}; kept as one set with a "
                            "single attempt limit and marking from the first question"
                        )
                    mandatory_count = optional.get("mandatory_count")
                    if not mandatory_count or mandatory_count > len(optional_qs):
                        mandatory_count = len(optional_qs)
                    title = f"{base_title} (optional)" if base_title else "Optional"
                    question_sets.append(
                        _build_set(optional_qs, title, mandatory_count)
                    )
                    num_graded_questions += len(optional_qs)
                    set_correct = optional_qs[0]["marking_scheme"]["correct"]
                    max_marks += set_correct * mandatory_count

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
        "time_limit": _time_limit(type_params),
        "instructions": type_params.get("instructions") or None,
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
