"""Общее для конвейера Shorts: пути, ключи, загрузка данных с сайта."""
import json
import os
import re
import urllib.request
from pathlib import Path

VIDEO_DIR = Path(__file__).resolve().parent.parent
ROOT = VIDEO_DIR.parent
PUBLIC = VIDEO_DIR / "public"
RENDERS = PUBLIC / "renders"          # voice.mp3 должен лежать в public/, иначе staticFile его не увидит
OUT = VIDEO_DIR / "out"
DATA = ROOT / "data"
SECRETS = Path(os.environ.get("SPINHIRE_YT_SECRETS", os.path.expanduser("~/.spinhire/yt")))
SITE = "https://spinhire.io"
TG = "https://t.me/spinhire_ru"


def env_or_file(env_name: str, filename: str) -> Path:
    """В GitHub Actions секрет приходит через env как JSON-строка; локально — файл в ~/.spinhire/yt."""
    val = os.environ.get(env_name)
    path = SECRETS / filename
    if val and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(val)
        os.chmod(path, 0o600)
    return path


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "SpinHire-Shorts/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def api_jobs(pages: int = 3, **params) -> list[dict]:
    jobs = []
    for page in range(1, pages + 1):
        q = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in {**params, "page": page, "limit": 100}.items())
        d = fetch_json(f"{SITE}/api/jobs?{q}")
        jobs += d["jobs"]
        if page >= d["pages"]:
            break
    return jobs


def market_stats() -> dict:
    return fetch_json(f"{SITE}/api/market-stats")


def professions() -> dict:
    return json.load(open(DATA / "professions.json", encoding="utf-8"))


def role(slug: str) -> dict:
    for r in professions()["roles"]:
        if r["slug"] == slug:
            return r
    raise KeyError(slug)


def tracks() -> list[dict]:
    return json.load(open(PUBLIC / "audio" / "tracks.json", encoding="utf-8"))


def pick_track(mood: str, seed: str) -> str:
    """Трек по настроению, детерминированно от seed (дата+слот), чтобы соседние ролики не совпадали."""
    pool = [t for t in tracks() if t["mood"] == mood] or tracks()
    idx = sum(ord(c) for c in seed) % len(pool)
    return "audio/" + pool[idx]["file"]


def monthly(job: dict) -> tuple[int | None, int | None]:
    lo, hi, unit = job.get("salary_min"), job.get("salary_max"), job.get("salary_unit")
    if unit == "YEAR":
        return (round(lo / 12 / 50) * 50 if lo else None, round(hi / 12 / 50) * 50 if hi else None)
    if unit == "MONTH":
        return (lo, hi)
    return (None, None)


CUR = {"USD": "$", "EUR": "€", "GBP": "£"}


def fmt_money(n: int, cur: str) -> str:
    return f"{CUR.get(cur, cur + ' ')}{n:,}".replace(",", " ")


def fmt_range(lo, hi, cur: str) -> str:
    if lo and hi and lo != hi:
        return f"{CUR.get(cur, '')}{lo:,}–{hi:,}".replace(",", " ")
    return "до " + fmt_money(hi or lo, cur)


def say_money(n: int, cur: str) -> str:
    """Для озвучки: «4 500 долларов»."""
    word = {"USD": "долларов", "EUR": "евро", "GBP": "фунтов"}.get(cur, cur)
    return f"{n:,}".replace(",", " ") + " " + word


def say_range(lo, hi, cur: str) -> str:
    """Для озвучки: «от 5 000 до 6 500 долларов» — валюта один раз, в конце."""
    word = {"USD": "долларов", "EUR": "евро", "GBP": "фунтов"}.get(cur, cur)
    n = lambda v: f"{v:,}".replace(",", " ")
    if lo and hi and lo != hi:
        return f"от {n(lo)} до {n(hi)} {word}"
    return f"до {n(hi or lo)} {word}"


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
