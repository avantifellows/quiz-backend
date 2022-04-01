from typing import Optional, List
from bson import ObjectId
from pydantic import BaseModel, Field
from schemas import QuestionType, PyObjectId


class Image(BaseModel):
    url: str
    alt_text: Optional[str] = None


class Option(BaseModel):
    text: str
    image: Optional[Image] = None


class MarkingScheme(BaseModel):
    correct: float
    wrong: float
    skipped: float


class QuestionMetadata(BaseModel):
    grade: str
    subject: str
    chapter: str
    topic: str
    competency: List[str]
    difficulty: str


class Question(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    text: str
    type: QuestionType
    instructions: Optional[str] = None
    image: Optional[Image] = None
    options: Optional[List[Option]] = []
    max_char_limit: Optional[int] = None
    correct_answer: Optional[List[int]] = None
    graded: bool = True
    markingScheme: MarkingScheme = None
    solution: Optional[List[str]] = []

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "text": "Which grade are you in?",
                "type": "multi-choice",
                "image": {
                    "url": "https://plio-prod-assets.s3.ap-south-1.amazonaws.com/images/afbxudrmbl.png",
                    "alt_text": "Image",
                },
                "options": [
                    {"text": "Option 1"},
                    {
                        "text": "Option 2",
                        "image": {
                            "url": "https://plio-prod-assets.s3.ap-south-1.amazonaws.com/images/afbxudrmbl.png"
                        },
                    },
                    {"text": "Option 3"},
                ],
                "correct_answer": [0, 2],
                "graded": True,
                "markingScheme": {"correct": 4, "wrong": -1, "skipped": 0},
            }
        }
