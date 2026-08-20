"""Генерация фотографий блюд через Pollinations (бесплатно, без ключей).

Картинки создаются нейросетью по описанию блюда -> нет проблем с авторскими
правами, каждое фото релевантно своему блюду. Сохраняются в frontend/images/<slug>.jpg.

Запуск:  python gen_images.py            # все недостающие
         python gen_images.py --force    # перегенерировать все

Уже существующие файлы пропускаются, поэтому скрипт можно перезапускать.
"""
from __future__ import annotations

import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from app.seed.image_prompts import PROMPTS  # noqa: E402
from app.seed.recipes_data import RECIPES  # noqa: E402
from app.seed.recipes_extra import RECIPES_EXTRA  # noqa: E402
from app.seed.recipes_extra2 import RECIPES_EXTRA2  # noqa: E402

IMAGES_DIR = ROOT / "frontend" / "images"
TEMPLATE = (
    "professional food photography of {subject}, on a plate, top view, "
    "soft natural light, appetizing, shallow depth of field, high detail, "
    "no text, no watermark"
)


def all_slugs() -> list[tuple[str, str]]:
    """Список (slug, subject) для всех рецептов."""
    out = []
    for r in RECIPES + RECIPES_EXTRA + RECIPES_EXTRA2:
        slug = r["slug"]
        subject = PROMPTS.get(slug) or r["name"]
        out.append((slug, subject))
    return out


def seed_for(slug: str) -> int:
    h = 2166136261
    for ch in slug:
        h = (h ^ ord(ch)) * 16777619 & 0xFFFFFFFF
    return h % 100000


def fetch(subject: str, slug: str, dest: Path, attempts: int = 5) -> bool:
    prompt = TEMPLATE.format(subject=subject)
    enc = urllib.parse.quote(prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{enc}"
        f"?width=600&height=600&nologo=true&seed={seed_for(slug)}"
    )
    for i in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "eatme/1.0"})
            with urllib.request.urlopen(req, timeout=150) as resp:
                data = resp.read()
            if len(data) > 3000 and data[:2] == b"\xff\xd8":  # валидный JPEG
                dest.write_bytes(data)
                return True
            print(f"    {slug} попытка {i}: невалидный ответ ({len(data)} б)", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"    {slug} попытка {i}: {e}", flush=True)
        time.sleep(min(5 * i, 25))  # экспоненциальная пауза при rate-limit
    return False


def main() -> None:
    # Последовательно: Pollinations на бесплатном тарифе жёстко лимитит
    # параллельные запросы (HTTP 429), поэтому строго по одному.
    force = "--force" in sys.argv
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    items = all_slugs()
    total = len(items)
    ok = skipped = failed = 0

    for n, (slug, subject) in enumerate(items, 1):
        dest = IMAGES_DIR / f"{slug}.jpg"
        if dest.exists() and not force:
            skipped += 1
            print(f"[{n}/{total}] {slug}: skip", flush=True)
            continue
        got = fetch(subject, slug, dest)
        if got:
            ok += 1
            print(f"[{n}/{total}] {slug}: OK", flush=True)
        else:
            failed += 1
            print(f"[{n}/{total}] {slug}: FAIL", flush=True)
        time.sleep(2)  # пауза, чтобы не ловить rate-limit

    print(
        f"\nГотово. Сгенерировано: {ok}, пропущено(уже есть): {skipped}, "
        f"ошибок: {failed}, всего блюд: {total}",
        flush=True,
    )
    if failed:
        print("Часть не скачалась — запусти 'python gen_images.py' ещё раз.", flush=True)


if __name__ == "__main__":
    main()
