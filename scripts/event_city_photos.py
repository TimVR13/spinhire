#!/usr/bin/env python3
"""Фирменные фото городов для обложек событий — Vertex AI (gemini-2.5-flash-image).

Обложка события на SpinHire — фото города под крупным текстом (как афиши у TheGamblest).
Скрипт берёт города из таблицы events (или из JSON) и генерирует по одному фото на город
в img/events/city/<город>.jpg (16:9, ~1600 px). Уже существующие пропускает; запасные
картинки из Википедии (их докачивает краулер, отметка в data/events-crawler.json)
заменяет фирменными при --replace-wiki.

    python3 scripts/event_city_photos.py                 # города всех активных событий из базы
    python3 scripts/event_city_photos.py --cities "Lisbon, Portugal" "Tbilisi, Georgia"
    python3 scripts/event_city_photos.py --from-json events.json   # [{"city":..,"country":..}, …]
    python3 scripts/event_city_photos.py --replace-wiki  # заменить википедийные запаски

Ключ Vertex — как у scripts/gen_images.py (VERTEX_SA или ~/Desktop/planner/.data/vertex-sa.json).
После генерации перепеките OG-карточки: python3 -m server.events_crawler --force --no-translate
(или дождитесь прогона воркера — он обновит og-картинки на изменившихся страницах).
"""
import argparse
import base64
import json
import os
import sqlite3
import sys
import time
from io import BytesIO

import requests
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import gen_images as g  # noqa: E402  (token(), PROJECT, LOCATION, MODEL)
from server import events_crawler as ec  # noqa: E402

STYLE = ("Photorealistic wide cinematic photograph of {city}, {country}: the city skyline with its most recognisable "
         "landmark, shot at golden hour turning to dusk, slightly moody teal-and-magenta tones, high detail, "
         "full-frame camera, 35mm lens, no people in the foreground, no text, no letters, no logos, no watermark.")
SOFT = ("Photorealistic aerial photograph of {city}, {country} at dusk, city lights, cinematic colours, "
        "no text, no watermark.")


PROMPTS = (
    STYLE,
    SOFT,
    "Travel photograph of the historic centre of {city}, {country}: streets, architecture and sky at golden hour, "
    "cinematic colours, no people in focus, no text, no watermark.",
    "Wide landscape photograph of the skyline of a large city at dusk with warm city lights and a teal sky, "
    "cinematic, no text, no watermark.",
)


def gen(city: str, country: str, aspect: str = "16:9") -> bytes:
    """Несколько формулировок подряд: фильтр безопасности иногда режет сам запрос по названию города."""
    url = (f"https://aiplatform.googleapis.com/v1/projects/{g.PROJECT}/locations/{g.LOCATION}"
           f"/publishers/google/models/{g.MODEL}:generateContent")
    for template in PROMPTS:
        prompt = template.format(city=city, country=country or "")
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}}}
        for attempt in range(3):
            r = requests.post(url, headers={"Authorization": "Bearer " + g.token()}, json=body, timeout=120)
            if r.status_code == 429:
                time.sleep(15 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            if "candidates" not in data:
                print("  blocked:", data.get("promptFeedback", {}).get("blockReason"), "→ другая формулировка", file=sys.stderr)
                break
            parts = data["candidates"][0]["content"].get("parts") or []
            for part in parts:
                if "inlineData" in part:
                    return base64.b64decode(part["inlineData"]["data"])
            break
    raise RuntimeError("no image for " + city)


def cities_from_db() -> list[tuple[str, str]]:
    db = sqlite3.connect(os.path.join(ROOT, "data", "spinhire.db"))
    rows = db.execute("select distinct city_en, country_en from events where active = 1 and city_en != ''").fetchall()
    db.close()
    return [(c, k) for c, k in rows]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cities", nargs="*", help='"City, Country" …')
    parser.add_argument("--from-json", help="файл со списком {city, country}")
    parser.add_argument("--replace-wiki", action="store_true", help="заменить запасные фото из Википедии")
    parser.add_argument("--force", action="store_true", help="перегенерировать даже существующие")
    parser.add_argument("--pause", type=float, default=6.0)
    args = parser.parse_args()
    if args.cities:
        pairs = [tuple(p.strip() for p in c.split(",", 1)) if "," in c else (c.strip(), "") for c in args.cities]
    elif args.from_json:
        rows = json.load(open(args.from_json, encoding="utf-8"))
        pairs = sorted({(r.get("city") or "", r.get("country") or "") for r in rows if r.get("city")})
    else:
        pairs = cities_from_db()
    status = ec.load_status()
    credits = status.setdefault("city_photos", {})
    os.makedirs(ec.CITY_DIR, exist_ok=True)
    done = 0
    for city, country in pairs:
        city = ec.clean_city(city, country)
        if not city or city.lower() == "online":
            continue
        path = ec.city_photo_path(city)
        key = os.path.basename(path)
        is_wiki = credits.get(key, {}).get("source") == "wikipedia"
        if os.path.exists(path) and not args.force and not (args.replace_wiki and is_wiki):
            print("skip", key)
            continue
        try:
            data = gen(city, country)
        except Exception as exc:  # noqa: BLE001
            print("FAIL", key, str(exc)[:120], file=sys.stderr)
            continue
        im = Image.open(BytesIO(data)).convert("RGB")
        im.thumbnail((1600, 1600))
        im.save(path, "JPEG", quality=85, optimize=True, progressive=True)
        credits[key] = {"source": "vertex", "city": city, "country": country, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        ec.save_status(status)
        done += 1
        print("ok", key, im.size, flush=True)
        time.sleep(args.pause)
    print(f"готово: {done} новых фото, всего городов {len(pairs)}")


if __name__ == "__main__":
    main()
