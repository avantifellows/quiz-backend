from tkinter.tix import INTEGER
from tokenize import Number
from typing import List
from pydantic import BaseModel
from enum import Enum


class Type(Enum):
    single_choice = 'single-choice'
    multi_choice = 'multi_choice'
    subjective = 'subjective'
    numerical = 'numerical'
    match = 'match'


class Image(BaseModel):
    url: str
    alt_text: str


class Options(BaseModel):
    id: int
    text: str
    image: Image


class Question(BaseModel):
    uuid: str
    instructions: str
    text: str
    type: Type = None
    options: List[Options] = []


class QuestionSet(BaseModel):
    uuid: str
    questions: List[int] = []
