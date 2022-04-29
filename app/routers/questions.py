from fastapi import APIRouter, status, HTTPException
from database import client
from models import QuestionResponse

router = APIRouter(prefix="/questions", tags=["Questions"])


@router.get("/{question_id}", response_model=QuestionResponse)
async def get_question(question_id: str):
    if (question := client.quiz.questions.find_one({"_id": question_id})) is not None:
        return question

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Question {question_id} not found",
    )
