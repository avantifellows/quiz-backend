from fastapi import APIRouter, status, HTTPException
from database import client
from models import Organization
from fastapi.responses import JSONResponse
import string
import random

router = APIRouter()


@router.post("/create-org/{org_name}")
async def create_organization(org_name: str):
    if org_name is not None:
        # create an API key
        char_set = string.ascii_letters + string.punctuation
        urand = random.SystemRandom()
        org_key = "".join([urand.choice(char_set) for _ in range(20)])

        org_data = {"org_name": org_name, "org_key": org_key}
        client.quiz.organization.insert_one(org_data)
        return JSONResponse(status_code=status.HTTP_201_CREATED, content=org_name)


@router.get("/check-auth-token/{api_key}", response_model=Organization)
async def check_auth_token(api_key: str):

    if (
        org := client.quiz.organization.find_one(
            {"org_key": api_key},
            {
                "org_name": 1,
            },
        )
    ) is not None:
        return org

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"org with key {api_key} not found",
    )
