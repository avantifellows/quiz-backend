from enum import Enum
from typing import Any
from bson import ObjectId
from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema


class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls.validate,
            serialization=core_schema.to_string_ser_schema(),
        )

    @classmethod
    def validate(cls, v: Any) -> ObjectId:
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str) and ObjectId.is_valid(v):
            return ObjectId(v)
        raise ValueError("Invalid ObjectId")

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return {"type": "string"}


class QuestionType(Enum):
    single_choice = "single-choice"
    multi_choice = "multi-choice"
    subjective = "subjective"
    numerical_integer = "numerical-integer"
    numerical_float = "numerical-float"
    matrix_match = "matrix-match"
    matrix_rating = "matrix-rating"
    matrix_numerical = "matrix-numerical"
    matrix_subjective = "matrix-subjective"


class NavigationMode(Enum):
    linear = "linear"
    non_linear = "non-linear"


class QuizLanguage(Enum):
    english = "en"
    hindi = "hi"


class QuizType(Enum):
    assessment = "assessment"
    homework = "homework"
    omr = "omr-assessment"
    form = "form"


class TestFormat(Enum):
    full_syllabus_test = "full_syllabus_test"
    major_test = "major_test"
    part_test = "part_test"
    chapter_test = "chapter_test"
    hiring_test = "hiring_test"
    evaluation_test = "evaluation_test"
    homework = "homework"
    mock_test = "mock_test"
    combined_chapter_test = "combined_chapter_test"
    questionnaire = "questionnaire"


class EventType(str, Enum):
    start_quiz = "start-quiz"
    resume_quiz = "resume-quiz"
    end_quiz = "end-quiz"
    dummy_event = "dummy-event"
