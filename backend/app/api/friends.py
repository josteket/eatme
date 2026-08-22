"""Друзья и приглашения по ссылке."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import settings
from ..database import get_db
from ..models import Friendship, User

router = APIRouter()


def ensure_invite_code(db: Session, user: User) -> str:
    if not user.invite_code:
        for _ in range(5):
            code = secrets.token_hex(4)
            if not db.scalar(select(User).where(User.invite_code == code)):
                user.invite_code = code
                db.commit()
                break
    return user.invite_code or ""


def make_friends(db: Session, uid_a: int, uid_b: int) -> bool:
    """Связать двух пользователей дружбой (обе стороны). True — если новая связь."""
    if uid_a == uid_b:
        return False
    created = False
    for a, b in ((uid_a, uid_b), (uid_b, uid_a)):
        exists = db.scalar(
            select(Friendship).where(
                Friendship.user_id == a, Friendship.friend_id == b
            )
        )
        if not exists:
            db.add(Friendship(user_id=a, friend_id=b))
            created = True
    db.commit()
    return created


def _friend_view(u: User) -> dict:
    return {
        "id": u.id,
        "telegram_id": u.telegram_id,
        "name": u.first_name or u.username or "Друг",
        "role": u.role,
    }


def list_friends(db: Session, user_id: int) -> list[dict]:
    rows = db.scalars(
        select(User)
        .join(Friendship, Friendship.friend_id == User.id)
        .where(Friendship.user_id == user_id)
        .order_by(User.first_name)
    ).all()
    return [_friend_view(u) for u in rows]


@router.get("/friends")
def get_friends(db: Session = Depends(get_db), user: User = Depends(current_user)):
    code = ensure_invite_code(db, user)
    link = f"https://t.me/{settings.BOT_USERNAME}?start=inv_{code}"
    return {
        "invite_code": code,
        "invite_link": link,
        "friends": list_friends(db, user.id),
    }


class AcceptInvite(BaseModel):
    code: str


@router.post("/friends/accept")
def accept_invite(
    body: AcceptInvite,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    code = body.code.replace("inv_", "").strip()
    inviter = db.scalar(select(User).where(User.invite_code == code))
    if not inviter:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")
    if inviter.id == user.id:
        raise HTTPException(status_code=400, detail="Нельзя добавить себя")
    make_friends(db, user.id, inviter.id)
    return {"ok": True, "friend": _friend_view(inviter)}


@router.delete("/friends/{friend_id}")
def remove_friend(
    friend_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    for a, b in ((user.id, friend_id), (friend_id, user.id)):
        f = db.scalar(
            select(Friendship).where(
                Friendship.user_id == a, Friendship.friend_id == b
            )
        )
        if f:
            db.delete(f)
    db.commit()
    return {"ok": True}
