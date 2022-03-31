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
    single_choice = 'single-choice'
    multi_choice = 'multi-choice'
    subjective = 'subjective'
    numerical = 'numerical'
    match = 'match'

# def userEntity(item) -> dict:
#     return {
#         "uuid": item["uuid"],
#         "questions": item["questions"],
#     }


# def usersEntity(entity) -> list:
#     return [userEntity(item) for item in entity]


# def QuestionEntity(item) -> dict:
#     return {
#         "uuid": item["uuid"],
#         "instructions": item["instructions"],
#         "text": item["text"],
#         "type": item["type"],
#         "options": item["options"],
#     }


# def QuestionsEntity(entity) -> list:
#     return [QuestionEntity(item) for item in entity]
