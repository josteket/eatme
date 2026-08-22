"""Кланы — именованные группы друзей. Тэгаешь клан → в заказ попадают все его
участники сразу. Участниками могут быть только друзья владельца.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user
from ..database import get_db
from ..models import Clan, ClanMember, Friendship, User

router = APIRouter()

MAX_NAME = 64


def _friend_ids(db: Session, user_id: int) -> set[int]:
    return set(
        db.scalars(
            select(Friendship.friend_id).where(Friendship.user_id == user_id)
        ).all()
    )


def _clan_view(db: Session, clan: Clan) -> dict:
    member_ids = [m.user_id for m in clan.members]
    users = (
        db.scalars(select(User).where(User.id.in_(member_ids))).all()
        if member_ids
        else []
    )
    return {
        "id": clan.id,
        "name": clan.name,
        "member_ids": member_ids,
        "members": [
            {"id": u.id, "name": u.first_name or u.username or "Друг", "role": u.role}
            for u in users
        ],
    }


@router.get("/clans")
def list_clans(db: Session = Depends(get_db), user: User = Depends(current_user)):
    clans = db.scalars(
        select(Clan)
        .options(selectinload(Clan.members))
        .where(Clan.owner_id == user.id)
        .order_by(Clan.created_at)
    ).all()
    return [_clan_view(db, c) for c in clans]


class ClanCreate(BaseModel):
    name: str
    member_ids: list[int] = []


@router.post("/clans")
def create_clan(
    body: ClanCreate, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    name = (body.name or "").strip()[:MAX_NAME]
    if not name:
        raise HTTPException(status_code=400, detail="Введите название клана")
    friends = _friend_ids(db, user.id)
    clan = Clan(owner_id=user.id, name=name)
    db.add(clan)
    db.flush()
    for fid in set(body.member_ids):
        if fid in friends:
            db.add(ClanMember(clan_id=clan.id, user_id=fid))
    db.commit()
    db.refresh(clan)
    return _clan_view(db, clan)


class ClanUpdate(BaseModel):
    name: str | None = None
    member_ids: list[int] | None = None


@router.patch("/clans/{clan_id}")
def update_clan(
    clan_id: int,
    body: ClanUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    clan = db.scalar(
        select(Clan).options(selectinload(Clan.members)).where(Clan.id == clan_id)
    )
    if not clan or clan.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Клан не найден")
    if body.name is not None:
        name = body.name.strip()[:MAX_NAME]
        if name:
            clan.name = name
    if body.member_ids is not None:
        friends = _friend_ids(db, user.id)
        for m in list(clan.members):
            db.delete(m)
        db.flush()
        for fid in set(body.member_ids):
            if fid in friends:
                db.add(ClanMember(clan_id=clan.id, user_id=fid))
    db.commit()
    db.refresh(clan)
    return _clan_view(db, clan)


@router.delete("/clans/{clan_id}")
def delete_clan(
    clan_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    clan = db.get(Clan, clan_id)
    if clan and clan.owner_id == user.id:
        for m in db.scalars(
            select(ClanMember).where(ClanMember.clan_id == clan.id)
        ).all():
            db.delete(m)
        db.delete(clan)
        db.commit()
    return {"ok": True}
