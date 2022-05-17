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
    integer_numerical = "integer-numerical"
    float_numerical = "float-numerical"


class NavigationMode(Enum):
    linear = "linear"
    non_linear = "non-linear"


class QuizLanguage(Enum):
    english = "en"
    hindi = "hi"


class QuizType(Enum):
    assessment = "assessment"
    homework = "homework"
