from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import normalize_role
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User


async def register_user(db: AsyncSession, email: str, password: str, role: str = "Viewer") -> User:
    user = User(
        email=email,
        hashed_password=hash_password(password),
        role=normalize_role(role),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> str | None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return create_access_token(subject=user.email, role=user.role)
