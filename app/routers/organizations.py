from fastapi import APIRouter, status, HTTPException
from database import client
from models import Organization

router = APIRouter()


@router.get("/check-auth-token/{api_key}", response_model=Organization)
async def check_auth_token(api_key: str):

    if (
        org := client.quiz.organization.find_one({"org_key": api_key}, {"org_name": 1})
    ) is not None:
        return org

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"org with key {api_key} not found",
    )
