# from typing import List
from bson import ObjectId
from pydantic import BaseModel, Field
from schemas import QuestionType, PyObjectId

# class Image(BaseModel):
#     url: str
#     alt_text: str


# class Options(BaseModel):
#     id: int
#     text: str
#     image: Image


class Question(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    text: str
    type: QuestionType
    # options: List[Options] = []

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "text": "Which grade are you in?",
                "type": "subjective"
            }
        }


# class QuestionSet(BaseModel):
#     uuid: str
#     questions: List[int] = []
