from fastapi import Depends, HTTPException, status, Request
from .jwt import verify_token
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ...db.main import get_session  # your async session dep
from ...db.models import User

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_session),
) -> User:
    token = credentials.credentials

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    payload = await verify_token(token)

    email: str = payload.get("sub") or payload.get("email", "")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    return user

from ...db.models import Subscription
from sqlmodel import select, Session
from ...db.main import engine
from datetime import datetime


def require_active_subscription(user):
    with Session(engine) as session:
        sub = session.exec(
            select(Subscription).where(
                Subscription.user_id == user.id,
                Subscription.is_active == True,
                Subscription.end_date > datetime.now(datetime.timezone.utc)
            )
        ).first()

        if not sub:
            raise HTTPException(403, "Subscription required")

        return sub