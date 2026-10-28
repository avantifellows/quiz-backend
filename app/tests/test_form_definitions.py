"""Form-builder definitions: the pure build (services.form_definition_build), the CRUD API
(routers/form_definitions.py) and building / regenerating a session's quiz from one
(POST /quiz/from-form-definition, PUT /quiz/{id}/from-form-definition)."""

import copy
import unittest

from .base import BaseTestCase
from routers import form_definitions, quizzes
from services.form_definition_build import (
    FormBuildError,
    build_quiz,
    completeness_errors,
    structure_errors,
)

DEFINITIONS = form_definitions.router.prefix


def _text(en, hi=""):
    return {"en": en, "hi": hi}


def _option(oid, en, hi=""):
    return {"id": oid, "text": _text(en, hi)}


def sample_definition():
    """Two sections, five questions: q2 follows q1 "Yes"; q5 follows q3 "Other"."""
    return {
        "title": "Mentorship Screener",
        "languages": ["en", "hi"],
        "header_text": "Please answer honestly",
        "sections": [
            {
                "id": "s1",
                "title": "Friends",
                "questions": [
                    {
                        "id": "q1",
                        "type": "single-choice",
                        "text": _text(
                            "Do you have a study group?", "क्या आपका समूह है?"
                        ),
                        "options": [
                            _option("o1", "Yes", "हाँ"),
                            _option("o2", "No", "नहीं"),
                        ],
                    },
                    {
                        "id": "q2",
                        "type": "subjective",
                        "text": _text("Who is in it?", "उसमें कौन है?"),
                        "show_if": {"question_id": "q1", "option_ids": ["o1"]},
                    },
                ],
            },
            {
                "id": "s2",
                "title": "Coaching",
                "questions": [
                    {
                        "id": "q3",
                        "type": "single-choice-other",
                        "text": _text("Where do you study?"),
                        "options": [
                            _option("o3", "School"),
                            _option("o4", "Coaching"),
                            _option("o5", "Other", "अन्य"),
                        ],
                    },
                    {
                        "id": "q4",
                        "type": "matrix-rating",
                        "text": _text("Rate these"),
                        "rows": [
                            _option("r1", "Maths", "गणित"),
                            _option("r2", "Physics"),
                        ],
                        "scale": _text("Low, High", "कम, ज़्यादा"),
                    },
                    {
                        "id": "q5",
                        "type": "multi-choice",
                        "text": _text("Which ones?"),
                        "required": False,
                        "options": [_option("o6", "A"), _option("o7", "B")],
                        "show_if": {"question_id": "q3", "option_ids": ["o5"]},
                    },
                ],
            },
        ],
    }


def _flat(quiz):
    return [q for qset in quiz["question_sets"] for q in qset["questions"]]


