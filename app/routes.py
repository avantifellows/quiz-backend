from fastapi import APIRouter
from models import QuestionSet, Question, Type, Image, Options
from schemas import userEntity, usersEntity, QuestionEntity, QuestionsEntity
from bson import objectid

player = APIRouter()


@player.get('/')
async def find_all_QuestionSet():
    return usersEntity(conn.player.QuestionSet.find())


@player.get('/{uuid}')
async def find_QuestionSet(uuid):
    return userEntity(conn.player.QuestionSet.find_one({"uuid": objectid(uuid)}))


@player.post('/')
async def create_QuestionSet(questionset: QuestionSet):
    conn.player.QuestionSet.insert_one(dict(questionset))
    return usersEntity(conn.player.QuestionSet.find())


@player.put('/{uuid}')
async def create_QuestionSet(uuid, questionset: QuestionSet):
    (conn.player.QuestionSet.find_one_and_update({"uuid": objectid(uuid)}, {
        "$set": dict(questionset)
    }))
    return userEntity(conn.player.QuestionSet.find_one({"uuid": objectid(uuid)}))


@player.delete('/{uuid}')
async def delete_QuestionSet(uuid):
    return userEntity(conn.player.QuestionSet.find_one_and_delete({"uuid": objectid(uuid)}))


@player.get('/.', response_model=Question)
async def find_all_Question():
    return QuestionsEntity(conn.player.Question.find())


@player.post('/.', response_model=Question)
async def create_Question(question: Question):
    conn.player.Question.insert_one(dict(question))
    return QuestionEntity(conn.player.Question.find())
