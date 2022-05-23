from typing import Optional, List, Union
from bson import ObjectId
from pydantic import BaseModel, Field
from schemas import QuestionType, PyObjectId, NavigationMode, QuizLanguage, QuizType

answerType = Union[List[int], str, None]


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
        json_encoders = {ObjectId: str}
        schema_extra = {"example": {"name": "Avanti Fellows"}}


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


class QuizTimeLimit(BaseModel):
    min: int
    max: int


class QuestionMetadata(BaseModel):
    grade: str
    subject: str
    chapter: str
    topic: str
    competency: List[str]
    difficulty: str


class QuizMetadata(BaseModel):
    quiz_type: QuizType
    grade: str
    subject: str
    chapter: Optional[str]
    topic: Optional[str]


class Question(BaseModel):
    """Model for the body of the request that creates a question"""

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    text: str
    type: QuestionType
    instructions: Optional[str] = None
    image: Optional[Image] = None
    options: Optional[List[Option]] = []
    max_char_limit: Optional[int] = None
    correct_answer: Union[List[int], None] = None
    graded: bool = True
    marking_scheme: MarkingScheme = None
    solution: Optional[List[str]] = []
    metadata: QuestionMetadata = None

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


class Quiz(BaseModel):
    """Model for the body of the request that creates a quiz"""

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    question_sets: List[QuestionSet]
    max_marks: int
    num_graded_questions: int
    shuffle: bool = False
    num_attempts_allowed: int = 1
    time_limit: QuizTimeLimit = None
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
                        ]
                    }
                ],
                "max_marks": 10,
                "num_graded_questions": 3,
                "metadata": {"quiz_type": "homework", "subject": "Maths", "grade": "8"},
            }
        }


class QuizResponse(Quiz):
    """Model for the response of any request that returns a quiz"""

    class Config:
        schema_extra = {
            "example": {
                "_id": "1234",
                "question_sets": [
                    {
                        "_id": "12020",
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


class SessionAnswer(BaseModel):
    """Model for the body of the request that creates a session answer"""

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    question_id: str
    answer: answerType = None

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {"example": {"question_id": "4567", "answer": [0, 1, 2]}}


class UpdateSessionAnswer(BaseModel):
    """Model for the body of the request that updates a session answer"""

    answer: answerType

    class Config:
        schema_extra = {"example": {"answer": [0, 1, 2]}}


class SessionAnswerResponse(SessionAnswer):
    """Model for the response of any request that returns a session answer"""

    session_id: str


class Session(BaseModel):
    """Model for the body of the request that creates a session"""

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: str
    quiz_id: str

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

    has_quiz_ended: bool = False

    class Config:
        schema_extra = {
            "example": {
                "has_quiz_ended": True,
            }
        }


class SessionResponse(Session):
    """Model for the response of any request that returns a session"""

    is_first: bool
    hasQuizEnded: Optional[bool] = False
    session_answers: List[SessionAnswer]

    class Config:
        schema_extra = {
            "example": {
                "_id": "1234",
                "user_id": "1234",
                "quiz_id": "5678",
                "is_first": True,
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
