from typing import Optional, List, Union
from bson import ObjectId
from pydantic import BaseModel, Field
from schemas import (
    QuestionType,
    PyObjectId,
    NavigationMode,
    QuizLanguage,
    QuizType,
    EventType,
)
from datetime import datetime

answerType = Union[List[int], float, int, str, None]


class Organization(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {"example": {"name": "Avanti Fellows"}}


class OrganizationResponse(Organization):
    name: str

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        schema_extra = {"example": {"name": "Avanti Fellows"}}


class Image(BaseModel):
    url: str
    alt_text: Optional[str] = None


class Option(BaseModel):
    text: str
    image: Optional[Image] = None


class PartialMarkCondition(BaseModel):
    num_correct_selected: int
    # for now, we only consider condition on count of correctly selected options


class PartialMarkRule(BaseModel):
    conditions: List[PartialMarkCondition]
    marks: int


class MarkingScheme(BaseModel):
    correct: float
    wrong: float
    skipped: float
    partial: List[PartialMarkRule] = None


class QuizTimeLimit(BaseModel):
    min: int
    max: int


class Event(BaseModel):
    event_type: EventType
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class QuestionMetadata(BaseModel):
    grade: Optional[str]
    subject: Optional[str]
    chapter: Optional[str]
    chapter_id: Optional[str]
    topic: Optional[str]
    topic_id: Optional[str]
    competency: Optional[List[str]]
    difficulty: Optional[str]


class QuizMetadata(BaseModel):
    quiz_type: QuizType
    grade: Optional[str]
    subject: Optional[str]
    chapter: Optional[str]
    topic: Optional[str]
    source: Optional[str]
    source_id: Optional[str]
    session_end_time: Optional[str]  # format: %Y-%m-%d %I:%M:%S %p


class Question(BaseModel):
    """Model for the body of the request that creates a question"""

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    text: str
    type: QuestionType
    instructions: Optional[str] = None
    image: Optional[Image] = None
    options: Optional[List[Option]] = []
    max_char_limit: Optional[int] = None
    correct_answer: Union[List[int], float, int, None] = None
    graded: bool = True
    marking_scheme: MarkingScheme = None
    solution: Optional[List[str]] = []
    metadata: QuestionMetadata = None
    source: Optional[str] = None
    source_id: Optional[str] = None

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
                "marking_scheme": {"correct": 4, "wrong": -1, "skipped": 0},
            }
        }


class QuestionResponse(Question):
    """Model for the response of any request that returns a question"""

    question_set_id: str
    text: Optional[str] = None

    class Config:
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
                "marking_scheme": {"correct": 4, "wrong": -1, "skipped": 0},
                "question_set_id": "1234",
            }
        }


class QuestionSet(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    questions: List[Question]
    title: Optional[str] = None
    description: Optional[str] = None
    max_questions_allowed_to_attempt: int
    marking_scheme: MarkingScheme = (
        None  # takes precedence over question-level marking scheme
    )


class QuestionSetResponse(QuestionSet):
    questions: List[QuestionResponse]


class Quiz(BaseModel):
    """Model for the body of the request that creates a quiz"""

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    title: Optional[str]
    question_sets: List[QuestionSet]
    max_marks: int
    num_graded_questions: int
    shuffle: bool = False
    num_attempts_allowed: int = 1
    time_limit: Optional[QuizTimeLimit] = None
    # review answers immediately after quiz ends
    review_immediate: Optional[bool] = True
    navigation_mode: NavigationMode = "linear"
    instructions: Optional[str] = None
    language: QuizLanguage = "en"
    metadata: QuizMetadata = None

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "question_sets": [
                    {
                        "title": "Physics set",
                        "max_questions_allowed_to_attempt": 2,
                        "questions": [
                            {
                                "text": "Which grade are you in?",
                                "type": "single-choice",
                                "options": [
                                    {"text": "Option 1"},
                                    {"text": "Option 2"},
                                    {"text": "Option 3"},
                                ],
                                "graded": False,
                            },
                            {
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
                            },
                            {
                                "text": "Which subject are you studying?",
                                "type": "multi-choice",
                                "options": [
                                    {"text": "Option 1"},
                                    {"text": "Option 2"},
                                    {"text": "Option 3"},
                                ],
                                "graded": False,
                            },
                        ],
                    }
                ],
                "title": "hello world",
                "max_marks": 10,
                "num_graded_questions": 3,
                "metadata": {
                    "quiz_type": "homework",
                    "subject": "Maths",
                    "grade": "8",
                    "source": "cms",
                },
            }
        }


