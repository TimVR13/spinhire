"""Очередь готовых роликов: собранные заранее mp4 ждут своего слота.

Имя файла не queue.py намеренно: pipeline/ стоит первым в sys.path и затенил бы stdlib-модуль queue,
без которого не импортируется requests (а значит и загрузка на YouTube).

Батч рендерит пачку (batch.py), автопилот в слот только забирает готовое (run.py) — озвучка и
рендер не занимают время слота, а YouTube получает ролики по расписанию, а не пачкой.
"""
import datetime as dt
import json

from common import DATA

QUEUE = DATA / "video-queue.json"


def load() -> list[dict]:
    return json.load(open(QUEUE, encoding="utf-8")) if QUEUE.exists() else []


def save(rows: list[dict]) -> None:
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text(json.dumps(rows, ensure_ascii=False, indent=1))


def add(entry: dict) -> None:
    rows = [r for r in load() if r["id"] != entry["id"]]
    rows.append(entry)
    save(rows)


def ready(fmt: str = "", exclude_slugs: set[str] | None = None) -> list[dict]:
    out = [r for r in load() if r.get("status") == "ready" and (not fmt or r["format"] == fmt)]
    if exclude_slugs:
        out = [r for r in out if r.get("slug") not in exclude_slugs]
    return sorted(out, key=lambda r: r.get("built_at", ""))


def mark_used(vid: str, published_as: str, video_id: str) -> None:
    rows = load()
    for r in rows:
        if r["id"] == vid:
            r.update({"status": "used", "published_as": published_as, "video_id": video_id,
                      "used_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")})
    save(rows)
