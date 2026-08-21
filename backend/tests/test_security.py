"""Безопасность: проверка подписи Telegram initData и контроль доступа."""
import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest

from app import auth
from app.config import settings

TEST_TOKEN = "123456:TESTTOKENFORUNITTESTS"


def make_init_data(token: str, user: dict, tamper: bool = False) -> str:
    fields = {"auth_date": "1700000000", "user": json.dumps(user)}
    dcs = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    fields["hash"] = h
    if tamper:
        # подменяем пользователя ПОСЛЕ подписи — подпись должна перестать сходиться
        fields["user"] = json.dumps({**user, "id": user["id"] + 1})
    return urlencode(fields)


def test_valid_signature_passes(monkeypatch):
    monkeypatch.setattr(settings, "BOT_TOKEN", TEST_TOKEN)
    init = make_init_data(TEST_TOKEN, {"id": 674280065, "first_name": "Тест"})
    parsed = auth._check_signature(init)
    assert parsed is not None
    assert json.loads(parsed["user"])["id"] == 674280065


def test_tampered_signature_rejected(monkeypatch):
    monkeypatch.setattr(settings, "BOT_TOKEN", TEST_TOKEN)
    init = make_init_data(TEST_TOKEN, {"id": 674280065, "first_name": "Тест"}, tamper=True)
    assert auth._check_signature(init) is None


def test_wrong_token_rejected(monkeypatch):
    monkeypatch.setattr(settings, "BOT_TOKEN", "999999:OTHERTOKEN")
    init = make_init_data(TEST_TOKEN, {"id": 1, "first_name": "X"})
    assert auth._check_signature(init) is None


def test_empty_init_data():
    assert auth._check_signature("") is None
    assert auth._check_signature("garbage-no-hash") is None


def test_allowed_user_gets_access(client, monkeypatch):
    monkeypatch.setattr(settings, "BOT_TOKEN", TEST_TOKEN)
    monkeypatch.setattr(settings, "ALLOWED_TELEGRAM_IDS", "674280065,844197375")
    monkeypatch.setattr(settings, "DEV_MODE", False)
    init = make_init_data(TEST_TOKEN, {"id": 674280065, "first_name": "Муж"})
    resp = client.get("/api/me", headers={"X-Telegram-Init-Data": init})
    assert resp.status_code == 200
    assert resp.json()["telegram_id"] == 674280065


def test_stranger_allowed_as_user(client, monkeypatch):
    # Приложение публичное: любой пользователь с валидной подписью — обычный user
    monkeypatch.setattr(settings, "BOT_TOKEN", TEST_TOKEN)
    monkeypatch.setattr(settings, "ALLOWED_TELEGRAM_IDS", "674280065,844197375")
    monkeypatch.setattr(settings, "DEV_MODE", False)
    init = make_init_data(TEST_TOKEN, {"id": 555000111, "first_name": "Гость"})
    resp = client.get("/api/me", headers={"X-Telegram-Init-Data": init})
    assert resp.status_code == 200
    assert resp.json()["role"] == "user"


def test_profile_update(client):
    r = client.patch("/api/profile", json={"profile_type": "pregnant"}).json()
    assert r["profile_type"] == "pregnant"
    assert client.get("/api/me").json()["profile_type"] == "pregnant"
    bad = client.patch("/api/profile", json={"profile_type": "nonsense"})
    assert bad.status_code == 400


def test_no_auth_without_dev_mode(client, monkeypatch):
    monkeypatch.setattr(settings, "DEV_MODE", False)
    monkeypatch.setattr(settings, "ALLOWED_TELEGRAM_IDS", "674280065")
    resp = client.get("/api/me")  # без initData и без DEV
    assert resp.status_code == 401


def test_wife_role_assigned(client, monkeypatch):
    monkeypatch.setattr(settings, "BOT_TOKEN", TEST_TOKEN)
    monkeypatch.setattr(settings, "ALLOWED_TELEGRAM_IDS", "674280065,844197375")
    monkeypatch.setattr(settings, "WIFE_TELEGRAM_ID", "844197375")
    monkeypatch.setattr(settings, "DEV_MODE", False)
    init = make_init_data(TEST_TOKEN, {"id": 844197375, "first_name": "Жена"})
    resp = client.get("/api/me", headers={"X-Telegram-Init-Data": init})
    assert resp.json()["role"] == "wife"
