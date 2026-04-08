from typing import Optional, List, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator
from schemas import (
    QuestionType,
    PyObjectId,
    NavigationMode,
    QuizLanguage,
    QuizType,
    EventType,
    TestFormat,
)
from datetime import datetime

answerType = Union[List[int], List[str], float, int, str, dict, None]


class Organization(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_schema_extra={"example": {"name": "Avanti Fellows"}},
    )

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str


class OrganizationResponse(Organization):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_schema_extra={"example": {"name": "Avanti Fellows"}},
    )

    name: str


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
    partial: Optional[List[PartialMarkRule]] = None


class QuizTimeLimit(BaseModel):
    min: int
    max: int


class Event(BaseModel):
    event_type: EventType
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class QuestionSetMetric(BaseModel):
    name: str
    qset_id: str
    marks_scored: float
    num_answered: int
    num_skipped: int
    num_correct: int
    num_wrong: int
    num_partially_correct: int
    num_marked_for_review: Optional[int] = None  # not there for non-assessment
    attempt_rate: float
    accuracy_rate: float


class SessionMetrics(BaseModel):
    qset_metrics: List[QuestionSetMetric]
    total_answered: int
    total_skipped: int
    total_correct: int
    total_wrong: int
    total_partially_correct: int
    total_marked_for_review: Optional[int] = None  # not there for non-assessment
    total_marks: float


class QuestionMetadata(BaseModel):
    grade: Optional[str] = None
    subject: Optional[str] = None
    chapter: Optional[str] = None
    chapter_id: Optional[str] = None
    topic: Optional[str] = None
    topic_id: Optional[str] = None
    competency: Optional[List[str]] = None
    difficulty: Optional[str] = None
    skill: Optional[str] = None
    skill_id: Optional[str] = None
    concept: Optional[str] = None
    concept_id: Optional[str] = None
    priority: Optional[str] = None


class QuizMetadata(BaseModel):
    quiz_type: QuizType
    test_format: Optional[TestFormat] = None
    grade: Optional[str] = None
    subject: Optional[str] = None
    chapter: Optional[str] = None
    topic: Optional[str] = None
    source: Optional[str] = None
    source_id: Optional[str] = None
    session_end_time: Optional[str] = None  # format: %Y-%m-%d %I:%M:%S %p
    next_step_url: Optional[str] = None  # URL to redirect to after quiz completion
    next_step_text: Optional[str] = None  # Text to display on the next step button
    next_step_autostart: Optional[bool] = False  # Whether next step should auto-start
    single_page_header_text: Optional[str] = None  # header text for single page mode


class Question(BaseModel):
    """Model for the body of the request that creates a question"""

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    text: str
    type: QuestionType
    instructions: Optional[str] = None
    image: Optional[Image] = None
    options: Optional[List[Option]] = Field(default_factory=list)
    max_char_limit: Optional[int] = None
    matrix_size: Optional[List[int]] = None  # for matrix match question
    matrix_rows: Optional[List[str]] = None  # for matrix rating/numerical questions
    correct_answer: Union[List[int], List[str], float, int, dict, None] = None
    graded: bool = True
    force_correct: bool = False
    marking_scheme: Optional[MarkingScheme] = None
    solution: Optional[List[str]] = Field(default_factory=list)
    metadata: Optional[QuestionMetadata] = None
    source: Optional[str] = None
    source_id: Optional[str] = None

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_schema_extra={
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
        },
    )


class QuestionResponse(Question):
    """Model for the response of any request that returns a question"""

    model_config = ConfigDict(
        json_schema_extra={
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
        },
    )

    question_set_id: str
    text: Optional[str] = None


