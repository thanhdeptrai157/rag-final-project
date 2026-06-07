from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User


class UserRepository:
    def __init__(self, db: Session = Depends(get_db)) -> None:
        self.db = db

    def get_by_id(self, user_id: str) -> User | None:
        try:
            parsed_user_id = UUID(str(user_id))
        except ValueError:
            return None

        return self.db.query(User).filter(User.user_id == parsed_user_id).first()

    def get_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email).first()

    def get_by_google_sub(self, google_sub: str) -> User | None:
        return self.db.query(User).filter(User.google_sub == google_sub).first()

    def create(
        self,
        *,
        email: str,
        password_hash: str,
        full_name: str | None = None,
        auth_provider: str = "local",
        google_sub: str | None = None,
        avatar_url: str | None = None,
        role: str = "user",
    ) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            auth_provider=auth_provider,
            google_sub=google_sub,
            avatar_url=avatar_url,
            role=role,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def update(self, user: User, **fields) -> User:
        for key, value in fields.items():
            setattr(user, key, value)
        self.db.commit()
        self.db.refresh(user)
        return user
