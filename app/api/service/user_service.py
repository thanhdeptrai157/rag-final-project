from fastapi import Depends, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.api.repositories.user_repository import UserRepository
from app.core.config import Config
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.user import (
    AuthTokenResponse,
    GoogleLogin,
    RefreshTokenRequest,
    UserCreate,
    UserLogin,
    UserResponse,
)


class UserService:
    def __init__(self, repo: UserRepository = Depends()) -> None:
        self.repo = repo

    def register(self, payload: UserCreate) -> AuthTokenResponse:
        existing = self.repo.get_by_email(payload.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        user = self.repo.create(
            email=payload.email,
            password_hash=hash_password(payload.password),
            full_name=payload.full_name,
        )
        return self._build_auth_response(user)

    def login(self, payload: UserLogin) -> AuthTokenResponse:
        user = self.repo.get_by_email(payload.email)
        if (
            not user
            or not user.is_active
            or not verify_password(payload.password, user.password_hash)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return self._build_auth_response(user)

    def login_with_google(self, payload: GoogleLogin) -> AuthTokenResponse:
        google_payload = self._verify_google_id_token(payload.id_token)
        google_sub = str(google_payload["sub"])
        email = str(google_payload["email"]).strip().lower()
        full_name = google_payload.get("name")
        avatar_url = google_payload.get("picture")

        user = self.repo.get_by_google_sub(google_sub)
        if user:
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User account is inactive",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            user = self.repo.update(
                user,
                email=email,
                full_name=full_name or user.full_name,
                avatar_url=avatar_url or user.avatar_url,
            )
            return self._build_auth_response(user)

        user = self.repo.get_by_email(email)
        if user:
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User account is inactive",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            user = self.repo.update(
                user,
                auth_provider="google",
                google_sub=google_sub,
                full_name=full_name or user.full_name,
                avatar_url=avatar_url or user.avatar_url,
            )
            return self._build_auth_response(user)

        user = self.repo.create(
            email=email,
            password_hash=hash_password(f"google:{google_sub}"),
            full_name=str(full_name) if full_name else None,
            auth_provider="google",
            google_sub=google_sub,
            avatar_url=str(avatar_url) if avatar_url else None,
        )
        return self._build_auth_response(user)

    def get_by_id(self, user_id: str) -> User | None:
        return self.repo.get_by_id(user_id)

    def refresh_token(self, payload: RefreshTokenRequest) -> AuthTokenResponse:
        token_payload = decode_refresh_token(payload.refresh_token)
        if not token_payload or not token_payload.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = self.repo.get_by_id(str(token_payload["sub"]))
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return self._build_auth_response(user)

    def _verify_google_id_token(self, token: str) -> dict:
        if not Config.GOOGLE_CLIENT_ID:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GOOGLE_CLIENT_ID is not configured",
            )

        try:
            payload = google_id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                Config.GOOGLE_CLIENT_ID,
            )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Google token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not payload.get("sub") or not payload.get("email"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google token is missing required identity fields",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if payload.get("email_verified") is not True:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google email is not verified",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return payload

    def _build_auth_response(self, user: User) -> AuthTokenResponse:
        access_token = create_access_token(
            subject=str(user.user_id),
            claims={"email": user.email, "role": user.role},
        )
        refresh_token = create_refresh_token(
            subject=str(user.user_id),
            claims={"email": user.email, "role": user.role},
        )
        return AuthTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserResponse.model_validate(user),
        )
