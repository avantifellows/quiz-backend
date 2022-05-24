from fastapi import APIRouter, status, HTTPException
from app.settings import Settings
from database import client
from models import Organization, OrganizationResponse
import secrets
import string
from fastapi.encoders import jsonable_encoder

router = APIRouter(prefix="/organizations", tags=["Organizations"])
settings = Settings()


def generate_random_string():
    return "".join(
        [
            secrets.choice(string.ascii_letters + string.digits)
            for _ in range(settings.random_string_length)
        ]
    )


@router.post("/", response_model=OrganizationResponse)
async def create_organization(organization: Organization):
    organization = jsonable_encoder(organization)
    number_of_loops = 3

    while number_of_loops > 0:

        # create an API key
        key = generate_random_string()

        # check if API key exists
        if (client.quiz.organization.find_one({"key": key})) is None:
            organization["key"] = key
            new_organization = client.quiz.organization.insert_one(organization)
            created_organization = client.quiz.organization.find_one(
                {"_id": new_organization.inserted_id}
            )
            return created_organization

        number_of_loops -= 1


@router.get("/authenticate/{api_key}", response_model=OrganizationResponse)
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
