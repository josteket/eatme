"""Проверка Telegram WebApp initData и получение текущего пользователя.

Безопасность: доверяем только подписанным Telegram данным. В DEV_MODE
разрешаем вход без initData (как первый разрешённый пользователь) для теста
из браузера.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

log = logging.getLogger("eatme.auth")


def _check_signature(init_data: str) -> dict | None:
    """Вернуть распарсенные поля, если подпись верна, иначе None."""
    if not init_data or not settings.BOT_TOKEN:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    except ValueError:
        return None

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(
        f"{k}={pairs[k]}" for k in sorted(pairs.keys())
    )
    secret_key = hmac.new(
        b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256
    ).digest()
    calc_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calc_hash, received_hash):
        return None
    return pairs


def _get_or_create_user(db: Session, tg_id: int, username: str | None,
                        first_name: str | None) -> User:
    user = db.scalar(select(User).where(User.telegram_id == tg_id))
    role = settings.role_for(tg_id)
    if user is None:
        user = User(
            telegram_id=tg_id,
            username=username,
            first_name=first_name,
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # держим роль/имя актуальными
        changed = False
        if user.role != role:
            user.role = role
            changed = True
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if changed:
            db.commit()
    return user


def current_user(
    x_telegram_init_data: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    pairs = _check_signature(x_telegram_init_data or "")

    if pairs is not None:
        user_raw = pairs.get("user")
        if not user_raw:
            log.warning("Auth: подпись верна, но нет поля user в initData")
            raise HTTPException(status_code=401, detail="Нет данных пользователя")
        info = json.loads(user_raw)
        tg_id = int(info["id"])
        if not settings.is_allowed(tg_id):
            log.warning("Auth: ОТКАЗ — id=%s (%s) не в списке разрешённых",
                        tg_id, info.get("first_name"))
            raise HTTPException(status_code=403, detail="Доступ только для членов семьи")
        log.info("Auth: ✅ Telegram id=%s (%s), роль=%s",
                 tg_id, info.get("first_name"), settings.role_for(tg_id))
        return _get_or_create_user(
            db, tg_id, info.get("username"), info.get("first_name")
        )

    if x_telegram_init_data:
        log.warning("Auth: initData передан, но ПОДПИСЬ НЕ СОШЛАСЬ "
                    "(неверный BOT_TOKEN или испорченные данные)")

    # DEV-режим: пускаем без Telegram
    if settings.DEV_MODE:
        dev_id = settings.allowed_ids[0] if settings.allowed_ids else 1
        log.info("Auth: DEV-вход без Telegram как id=%s", dev_id)
        return _get_or_create_user(db, dev_id, "dev", "Тест")

    log.warning("Auth: ОТКАЗ — нет валидного initData и DEV_MODE выключен")
    raise HTTPException(status_code=401, detail="Откройте приложение через Telegram")
