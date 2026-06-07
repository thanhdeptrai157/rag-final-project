from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.service.user_service import UserService
from app.core.security import decode_access_token
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    service: UserService = Depends(),
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    payload = decode_access_token(credentials.credentials)
    if not payload or not payload.get("sub"):
        raise _unauthorized()

    user = service.get_by_id(str(payload["sub"]))
    if not user or not user.is_active:
        raise _unauthorized()

    return user


def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return current_user


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
