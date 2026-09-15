#!/usr/bin/env python3
"""Посты браузерных рутин → реестр публикаций сайта (/admin/publications).

Рутины LinkedIn / Instagram / Threads / X / Facebook пишут только локальные журналы.
Скрипт читает их и отправляет в POST /api/publications/upsert по одной строке на пост
(лайки, подписки, вступления в группы и комментарии-прогревы не отправляются).
external_id стабильный, поэтому повторный запуск ничего не дублирует — вызывать
после каждой записи в журнал и для бэкфилла.

  python3 scripts/pub_report.py                 # отправить всё из журналов
  python3 scripts/pub_report.py --dry-run       # показать, что ушло бы, без сети
  python3 scripts/pub_report.py --only x,threads

Ключ: переменная SPINHIRE_PUBLISH_KEY или файл ~/.spinhire/publish.env
(строка SPINHIRE_PUBLISH_KEY=...). В репозиторий ключ не кладём.
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = os.environ.get("SPINHIRE_SITE", "https://spinhire.io")
KEY_FILE = Path.home() / ".spinhire" / "publish.env"
ORIGIN = "routine"
BATCH = 50


def _load(name: str) -> list:
    path = DATA / name
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8") or "[]")
    except ValueError as e:
        print(f"! {name}: битый JSON ({e}), пропускаю", file=sys.stderr)
        return []
    return rows if isinstance(rows, list) else []


def _title(note: str, fallback: str) -> str:
    note = (note or "").strip()
    if not note:
        return fallback
    head = re.split(r"[;\n]", note, maxsplit=1)[0].strip()
    return head[:140] or fallback


def _tail_id(url: str) -> str:
    """Короткий id поста из ссылки: urn, код поста, status id."""
    url = (url or "").split("?")[0].rstrip("/")
    m = re.search(r"urn:li:(?:activity|groupPost|share|ugcPost):[\w-]+", url)
    if m:
        return m.group(0)
    return url.rsplit("/", 1)[-1]


def _status(entry: dict) -> str:
    note = (entry.get("note") or "").lower()
    if "rate-limited" in note:
        return "error"
    if not entry.get("url") or "на модерации" in note or "pending moderation" in note:
        return "scheduled"  # отправлен, но ещё не виден в ленте
    return "published"


def _row(platform, ext, kind, lang, entry, title, url=None, status=None, meta=None) -> dict:
    status = status or _status(entry)
    return {
        "external_id": ext, "platform": platform, "lang": lang, "kind": kind, "title": title,
        "url": url if url is not None else (entry.get("url") or ""),
        "status": status,
        "published_at": entry.get("date") if status == "published" else None,
        "error": entry.get("note", "") if status == "error" else "",
        "meta": meta or {}, "origin": ORIGIN,
    }


def linkedin_feed() -> list:
    """data/linkedin-posts.json — пост страницы SPIN HIRE + репост с профиля Anton Kylikov."""
    out = []
    for e in _load("linkedin-posts.json"):
        if not e.get("url"):
            continue
        kind_name = e.get("kind") or "hiring"
        meta = {k: e[k] for k in ("slot", "kind", "job_id", "company_slug", "link") if e.get(k)}
        title = _title(e.get("note"), f"LinkedIn: {kind_name}")
        out.append(_row("linkedin", f"li:{_tail_id(e['url'])}", "post", "en", e, title,
                        meta={**meta, "author": "page SPIN HIRE"}))
        if e.get("repost_url"):
            out.append(_row("linkedin", f"li:{_tail_id(e['repost_url'])}", "repost", "en", e,
                            "Репост: " + title, url=e["repost_url"], status="published",
                            meta={**meta, "author": "Anton Kylikov", "of": e["url"]}))
    return out


def _group_posts(name: str, platform: str, prefix: str, default_lang: str) -> list:
    out = []
    for e in _load(name):
        if e.get("kind") != "post":
            continue
        gid = e.get("group_id")
        # ключ по группе и дате, а не по ссылке: ссылка часто появляется позже (пост на модерации),
        # и строка должна обновиться, а не задвоиться; в одну группу постим не чаще раза в 7 дней
        ext = f"{prefix}:group:{gid}:{e.get('date')}"
        note = e.get("note") or ""
        lang = "ru" if re.search(r"\bRU\b", note) else ("en" if re.search(r"\bEN\b", note) else default_lang)
        out.append(_row(platform, ext, "group_post", lang, e, _title(note, f"Пост в группу {gid}"),
                        meta={"group_id": gid, "mode": e.get("mode")}))
    return out


def linkedin_groups() -> list:
    return _group_posts("linkedin-group-posts.json", "linkedin", "li", "en")


def facebook_groups() -> list:
    return _group_posts("facebook-group-posts.json", "facebook", "fb", "en")


def instagram_threads() -> list:
    out = []
    for e in _load("social-posts.json"):
        platform = e.get("platform")
        if platform not in ("instagram", "threads") or not e.get("url"):
            continue
        prefix = "ig" if platform == "instagram" else "th"
        out.append(_row(platform, f"{prefix}:{_tail_id(e['url'])}", "post", "ru", e,
                        f"Карточка {e.get('kind', '')}".strip(), meta={"card": e.get("kind")}))
    return out


def x_posts() -> list:
    out = []
    for e in _load("x-engagement.json"):
        if e.get("action") != "post" or not e.get("url"):
            continue
        out.append(_row("x", f"x:{_tail_id(e['url'])}", "post", "en", e, _title(e.get("note"), "Пост в X")))
    return out


SOURCES = {
    "linkedin": [linkedin_feed, linkedin_groups],
    "instagram": [instagram_threads],
    "threads": [instagram_threads],
    "x": [x_posts],
    "facebook": [facebook_groups],
}


def collect(only: set | None) -> list:
    seen, rows = set(), []
    for platform, fns in SOURCES.items():
        if only and platform not in only:
            continue
        for fn in fns:
            for r in fn():
                if r["platform"] != platform or r["external_id"] in seen:
                    continue
                seen.add(r["external_id"])
                rows.append(r)
    return rows


def publish_key() -> str:
    key = os.environ.get("SPINHIRE_PUBLISH_KEY", "").strip()
    if key or not KEY_FILE.exists():
        return key
    for line in KEY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if line.startswith("SPINHIRE_PUBLISH_KEY="):
            return line.split("=", 1)[1].strip().strip("'\"")
    return ""


def send(rows: list, key: str) -> int:
    sent = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        req = urllib.request.Request(
            f"{SITE}/api/publications/upsert", data=json.dumps(chunk, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json", "X-Publish-Key": key,
                     "User-Agent": "spinhire-pub-report/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read() or b"{}")
        sent += len(body.get("upserted", []))
    return sent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="напечатать строки и итог, в сеть не ходить")
    ap.add_argument("--only", default="", help="через запятую: linkedin,instagram,threads,x,facebook")
    ap.add_argument("--quiet", action="store_true", help="без построчного вывода")
    a = ap.parse_args()
    only = {p.strip() for p in a.only.split(",") if p.strip()} or None

    rows = collect(only)
    if not a.quiet or a.dry_run:
        for r in rows:
            print(f"{r['platform']:<9} {r['status']:<9} {r['kind']:<10} {r['lang']} {r['external_id']:<60} {r['title'][:60]}")
    total = Counter((r["platform"], r["status"]) for r in rows)
    summary = ", ".join(f"{p}/{s}: {n}" for (p, s), n in sorted(total.items())) or "пусто"
    if a.dry_run:
        print(f"[dry-run] строк: {len(rows)} — {summary}")
        return 0
    if not rows:
        print("реестр: отправлять нечего")
        return 0
    key = publish_key()
    if not key:
        print(f"реестр: нет SPINHIRE_PUBLISH_KEY (env или {KEY_FILE}) — пропускаю", file=sys.stderr)
        return 0  # рутине это не повод падать
    try:
        n = send(rows, key)
    except Exception as e:  # noqa: BLE001 — реестр не критичный путь, рутина продолжает
        print(f"реестр недоступен: {e}", file=sys.stderr)
        return 0
    print(f"реестр: отправлено {n} строк — {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
