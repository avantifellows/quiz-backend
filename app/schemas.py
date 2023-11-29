from enum import Enum
from bson import ObjectId


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")


class QuestionType(Enum):
    single_choice = "single-choice"
    multi_choice = "multi-choice"
    subjective = "subjective"
    numerical_integer = "numerical-integer"
    numerical_float = "numerical-float"


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


class TestFormat(Enum):
    full_syllabus_test = "full_syllabus_test"
    major_test = "major_test"
    part_test = "part_test"
    chapter_test = "chapter_test"
    hiring_test = "hiring_test"
    evaluation_test = "evaluation_test"
    homework = "homework"
    mock_test = "mock_test"


class EventType(str, Enum):
    start_quiz = "start-quiz"
    resume_quiz = "resume-quiz"
    end_quiz = "end-quiz"
    dummy_event = "dummy-event"