class FormDefinitionBuildTestCase(unittest.TestCase):
    def test_builds_positional_quiz_with_display_conditions(self):
        quiz = build_quiz(sample_definition(), "def1", None)
        questions = _flat(quiz)
        self.assertEqual([len(s["questions"]) for s in quiz["question_sets"]], [2, 3])
        self.assertEqual(
            [s["title"] for s in quiz["question_sets"]], ["Friends", "Coaching"]
        )
        self.assertEqual(
            questions[1]["display_condition"],
            {"source_position": 0, "option_indices": [0]},
        )
        self.assertEqual(
            questions[4]["display_condition"],
            {"source_position": 2, "option_indices": [2]},
        )
        self.assertEqual(
            [q["source_id"] for q in questions], ["q1", "q2", "q3", "q4", "q5"]
        )
        self.assertTrue(
            all(q["source"] == "form-builder" and not q["graded"] for q in questions)
        )

    def test_form_metadata_and_required(self):
        quiz = build_quiz(sample_definition(), "def1", None)
        self.assertEqual(
            quiz["metadata"],
            {
                "quiz_type": "form",
                "test_format": "questionnaire",
                "source": "form-builder",
                "source_id": "def1",
                "lang_code": None,
                "single_page_header_text": "Please answer honestly",
            },
        )
        self.assertTrue(quiz["require_all_questions"])
        self.assertEqual(
            [q["required"] for q in _flat(quiz)], [True, True, True, True, False]
        )

    def test_english_only_when_no_language_chosen(self):
        questions = _flat(build_quiz(sample_definition(), "def1", None))
        self.assertEqual(questions[0]["text"], "Do you have a study group?")
        self.assertEqual([o["text"] for o in questions[0]["options"]], ["Yes", "No"])

    def test_hindi_is_stacked_under_english(self):
        questions = _flat(build_quiz(sample_definition(), "def1", "hi"))
        self.assertEqual(
            questions[0]["text"], "Do you have a study group?\nक्या आपका समूह है?"
        )
        self.assertEqual(
            [o["text"] for o in questions[0]["options"]], ["Yes\nहाँ", "No\nनहीं"]
        )
        # no Hindi text -> English alone
        self.assertEqual(questions[2]["text"], "Where do you study?")
        self.assertEqual(
            questions[3]["options"], [{"text": "Low\nकम"}, {"text": "High\nज़्यादा"}]
        )
        self.assertEqual(questions[3]["matrix_rows"], ["Maths\nगणित", "Physics"])

    def test_header_text_comes_from_the_form_as_typed(self):
        # one text, not stacked with the session's language
        for lang_code in (None, "hi"):
            self.assertEqual(
                build_quiz(sample_definition(), "def1", lang_code)["metadata"][
                    "single_page_header_text"
                ],
                "Please answer honestly",
            )
        definition = sample_definition()
        definition["header_text"] = "  "
        self.assertIsNone(
            build_quiz(definition, "def1", None)["metadata"]["single_page_header_text"]
        )
        # stored per language during development: its English is used
        definition["header_text"] = _text("Old header", "पुराना")
        self.assertEqual(
            build_quiz(definition, "def1", None)["metadata"]["single_page_header_text"],
            "Old header",
        )

    def test_type_specific_fields(self):
        questions = _flat(build_quiz(sample_definition(), "def1", None))
        self.assertEqual(questions[1]["max_char_limit"], 500)  # subjective
        self.assertEqual(questions[2]["max_char_limit"], 500)  # Other box
        self.assertEqual(questions[2]["options"][-1], {"text": "Other"})
        self.assertNotIn("max_char_limit", questions[0])

    def test_refuses_a_language_the_form_does_not_have(self):
        definition = sample_definition()
        definition["languages"] = ["en"]
        with self.assertRaises(FormBuildError) as ctx:
            build_quiz(definition, "def1", "hi")
        self.assertIn("the form has no 'hi' text", ctx.exception.errors)

    def test_structure_errors(self):
        definition = sample_definition()
        q2 = definition["sections"][0]["questions"][1]
        q2["show_if"] = {"question_id": "q4", "option_ids": ["x"]}  # a LATER question
        definition["sections"][1]["questions"][0][
            "options"
        ].pop()  # Other no longer last
        errors = structure_errors(definition)
        self.assertTrue(any("earlier question" in e for e in errors))
        self.assertTrue(any('last option must be "Other"' in e for e in errors))

    def test_condition_on_a_non_choice_or_missing_option(self):
        definition = sample_definition()
        q5 = definition["sections"][1]["questions"][2]
        q5["show_if"] = {"question_id": "q2", "option_ids": ["o1"]}
        self.assertTrue(
            any("choice question" in e for e in structure_errors(definition))
        )
        q5["show_if"] = {"question_id": "q1", "option_ids": ["nope"]}
        self.assertTrue(any("doesn't have" in e for e in structure_errors(definition)))

    def test_a_follow_up_without_its_option_is_incomplete_not_inconsistent(self):
        definition = sample_definition()
        definition["sections"][0]["questions"][1]["show_if"]["option_ids"] = []
        self.assertEqual(structure_errors(definition), [])
        self.assertTrue(
            any(
                "no trigger option chosen" in e for e in completeness_errors(definition)
            )
        )

    def test_completeness_errors(self):
        definition = sample_definition()
        definition["sections"][0]["questions"][0]["text"]["en"] = " "
        definition["sections"][1]["questions"][2]["options"] = [_option("o6", "A")]
        definition["sections"].append({"id": "s3", "title": "", "questions": []})
        errors = completeness_errors(definition)
        self.assertTrue(any("missing English text" in e for e in errors))
        self.assertTrue(any("at least two options" in e for e in errors))
        self.assertIn("section 3 has no questions", errors)
        self.assertEqual(completeness_errors(sample_definition()), [])