class GetQuizResponse(Quiz):
    """Model for the response of any request that returns a quiz"""

    question_sets: List[QuestionSetResponse]

    class Config:
        schema_extra = {
            "example": {
                "_id": "1234",
                "question_sets": [
                    {
                        "_id": "12020",
                        "title": "question set title",
                        "max_questions_allowed_to_attempt": 2,
                        "questions": [
                            {
                                "_id": "304030",
                                "text": "Which grade are you in?",
                                "type": "single-choice",
                                "options": [
                                    {"text": "Option 1"},
                                    {"text": "Option 2"},
                                    {"text": "Option 3"},
                                ],
                                "graded": False,
                            },
                            {
                                "_id": "3039004",
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
                            },
                            {
                                "_id": "393920",
                                "text": "Which subject are you studying?",
                                "type": "multi-choice",
                                "options": [
                                    {"text": "Option 1"},
                                    {"text": "Option 2"},
                                    {"text": "Option 3"},
                                ],
                                "graded": False,
                            },
                        ],
                    }
                ],
                "max_marks": 10,
                "num_graded_questions": 3,
                "metadata": {"quiz_type": "JEE", "subject": "Maths", "grade": "8"},
            }
        }


class CreateQuizResponse(BaseModel):
    """Model for the response of a request that creates a quiz"""

    id: str

    class Config:
        schema_extra = {
            "example": {
                "id": "1234",
            }
        }


class SessionAnswer(BaseModel):
    """Model for the body of the request that creates a session answer"""

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    question_id: str
    answer: answerType = None
    visited: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {"example": {"question_id": "4567", "answer": [0, 1, 2]}}


class UpdateSessionAnswer(BaseModel):
    """Model for the body of the request that updates a session answer"""

    answer: Optional[answerType]
    visited: Optional[bool]
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        schema_extra = {"example": {"answer": [0, 1, 2], "visited": True}}


"""
Note : The below model is not being used currently anywhere
"""


class SessionAnswerResponse(SessionAnswer):
    """Model for the response of any request that returns a session answer"""

    session_id: str


class Session(BaseModel):
    """Model for the body of the request that creates a session"""

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: str
    quiz_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    events: List[Event] = []
    has_quiz_ended: bool = False

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "user_id": "1234",
                "quiz_id": "5678",
            }
        }


class UpdateSession(BaseModel):
    """Model for the body of the request that updates a session"""

    event: EventType

    class Config:
        schema_extra = {"example": {"event": "start-quiz"}}


class SessionResponse(Session):
    """Model for the response of any request that returns a session"""

    is_first: bool
    session_answers: List[SessionAnswer]
    time_remaining: Optional[int] = None  # time in seconds

    class Config:
        schema_extra = {
            "example": {
                "_id": "1234",
                "user_id": "1234",
                "quiz_id": "5678",
                "is_first": True,
                "time_remaining": 300,
                "has_quiz_ended": False,
                "session_answers": [
                    {
                        "_id": "1030c00d03",
                        "question_id": "4ne0c0s0",
                        "answer": [0, 1, 2],
                    },
                    {
                        "_id": "30c000dww0d34h573",
                        "question_id": "20200c0c0cw0",
                        "answer": [0],
                    },
                ],
            }
        }


class UpdateSessionResponse(BaseModel):
    """Model for the response of request that updates a session"""

    time_remaining: Optional[int]  # time in seconds

    class Config:
        schema_extra = {"example": {"time_remaining": 300}}
