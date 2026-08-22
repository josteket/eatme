"""Единый формат времени для API.

Все временные метки хранятся в UTC (Render работает в UTC, func.now() — UTC).
Отдаём ISO с суффиксом 'Z', чтобы клиент (JS) показал их в часовом поясе
устройства пользователя — «как на телефоне».
"""
from __future__ import annotations

from datetime import datetime


def iso_utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    # значение наивное и по факту в UTC → помечаем 'Z'
    if dt.tzinfo is not None:
        return dt.isoformat()
    return dt.replace(microsecond=0).isoformat() + "Z"