class FormDefinitionApiTestCase(BaseTestCase):
    def create(self, definition=None, actor="pm@avantifellows.org"):
        response = self.client.post(
            DEFINITIONS + "/",
            json={**(definition or sample_definition()), "actor": actor},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def build_quiz(self, definition_id, lang_code=None):
        body = {"definition_id": definition_id}
        if lang_code:
            body["lang_code"] = lang_code
        return self.client.post(
            quizzes.router.prefix + "/from-form-definition", json=body
        )

    # ---- CRUD ----------------------------------------------------------------------------
    def test_create_and_get(self):
        definition_id = self.create()
        stored = self.client.get(f"{DEFINITIONS}/{definition_id}").json()
        self.assertEqual(stored["title"], "Mentorship Screener")
        self.assertEqual(stored["languages"], ["en", "hi"])
        self.assertEqual(stored["question_count"], 5)
        self.assertEqual(stored["conditional_count"], 2)
        self.assertTrue(stored["ready"])
        self.assertIsNone(stored["locked_at"])
        self.assertEqual(stored["created_by"], "pm@avantifellows.org")

    def test_get_unknown_is_404(self):
        self.assertEqual(self.client.get(f"{DEFINITIONS}/nope").status_code, 404)

    def test_incomplete_draft_saves_but_is_not_ready(self):
        definition = sample_definition()
        definition["sections"][0]["questions"][0]["text"]["en"] = ""
        definition_id = self.create(definition)
        self.assertFalse(
            self.client.get(f"{DEFINITIONS}/{definition_id}").json()["ready"]
        )

    def test_inconsistent_definition_is_rejected(self):
        definition = sample_definition()
        definition["sections"][0]["questions"][1]["show_if"]["question_id"] = "q4"
        response = self.client.post(DEFINITIONS + "/", json=definition)
        self.assertEqual(response.status_code, 422)

    def test_english_is_always_a_language(self):
        definition = sample_definition()
        definition["languages"] = ["hi"]
        stored = self.client.get(f"{DEFINITIONS}/{self.create(definition)}").json()
        self.assertEqual(stored["languages"], ["en", "hi"])

    def test_list_newest_first_with_search_and_paging(self):
        for title in ("Parent Feedback", "Mentorship Screener", "Hostel Survey"):
            definition = sample_definition()
            definition["title"] = title
            self.create(definition)
        listing = self.client.get(DEFINITIONS + "/").json()
        self.assertEqual(
            [row["title"] for row in listing["items"]],
            ["Hostel Survey", "Mentorship Screener", "Parent Feedback"],
        )
        self.assertNotIn("sections", listing["items"][0])
        found = self.client.get(DEFINITIONS + "/", params={"search": "screen"}).json()
        self.assertEqual(
            [row["title"] for row in found["items"]], ["Mentorship Screener"]
        )
        page = self.client.get(DEFINITIONS + "/", params={"limit": 2}).json()
        self.assertEqual(len(page["items"]), 2)
        self.assertTrue(page["has_more"])

    def test_list_ready_only(self):
        draft = sample_definition()
        draft["title"] = "Draft"
        draft["sections"] = []
        self.create(draft)
        self.create()
        listing = self.client.get(DEFINITIONS + "/", params={"ready_only": True}).json()
        self.assertEqual(
            [row["title"] for row in listing["items"]], ["Mentorship Screener"]
        )

    def test_save_replaces_content(self):
        definition_id = self.create()
        definition = sample_definition()
        definition["title"] = "Renamed"
        response = self.client.put(
            f"{DEFINITIONS}/{definition_id}",
            json={**definition, "actor": "other@x.org"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        stored = self.client.get(f"{DEFINITIONS}/{definition_id}").json()
        self.assertEqual(stored["title"], "Renamed")
        self.assertEqual(stored["updated_by"], "other@x.org")
        self.assertEqual(stored["created_by"], "pm@avantifellows.org")

    def test_delete_unused(self):
        definition_id = self.create()
        self.assertEqual(
            self.client.delete(f"{DEFINITIONS}/{definition_id}").status_code, 204
        )
        self.assertEqual(
            self.client.get(f"{DEFINITIONS}/{definition_id}").status_code, 404
        )
        self.assertEqual(
            self.client.delete(f"{DEFINITIONS}/{definition_id}").status_code, 404
        )

    # ---- building a session's quiz + the lock ---------------------------------------------
    def test_build_creates_a_form_quiz_and_locks_the_definition(self):
        definition_id = self.create()
        response = self.build_quiz(definition_id, "hi")
        self.assertEqual(response.status_code, 201, response.text)
        quiz_id = response.json()["id"]

        quiz = self.db.quizzes.find_one({"_id": quiz_id})
        self.assertEqual(quiz["metadata"]["source"], "form-builder")
        self.assertEqual(quiz["metadata"]["source_id"], definition_id)
        self.assertEqual(quiz["metadata"]["lang_code"], "hi")
        self.assertEqual(
            self.db.questions.count_documents({}), 5 + self._fixture_questions()
        )
        form = self.client.get(f"/form/{quiz_id}").json()
        self.assertEqual(
            form["question_sets"][0]["questions"][0]["text"],
            "Do you have a study group?\nक्या आपका समूह है?",
        )
        self.assertIsNotNone(
            self.client.get(f"{DEFINITIONS}/{definition_id}").json()["locked_at"]
        )

    def _fixture_questions(self):
        """Questions BaseTestCase.setUp inserted (other quizzes) — counted before the test."""
        return self.db.questions.count_documents({"source": {"$ne": "form-builder"}})

    def test_locked_definition_cannot_be_saved_or_deleted(self):
        definition_id = self.create()
        self.assertEqual(self.build_quiz(definition_id).status_code, 201)
        save = self.client.put(
            f"{DEFINITIONS}/{definition_id}", json=sample_definition()
        )
        self.assertEqual(save.status_code, 409)
        self.assertIn("Duplicate", save.json()["detail"])
        self.assertEqual(
            self.client.delete(f"{DEFINITIONS}/{definition_id}").status_code, 409
        )

    def test_a_locked_form_keeps_its_first_lock_time(self):
        definition_id = self.create()
        self.build_quiz(definition_id)
        first = self.client.get(f"{DEFINITIONS}/{definition_id}").json()["locked_at"]
        self.assertEqual(self.build_quiz(definition_id).status_code, 201)
        self.assertEqual(
            self.client.get(f"{DEFINITIONS}/{definition_id}").json()["locked_at"], first
        )

    def test_an_incomplete_form_is_refused_and_stays_unlocked(self):
        definition = sample_definition()
        definition["sections"][0]["questions"][0]["text"]["en"] = ""
        definition_id = self.create(definition)
        response = self.build_quiz(definition_id)
        self.assertEqual(response.status_code, 422)
        self.assertIsNone(
            self.client.get(f"{DEFINITIONS}/{definition_id}").json()["locked_at"]
        )

    def test_build_unknown_definition_is_404(self):
        self.assertEqual(self.build_quiz("nope").status_code, 404)

    def test_build_with_a_language_the_form_lacks_is_422(self):
        definition = sample_definition()
        definition["languages"] = ["en"]
        response = self.build_quiz(self.create(definition), "hi")
        self.assertEqual(response.status_code, 422)

    def test_sessions_using_the_form(self):
        definition_id = self.create()
        quiz_ids = [self.build_quiz(definition_id).json()["id"] for _ in range(2)]
        self.db.quizzes.update_one({"_id": quiz_ids[0]}, {"$set": {"title": "Cycle 1"}})
        sessions = self.client.get(f"{DEFINITIONS}/{definition_id}/sessions").json()
        self.assertEqual([row["quiz_id"] for row in sessions], sorted(quiz_ids))
        self.assertIn("Cycle 1", [row["title"] for row in sessions])
        self.assertEqual(self.client.get(f"{DEFINITIONS}/other/sessions").json(), [])

    # ---- regenerate in place -------------------------------------------------------------
    def test_regenerate_keeps_ids_and_session_settings_and_can_change_language(self):
        definition_id = self.create()
        quiz_id = self.build_quiz(definition_id).json()["id"]
        before = self.db.quizzes.find_one({"_id": quiz_id})
        # what sessionCreator writes after create (it leaves a form-builder header alone)
        self.db.quizzes.update_one(
            {"_id": quiz_id}, {"$set": {"title": "G12 Screener – Cycle 1"}}
        )
        response = self.client.put(
            f"{quizzes.router.prefix}/{quiz_id}/from-form-definition",
            json={"lang_code": "hi"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        after = self.db.quizzes.find_one({"_id": quiz_id})
        self.assertEqual(
            [[q["_id"] for q in s["questions"]] for s in after["question_sets"]],
            [[q["_id"] for q in s["questions"]] for s in before["question_sets"]],
        )
        self.assertEqual(after["title"], "G12 Screener – Cycle 1")
        # the header is the form's (decision D23), as typed
        self.assertEqual(
            after["metadata"]["single_page_header_text"], "Please answer honestly"
        )
        self.assertEqual(after["metadata"]["lang_code"], "hi")
        first_question = self.db.questions.find_one(
            {"_id": after["question_sets"][0]["questions"][0]["_id"]}
        )
        self.assertTrue(first_question["text"].endswith("क्या आपका समूह है?"))

    def test_regenerate_without_lang_code_keeps_the_language(self):
        quiz_id = self.build_quiz(self.create(), "hi").json()["id"]
        self.client.put(
            f"{quizzes.router.prefix}/{quiz_id}/from-form-definition", json={}
        )
        self.assertEqual(
            self.db.quizzes.find_one({"_id": quiz_id})["metadata"]["lang_code"], "hi"
        )

    def test_regenerate_refuses_a_quiz_not_built_from_a_form(self):
        response = self.client.put(
            f"{quizzes.router.prefix}/{self.homework_quiz_id}/from-form-definition",
            json={},
        )
        self.assertEqual(response.status_code, 409)

    def test_regenerate_refuses_another_form(self):
        quiz_id = self.build_quiz(self.create()).json()["id"]
        response = self.client.put(
            f"{quizzes.router.prefix}/{quiz_id}/from-form-definition",
            json={"definition_id": self.create()},
        )
        self.assertEqual(response.status_code, 409)

    def test_regenerate_refuses_a_reshaped_definition(self):
        # Defence in depth: a locked form can't change via the API, so edit Mongo directly.
        definition_id = self.create()
        quiz_id = self.build_quiz(definition_id).json()["id"]
        definition = copy.deepcopy(sample_definition())
        definition["sections"][0]["questions"].pop()
        self.db.form_definitions.update_one(
            {"_id": definition_id}, {"$set": {"sections": definition["sections"]}}
        )
        response = self.client.put(
            f"{quizzes.router.prefix}/{quiz_id}/from-form-definition", json={}
        )
        self.assertEqual(response.status_code, 409)
