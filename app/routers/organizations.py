from fastapi import APIRouter, status, HTTPException
from database import client
from models import Organization, OrganizationResponse
from fastapi.responses import JSONResponse
import secrets
import string
from fastapi.encoders import jsonable_encoder

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.post("/", response_model=OrganizationResponse, response_model_exclude={"key"})
async def create_organization(org: Organization):
    org = jsonable_encoder(org)
    if org["name"] is not None:
        # create an API key
        key = "".join(
            [secrets.choice(string.ascii_letters + string.digits) for _ in range(20)]
        )
        number_of_loops = 3
        while number_of_loops > 0:
            # check if API key exists
            if (client.quiz.organization.find_one({"key": key})) is None:
                org["key"] = key
                new_org = client.quiz.organization.insert_one(org)
                created_org = client.quiz.organization.find_one(
                    {"_id": new_org.inserted_id}
                )
                return JSONResponse(
                    status_code=status.HTTP_201_CREATED, content=created_org
                )

            else:
                key = "".join(
                    [
                        secrets.choice(string.ascii_letters + string.digits)
                        for _ in range(20)
                    ]
                )
                number_of_loops -= 1

        raise HTTPException(
            status_code=500,
            detail="Duplicate API key. Please try again.",
        )


@router.get("/authenticate/{api_key}", response_model=Organization)
async def check_auth_token(api_key: str):

    if (
        org := client.quiz.organization.find_one(
            {"key": api_key},
        )
    ) is not None:
        return org

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"org with key {api_key} not found",
    )
