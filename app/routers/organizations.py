from fastapi import APIRouter, status, HTTPException
from fastapi.responses import JSONResponse
from settings import Settings
from database import get_quiz_db
from models import Organization, OrganizationResponse
import secrets
import string
from fastapi.encoders import jsonable_encoder
from logger_config import get_logger
from cache import cache_get, cache_set, cache_key

router = APIRouter(prefix="/organizations", tags=["Organizations"])
settings = Settings()
logger = get_logger()


def generate_random_string(length: int = settings.api_key_length):
    return "".join(
        [secrets.choice(string.ascii_letters + string.digits) for _ in range(length)]
    )


@router.post("/", response_model=OrganizationResponse)
async def create_organization(organization: Organization):
    logger.info("Creating new organization")
    organization = jsonable_encoder(organization)

    # create an API key
    key = generate_random_string()
    logger.info(f"Generated API key: {key}")

    # check if API key exists
    db = get_quiz_db()
    if (await db.organization.find_one({"key": key})) is None:
        organization["key"] = key
        new_organization = await db.organization.insert_one(organization)
        if new_organization.acknowledged:
            logger.info(f"Inserted new organization with API key: {key}")
        else:
            logger.error("Failed to insert new organization")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to insert new organization",
            )
        created_organization = await db.organization.find_one(
            {"_id": new_organization.inserted_id}
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=created_organization,
        )

    logger.error(f"API key collision occurred for key: {key}")
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"API key {key} already exists",
    )


@router.get("/authenticate/{api_key}", response_model=OrganizationResponse)
async def check_auth_token(api_key: str):
    logger.info(f"Authenticating API key: {api_key}")

    key = cache_key("org", "key", api_key)
    org = await cache_get(key)
    if org is None:
        db = get_quiz_db()
        org = await db.organization.find_one({"key": api_key})
        if org is None:
            logger.error(f"Failed to authenticate API key: {api_key}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="organization not found",
            )
        await cache_set(key, org, ttl_seconds=300)

    logger.info(f"Authenticated API key: {api_key}")
    return org
