from fastapi import APIRouter, HTTPException

from  models.auth_models import (
    RegisterRequest,
    LoginRequest
)

from  database_service.user_repository import (
    create_user,
    find_user_by_email
)

from  database_service.authentication.password_utils import (
    hash_password,
    verify_password
)

from  database_service.authentication.auth import (
    create_access_token
)

from  database_service.session_sync import (
    load_session_from_database
)

from  session_service.current_session import current_session

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


@router.post("/register")
async def register(
    request: RegisterRequest
):

    existing = await find_user_by_email(
        request.email
    )

    if existing:

        raise HTTPException(
            status_code=409,
            detail="User already exists."
        )

    document = {

        "email": request.email,

        "password_hash": hash_password(
            request.password
        ),

        "refresh_tokens": [],

        "session": {

            "jd_name": "",

            "skills": [],

            "results": [],

            "processed_files": []

        }

    }

    await create_user(document)

    return {

        "message": "Registration successful."

    }


@router.post("/login")
async def login(
    request: LoginRequest
):

    user = await find_user_by_email(
        request.email
    )

    if not user:

        raise HTTPException(
            status_code=401,
            detail="Invalid credentials."
        )

    if not verify_password(
        request.password,
        user["password_hash"]
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid credentials."
        )

    current_session.email = user["email"]

    await load_session_from_database(
        user["email"]
    )

    token = create_access_token(
        str(user["_id"]),
        user["email"]
    )

    return {

        "access_token": token,

        "token_type": "bearer",

        "user": {

            "email": user["email"]

        }

    }


@router.post("/logout")
async def logout():

    current_session.email = ""

    current_session.jd_name = ""

    current_session.skills.clear()

    current_session.results.clear()

    current_session.processed_files.clear()

    current_session.status.processed = 0

    current_session.status.total = 0

    return {

        "message": "Logged out."

    }