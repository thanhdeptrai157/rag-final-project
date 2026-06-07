from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_current_user
from app.api.service.user_service import UserService
from app.models.user import User
from app.schemas.user import (
    AuthTokenResponse,
    GoogleLogin,
    RefreshTokenRequest,
    UserCreate,
    UserLogin,
    UserResponse,
)

auth_router = APIRouter()


@auth_router.post(
    "/register",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: UserCreate,
    service: UserService = Depends(),
) -> AuthTokenResponse:
    return service.register(payload)


@auth_router.post("/login", response_model=AuthTokenResponse)
def login(
    payload: UserLogin,
    service: UserService = Depends(),
) -> AuthTokenResponse:
    return service.login(payload)


@auth_router.post("/google", response_model=AuthTokenResponse)
def login_with_google(
    payload: GoogleLogin,
    service: UserService = Depends(),
) -> AuthTokenResponse:
    return service.login_with_google(payload)


@auth_router.post("/refresh", response_model=AuthTokenResponse)
def refresh_token(
    payload: RefreshTokenRequest,
    service: UserService = Depends(),
) -> AuthTokenResponse:
    return service.refresh_token(payload)


@auth_router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)
