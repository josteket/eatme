"""Конфигурация приложения (читается из .env в корне проекта)."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Корень проекта = .../EATME
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str = ""
    WEBAPP_URL: str = "https://localhost"
    ALLOWED_TELEGRAM_IDS: str = ""
    WIFE_TELEGRAM_ID: str = ""
    # Прокси для бота, если провайдер блокирует api.telegram.org.
    # Примеры: socks5://127.0.0.1:1080  или  http://user:pass@host:port
    TELEGRAM_PROXY: str = ""

    HOST: str = "0.0.0.0"
    PORT: int = 8080
    SECRET_KEY: str = "change-me"
    DATABASE_URL: str = "sqlite:///./eatme.db"
    DEV_MODE: bool = True

    # ==== Облако (Render и т.п.) ====
    # true → бот работает через webhook, без туннеля и polling.
    USE_WEBHOOK: bool = False
    # Постоянный публичный адрес сервиса. Render подставляет RENDER_EXTERNAL_URL сам.
    PUBLIC_URL: str = ""
    RENDER_EXTERNAL_URL: str = ""

    @property
    def allowed_ids(self) -> list[int]:
        out: list[int] = []
        for part in self.ALLOWED_TELEGRAM_IDS.split(","):
            part = part.strip()
            if part.isdigit():
                out.append(int(part))
        return out

    @property
    def wife_id(self) -> int | None:
        v = self.WIFE_TELEGRAM_ID.strip()
        return int(v) if v.isdigit() else None

    def role_for(self, telegram_id: int) -> str:
        if self.wife_id is not None and telegram_id == self.wife_id:
            return "wife"
        if telegram_id in self.allowed_ids:
            return "husband"
        return "user"

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.allowed_ids

    def is_allowed(self, telegram_id: int) -> bool:
        # Публичное приложение — пускаем любого пользователя Telegram.
        return True

    @property
    def is_webapp_public(self) -> bool:
        """URL пригоден для Telegram Mini App (публичный HTTPS, не localhost)."""
        u = self.WEBAPP_URL.strip().lower()
        if not u.startswith("https://"):
            return False
        bad = ("localhost", "127.0.0.1", "0.0.0.0", "://192.168.", "://10.", "://172.")
        return not any(b in u for b in bad)

    @property
    def token_masked(self) -> str:
        t = self.BOT_TOKEN.strip()
        if not t or ":" not in t:
            return "(не задан)"
        head, tail = t.split(":", 1)
        return f"{head}:{tail[:4]}…{tail[-3:]}"

    @property
    def token_ok(self) -> bool:
        t = self.BOT_TOKEN.strip()
        return bool(t) and "PUT_YOUR_TOKEN" not in t

    @property
    def public_base_url(self) -> str:
        return (self.PUBLIC_URL or self.RENDER_EXTERNAL_URL or "").rstrip("/")

    @property
    def use_webhook(self) -> bool:
        return self.USE_WEBHOOK and self.token_ok and bool(self.public_base_url)

    @property
    def webhook_secret(self) -> str:
        import hashlib

        raw = ("eatme-wh" + self.SECRET_KEY + self.BOT_TOKEN).encode()
        return hashlib.sha256(raw).hexdigest()[:40]


settings = Settings()
