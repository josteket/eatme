"""Telegram-бот: запуск Mini App и приём уведомлений."""
from __future__ import annotations

import logging

import socket

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.types import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonDefault,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

from ..config import settings

log = logging.getLogger("eatme.bot")


def _make_session() -> AiohttpSession:
    """Сессия бота: форсим IPv4 (IPv6-ветка к Telegram часто битая) + опц. прокси."""
    proxy = settings.TELEGRAM_PROXY.strip() or None
    session: AiohttpSession
    if proxy:
        try:
            session = AiohttpSession(proxy=proxy)
            log.info("Бот использует прокси: %s", proxy.split("@")[-1])
        except Exception as e:  # noqa: BLE001
            log.warning("Прокси не применён (%s). Установи aiohttp-socks. Работаю без прокси.", e)
            session = AiohttpSession()
    else:
        session = AiohttpSession()
    # заставляем aiohttp ходить только по IPv4
    try:
        session._connector_init["family"] = socket.AF_INET  # noqa: SLF001
    except Exception:  # noqa: BLE001
        pass
    return session


async def setup_menu(bot: Bot, log_success: bool = True) -> None:
    """Настроить постоянную кнопку-меню и список команд.

    Кнопка «Меню» слева от поля ввода всегда открывает актуальный WEBAPP_URL.
    Бросает исключение при сетевой ошибке — вызывающий может повторить.
    """
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Открыть меню"),
            BotCommand(command="menu", description="Кнопка меню"),
            BotCommand(command="id", description="Мой Telegram ID"),
        ])
    except Exception:  # noqa: BLE001
        pass  # команды не критичны

    if settings.is_webapp_public:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="🍽 Меню", web_app=WebAppInfo(url=settings.WEBAPP_URL)
            )
        )
        if log_success:
            log.info("Кнопка-меню Telegram настроена на %s", settings.WEBAPP_URL)
    else:
        await bot.set_chat_menu_button(menu_button=MenuButtonDefault())


def build_bot() -> tuple[Bot, Dispatcher]:
    bot = Bot(token=settings.BOT_TOKEN, session=_make_session())
    dp = Dispatcher()

    def _webapp_kb() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🍽 Открыть меню",
                        web_app=WebAppInfo(url=settings.WEBAPP_URL),
                    )
                ]
            ]
        )

    async def _send_menu(message: Message, greeting: str) -> None:
        """Прислать кнопку меню, либо объяснение, если URL не публичный."""
        if settings.is_webapp_public:
            await message.answer(greeting, reply_markup=_webapp_kb(), parse_mode="HTML")
        else:
            log.warning(
                "Кнопка Mini App не отправлена: WEBAPP_URL=%s не публичный HTTPS",
                settings.WEBAPP_URL,
            )
            await message.answer(
                greeting + "\n\n"
                "⚠️ <b>Приложение пока нельзя открыть.</b>\n"
                f"Сейчас адрес: <code>{settings.WEBAPP_URL}</code> — это не публичный "
                "HTTPS, Telegram не может его открыть.\n\n"
                "Нужно поднять туннель (cloudflared) и вписать его адрес в файл "
                "<code>.env</code> → <code>WEBAPP_URL</code>, затем перезапустить.",
                parse_mode="HTML",
            )

    @dp.message(Command("start"))
    async def start(message: Message) -> None:
        uid = message.from_user.id
        uname = message.from_user.first_name
        log.info("Бот: /start от id=%s (%s)", uid, uname)
        if not settings.is_allowed(uid):
            log.warning("Бот: /start ОТКАЗ — id=%s не в ALLOWED_TELEGRAM_IDS", uid)
            await message.answer(
                "Это семейное приложение. Твой Telegram ID не в списке.\n"
                f"ID: <code>{uid}</code> — добавь его в .env (ALLOWED_TELEGRAM_IDS).",
                parse_mode="HTML",
            )
            return
        name = uname or "друг"
        await _send_menu(
            message,
            f"👋 Привет, {name}!\n\n"
            "Это <b>Freely</b> 🌿 — вкусное питание без глютена и с контролем сахара.\n"
            "Выбирай блюда → собирай план → получай список покупок.",
        )

    @dp.message(Command("menu"))
    async def menu(message: Message) -> None:
        log.info("Бот: /menu от id=%s", message.from_user.id)
        await _send_menu(message, "🍽 Меню:")

    @dp.message(Command("id"))
    async def whoami(message: Message) -> None:
        log.info("Бот: /id от id=%s", message.from_user.id)
        await message.answer(
            f"Твой Telegram ID: <code>{message.from_user.id}</code>",
            parse_mode="HTML",
        )

    @dp.message(Command("help"))
    async def help_cmd(message: Message) -> None:
        log.info("Бот: /help от id=%s", message.from_user.id)
        await message.answer(
            "Команды:\n"
            "/start — открыть приложение\n"
            "/menu — кнопка меню\n"
            "/id — узнать свой Telegram ID\n\n"
            "Внутри: выбираешь блюда, собираешь план еды, "
            "получаешь список покупок. Второй в семье получит уведомление."
        )

    @dp.message()
    async def fallback(message: Message) -> None:
        log.info("Бот: сообщение от id=%s: %r", message.from_user.id,
                 (message.text or "")[:50])
        await message.answer("Напиши /start, чтобы открыть меню.")

    return bot, dp
