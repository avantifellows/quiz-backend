from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from database import client
from models import Question

router = APIRouter(prefix='/questions', tags=['questions'])


@router.get('/')
async def get_questions():
    questions = client.quiz.questions.find({})
    return questions


@router.post('/', response_model=Question)
async def create_question(question: Question):
    question = jsonable_encoder(question)
    new_question = client.quiz.questions.insert_one(question)
    created_question = client.quiz.questions.find_one({
        "_id": new_question.inserted_id
    })
    return JSONResponse(
        status_code=status.HTTP_201_CREATED, content=created_question
    )