class QuestionSet(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    questions: List[Question]
    title: Optional[str] = None
    description: Optional[str] = None
    max_questions_allowed_to_attempt: int
    marking_scheme: Optional[MarkingScheme] = (
        None  # takes precedence over question-level marking scheme
    )


class QuestionSetResponse(QuestionSet):
    questions: List[QuestionResponse]


class Quiz(BaseModel):
    """Model for the body of the request that creates a quiz"""

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_schema_extra={
            "example": {
                "question_sets": [
                    {
                        "title": "Physics set",
                        "max_questions_allowed_to_attempt": 3,
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
                    "test_format": "part_test",
                },
            }
        },
    )

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    title: Optional[str] = None
    question_sets: List[QuestionSet]
    max_marks: int
    num_graded_questions: int
    shuffle: bool = False
    num_attempts_allowed: int = 1
    time_limit: Optional[QuizTimeLimit] = None
    # review answers immediately after quiz ends
    review_immediate: Optional[bool] = True
    display_solution: Optional[bool] = True
    show_scores: Optional[bool] = True
    navigation_mode: NavigationMode = "linear"
    instructions: Optional[str] = None
    language: QuizLanguage = "en"
    metadata: Optional[QuizMetadata] = None


class GetQuizResponse(Quiz):
    """Model for the response of any request that returns a quiz"""

    model_config = ConfigDict(
        json_schema_extra={
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
                "metadata": {
                    "quiz_type": "JEE",
                    "subject": "Maths",
                    "grade": "8",
                    "test_format": "full_syllabus_test",
                },
            }
        },
    )

    question_sets: List[QuestionSetResponse]


class CreateQuizResponse(BaseModel):
    """Model for the response of a request that creates a quiz"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "1234",
            }
        },
    )

    id: str


class SessionAnswer(BaseModel):
    """Model for the body of the request that creates a session answer"""

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_schema_extra={
            "example": {"question_id": "4567", "answer": [0, 1, 2], "time_spent": 30}
        },
    )

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    question_id: str
    answer: answerType = None
    visited: bool = False
    time_spent: Optional[int] = None  # in seconds
    marked_for_review: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UpdateSessionAnswer(BaseModel):
    """Model for the body of the request that updates a session answer"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"answer": [0, 1, 2], "visited": True, "time_spent": 20}
        },
    )

    answer: Optional[answerType] = None
    visited: Optional[bool] = None
    time_spent: Optional[int] = None
    marked_for_review: Optional[bool] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


"""
Note : The below model is not being used currently anywhere
"""


class SessionAnswerResponse(SessionAnswer):
    """Model for the response of any request that returns a session answer"""

    session_id: str


class Session(BaseModel):
    """Model for the body of the request that creates a session"""

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_schema_extra={
            "example": {
                "user_id": "1234",
                "quiz_id": "5678",
            }
        },
    )

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: str
    quiz_id: str
    omr_mode: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Session-level "last modified" timestamp. This is used for incremental ETL sync.
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    events: List[Event] = Field(default_factory=list)

    @field_validator("user_id", mode="before")
    @classmethod
    def coerce_user_id_to_str(cls, v):
        """Preserve Pydantic v1 behavior: accept int input and coerce to str."""
        return str(v)

    has_quiz_ended: bool = False
    time_limit_max: Optional[
        int
    ] = None  # store quiz.time_limit.max in seconds for derivation
    start_quiz_time: Optional[datetime] = None
    end_quiz_time: Optional[datetime] = None
    total_time_spent: Optional[
        float
    ] = None  # in seconds (float for sub-second precision)
    question_order: List[int] = Field(
        default_factory=list
    )  # random order of questions for each quiz assesment/homework
    metrics: Optional[SessionMetrics] = None  # gets updated when quiz ends


class UpdateSession(BaseModel):
    """Model for the body of the request that updates a session"""

    model_config = ConfigDict(
        json_schema_extra={"example": {"event": "start-quiz"}},
    )

    event: EventType
    metrics: Optional[SessionMetrics] = None


class SessionResponse(Session):
    """Model for the response of any request that returns a session"""

    model_config = ConfigDict(
        json_schema_extra={
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
                        "time_spent": 20,
                    },
                    {
                        "_id": "30c000dww0d34h573",
                        "question_id": "20200c0c0cw0",
                        "answer": [0],
                        "time_spent": 30,
                    },
                ],
                "question_order": [0, 1, 2, 3],
            }
        },
    )

    is_first: bool
    session_answers: List[SessionAnswer]
    time_remaining: Optional[int] = None  # time in seconds


class UpdateSessionResponse(BaseModel):
    """Model for the response of request that updates a session"""

    model_config = ConfigDict(
        json_schema_extra={"example": {"time_remaining": 300}},
    )

    time_remaining: Optional[int] = None  # time in seconds
    metrics: Optional[SessionMetrics] = None
