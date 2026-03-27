import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..services.dependency import get_current_user
from ..services.jwt import create_access_token, create_refresh_token, verify_token
from ..services.utils import hash_password, verify_password
from ...db.main import get_session as get_db
from ...db.models import User
from ..schemas import (
    LogIn,
    PasswordChangeRequest,
    TelegramLinkRequest,
    Token,
    UserOut,
    UserRegister,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    body: UserRegister,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    # ✅ Fixed: was `user.email == User.email` (always True — compares column to column)
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = User(
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(f"New user registered: {user.email}")
    return user


@router.post("/login", response_model=Token, status_code=status.HTTP_200_OK)
async def login(
    response: Response,
    body: LogIn,
    db: AsyncSession = Depends(get_db),
) -> Token:
    # ✅ Fixed: was `user.email == User.email` (column == column — always True)
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    # Update last_seen
    user.last_seen = datetime.now(timezone.utc)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token_data = {
        # ✅ use "sub" as the standard JWT claim — dependency.py reads this
        "sub": user.email,
        "uid": jsonable_encoder(user.id),
        "username": user.username,
        "role": user.tier.value,
    }

    access = await create_access_token(token_data)
    refresh = await create_refresh_token(token_data)

    # Set refresh token as HttpOnly cookie
    response.set_cookie(
        key="refresh",
        value=refresh,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )

    # ✅ Don't put access token in response header — body is enough and standard
    return Token(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=Token, status_code=status.HTTP_200_OK)
async def refresh_token(
    response: Response,
    db: AsyncSession = Depends(get_db),
    # Read refresh token from cookie
    refresh: str = None,
) -> Token:
    from fastapi import Request

    if not refresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )

    payload = verify_token(refresh)
    email: str = payload.get("sub", "")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    token_data = {
        "sub": user.email,
        "uid": jsonable_encoder(user.id),
        "username": user.username,
        "role": user.tier.value,
    }

    new_access = await create_access_token(token_data)
    new_refresh = await create_refresh_token(token_data)

    response.set_cookie(
        key="refresh",
        value=new_refresh,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )

    return Token(access_token=new_access, refresh_token=new_refresh)


@router.get("/me", response_model=UserOut, status_code=status.HTTP_200_OK)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return current_user


@router.post("/link-telegram", response_model=UserOut)
async def link_telegram(
    body: TelegramLinkRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    user.tg_chat_id = body.tg_chat_id
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChangeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    user.hashed_password = hash_password(body.new_password)
    db.add(user)
    await db.commit()


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    # Clear the refresh cookie — client drops the access token
    response.delete_cookie(key="refresh", httponly=True, secure=True)


@router.post("/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_account(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    user.is_active = False
    db.add(user)
    await db.commit()