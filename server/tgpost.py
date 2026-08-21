# -*- coding: utf-8 -*-
"""Ежедневный дайджест вакансий в Telegram-каналы через Bot API.

Постим не каждую вакансию (это спам), а один пост в день: топ самых
дорогих вакансий за сутки, оформленный карточками, со ссылкой на борд.

Настройка — env:

  SPINHIRE_TG_BOT_TOKEN    токен бота из @BotFather (бот — админ канала)
  SPINHIRE_TG_CHANNEL_EN   @юзернейм или -100…id английского канала
  SPINHIRE_TG_CHANNEL_RU   то же для русского
  SPINHIRE_TG_DIGEST_AT    час выхода дайджеста, по умолчанию 10
  SPINHIRE_TG_TZ_OFFSET    часовой пояс канала, по умолчанию +3
  SPINHIRE_TG_TOP          сколько вакансий в дайджесте, по умолчанию 7

Без токена и каналов всё молчит.
"""
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import Session

from server.app import BASE_URL, Base, Job, SessionLocal, db_session, need_admin

router = APIRouter()

TOKEN = os.environ.get("SPINHIRE_TG_BOT_TOKEN", "")
CHANNELS = {
    "en": os.environ.get("SPINHIRE_TG_CHANNEL_EN", ""),
    "ru": os.environ.get("SPINHIRE_TG_CHANNEL_RU", ""),
}
DIGEST_AT = int(os.environ.get("SPINHIRE_TG_DIGEST_AT", "10"))
TZ_OFFSET = int(os.environ.get("SPINHIRE_TG_TZ_OFFSET", "3"))
TOP_N = max(3, int(os.environ.get("SPINHIRE_TG_TOP", "7")))
# «Горячие» вакансии — отдельными постами помимо дайджеста: от ~$5k/мес
HOT_EUR = float(os.environ.get("SPINHIRE_TG_HOT_EUR", "4600"))
HOT_PER_DAY = int(os.environ.get("SPINHIRE_TG_HOT_PER_DAY", "3"))
HOT_GAP_H = int(os.environ.get("SPINHIRE_TG_HOT_GAP_H", "3"))
_hours = os.environ.get("SPINHIRE_TG_HOURS", "9-21").split("-")
HOUR_FROM, HOUR_TO = int(_hours[0]), int(_hours[-1])
SITE = (BASE_URL or "https://spinhire.io").rstrip("/")

# Курсы для сравнения вилок между валютами — грубые, нужны только для сортировки
TO_EUR = {"€": 1.0, "$": 0.92, "£": 1.17, "₴": 0.022, "PLN": 0.23, "zł": 0.23,
          "₽": 0.010, "JPY": 0.0060, "¥": 0.0060, "SEK": 0.088, "NOK": 0.086,
          "CZK": 0.040, "RON": 0.20, "BGN": 0.51, "TRY": 0.026, "INR": 0.011}


class TgDigestPost(Base):
    """История дайджестов: чтобы не повторять вакансии и не слать дважды в день."""
    __tablename__ = "tg_digest_posts"
    id = Column(Integer, primary_key=True)
    channel = Column(String, nullable=False)          # 'en' | 'ru'
    job_ids = Column(String, default="")              # какие вакансии вошли
    message_id = Column(Integer, nullable=True)
    posted_at = Column(DateTime, default=datetime.utcnow)


class TgHotPost(Base):
    """Отдельные посты «горячих» вакансий (от ~$5k/мес) — дедуп по каналу."""
    __tablename__ = "tg_channel_posts"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, nullable=False)
    channel = Column(String, nullable=False)          # 'en' | 'ru'
    message_id = Column(Integer, nullable=True)
    posted_at = Column(DateTime, default=datetime.utcnow)


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def salary_eur(job) -> float:
    """Верхняя граница вилки в евро — для сортировки «самые дорогие»."""
    text = job.salary or ""
    numbers = [float(n.replace(" ", "").replace(" ", "").replace(",", "."))
               for n in re.findall(r"\d[\d\s ]*(?:[.,]\d+)?", text)]
    if not numbers:
        return 0.0
    rate = next((v for k, v in TO_EUR.items() if k in text), 1.0)
    top = max(numbers)
    # «€60K» и «60 000» должны сравниваться одинаково
    if re.search(r"\d\s*[KkКк]\b", text) and top < 1000:
        top *= 1000
    monthly = top * rate
    if re.search(r"в год|/year|annual|rocznie|p\.a\.", text, re.I):
        monthly /= 12
    elif monthly > 15000 and not re.search(r"в мес|/mo|month|мiсяц|miesi", text, re.I):
        # «£33 000 – £37 000» без периода — почти всегда годовая вилка
        monthly /= 12
    return monthly



PERIOD_WORDS = {
    "en": [(r"\s*в год\b", "/year"), (r"\s*в месяц\b", "/month"), (r"\s*в час\b", "/hour"),
           (r"\s*/ ?мес\b", "/month")],
    "ru": [(r"\s*/year\b", " в год"), (r"\s*/month\b", " в месяц"), (r"\s*/hour\b", " в час"),
           (r"\s*per year\b", " в год"), (r"\s*annually\b", " в год")],
}


def pretty_salary(text: str, lang: str) -> str:
    """Подпись периода — на языке канала, чтобы «в год» не торчало в EN-посте."""
    out = (text or "").strip()
    for pattern, repl in PERIOD_WORDS.get(lang, []):
        out = re.sub(pattern, repl, out, flags=re.I)
    return re.sub(r"\s{2,}", " ", out)


def is_english(job) -> bool:
    """В английский канал идёт только написанное латиницей: русская вакансия
    подписчику из Мальты бесполезна."""
    return not re.search(r"[а-яА-ЯіїєґІЇЄҐ]", f"{job.title} {(job.description or '')[:400]}")


def pick_jobs(db: Session, hours: int = 24, limit: int = TOP_N, exclude=(), lang: str = "ru"):
    """Топ по зарплате среди свежих вакансий; если их мало — расширяем окно."""
    for window in (hours, hours * 3, hours * 7):
        since = datetime.utcnow() - timedelta(hours=window)
        rows = (db.query(Job)
                .filter(Job.status == "approved", Job.created_at >= since)
                .all())
        rows = [j for j in rows if j.id not in exclude and salary_eur(j) > 0]
        if lang == "en":
            rows = [j for j in rows if is_english(j)]
        rows.sort(key=salary_eur, reverse=True)
        # не больше двух вакансий одной компании — иначе дайджест выглядит
        # как реклама одного работодателя
        picked, per_company = [], {}
        for job in rows:
            key = (job.company_name or "").strip().lower()
            if per_company.get(key, 0) >= 2:
                continue
            per_company[key] = per_company.get(key, 0) + 1
            picked.append(job)
            if len(picked) >= limit:
                break
        if len(picked) >= limit:
            return picked, window
    return picked, window



def localize(text: str, lang: str) -> str:
    """Гео и служебные слова — словарём языка канала (Польша → Poland)."""
    if lang == "ru" or not text:
        return text
    try:
        from server.app import _SERVER_VOCAB
    except Exception:
        return text
    vocab = _SERVER_VOCAB.get(lang) or {}
    for source in sorted(vocab, key=len, reverse=True):
        if source in text:
            text = text.replace(source, vocab[source])
    return text


TEXT = {
    "en": {
        "head": "💰 <b>Top paying iGaming jobs</b>",
        "today": "today", "week": "this week",
        "stat": "{new} new jobs · {total} open on the board",
        "cta": "👉 <a href=\"{url}\">See all jobs</a>",
        "remote": "remote", "hybrid": "hybrid", "office": "office",
        "tags": "#iGaming #jobs #casino #betting",
        "hot": "🔥 <b>Hot job</b>", "need": "What they're looking for:",
        "apply": "Details & apply",
    },
    "ru": {
        "head": "💰 <b>Самые дорогие вакансии iGaming</b>",
        "today": "за сегодня", "week": "за неделю",
        "stat": "{new} новых вакансий · {total} открыто на борде",
        "cta": "👉 <a href=\"{url}\">Все вакансии</a>",
        "remote": "удалёнка", "hybrid": "гибрид", "office": "офис",
        "tags": "#iGaming #вакансии #казино #беттинг",
        "hot": "🔥 <b>Вакансия дня</b>", "need": "Что ищут:",
        "apply": "Подробнее и отклик",
    },
}
FMT_KEY = {"удалёнка": "remote", "гибрид": "hybrid", "офис": "office"}


def build_digest(db: Session, lang: str, jobs=None, window=24) -> tuple:
    """Готовый HTML-текст поста и список id вошедших вакансий."""
    t = TEXT.get(lang, TEXT["en"])
    if jobs is None:
        jobs, window = pick_jobs(db)
    if not jobs:
        return "", []
    period = t["today"] if window <= 24 else t["week"]
    day = datetime.utcnow() + timedelta(hours=TZ_OFFSET)
    lines = [f"{t['head']} — {period}", ""]
    prefix = "" if lang == "ru" else f"/{lang}"
    for i, job in enumerate(jobs, 1):
        url = f"{SITE}{prefix}/job/{job.id}?utm_source=telegram&utm_medium=digest&utm_campaign={lang}"
        title = _esc((job.title or "").strip())[:70]
        place = " · ".join(x for x in (
            _esc(job.company_name or ""),
            _esc(localize(job.location or "", lang)),
            t.get(FMT_KEY.get(job.fmt, ""), ""),
        ) if x)
        lines.append(f"<b>{i}. <a href=\"{url}\">{title}</a></b>")
        lines.append(f"    <b>{_esc(pretty_salary(job.salary, lang))}</b>")
        lines.append(f"    <i>{place}</i>")
        lines.append("")
    since = datetime.utcnow() - timedelta(hours=24)
    new_today = db.query(Job).filter(Job.status == "approved", Job.created_at >= since).count()
    total = db.query(Job).filter(Job.status == "approved").count()
    lines.append(t["stat"].format(new=new_today, total=total))
    lines.append(t["cta"].format(url=f"{SITE}{prefix}/jobs?utm_source=telegram&utm_medium=digest"))
    lines.append("")
    lines.append(t["tags"])
    return "\n".join(lines), [j.id for j in jobs]


def job_bullets(job, limit: int = 4) -> list:
    """Первые пункты требований из описания — <li> или строки-буллеты."""
    text = job.description or ""
    items = [re.sub(r"<[^>]+>", "", m).strip()
             for m in re.findall(r"<li[^>]*>(.*?)</li>", text, re.S | re.I)]
    if not items:
        items = [line.strip().lstrip("•-–* ").strip()
                 for line in text.splitlines() if line.strip()[:1] in "•-–*"]
    out = []
    for item in items:
        item = re.sub(r"\s+", " ", item)
        if 8 <= len(item) <= 90:
            out.append(item)
        if len(out) >= limit:
            break
    return out


def build_hot(job, lang: str) -> str:
    """Пост одной «горячей» вакансии: заметно, но без нагромождения."""
    t = TEXT.get(lang, TEXT["en"])
    prefix = "" if lang == "ru" else f"/{lang}"
    url = f"{SITE}{prefix}/job/{job.id}?utm_source=telegram&utm_medium=hot&utm_campaign={lang}"
    fmt = t.get(FMT_KEY.get(job.fmt, ""), "")
    place = " · ".join(x for x in (_esc(localize(job.location or "", lang)), fmt) if x)
    lines = [f"{t['hot']}",
             "",
             f"🎰 <b>{_esc((job.title or '').strip())}</b> — {_esc(job.company_name or '')}"]
    if place:
        lines.append(f"📍 {place}")
    lines.append(f"💰 <b>{_esc(pretty_salary(job.salary, lang))}</b>")
    bullets = job_bullets(job)
    if bullets:
        lines += ["", f"<i>{t['need']}</i>"]
        lines += [f"• {_esc(localize(b, lang))}" for b in bullets]
    lines += ["", f"➡️ <a href=\"{url}\">{t['apply']}</a>", "", t["tags"]]
    return "\n".join(lines)


def pick_hot(db: Session, lang: str):
    """Самая дорогая непощенная вакансия за последние двое суток от порога HOT_EUR."""
    posted = {r.job_id for r in db.query(TgHotPost.job_id).filter(TgHotPost.channel == lang)}
    since = datetime.utcnow() - timedelta(hours=48)
    rows = (db.query(Job).filter(Job.status == "approved", Job.created_at >= since).all())
    rows = [j for j in rows if j.id not in posted and salary_eur(j) >= HOT_EUR]
    if lang == "en":
        rows = [j for j in rows if is_english(j)]
    rows.sort(key=salary_eur, reverse=True)
    return rows[0] if rows else None


def send_hot(db: Session, force: bool = False, dry: bool = False) -> dict:
    """Пост горячей вакансии, если нашлась и не нарушаем темп (кол-во/паузу)."""
    if not TOKEN and not dry:
        return {"skipped": "no_token"}
    result = {}
    day_ago = datetime.utcnow() - timedelta(hours=24)
    gap = datetime.utcnow() - timedelta(hours=HOT_GAP_H)
    for lang, chat in CHANNELS.items():
        if not chat and not dry:
            continue
        recent = (db.query(TgHotPost)
                  .filter(TgHotPost.channel == lang, TgHotPost.posted_at >= day_ago).all())
        if not force and len(recent) >= HOT_PER_DAY:
            result[lang] = "daily_cap"
            continue
        if not force and any(r.posted_at >= gap for r in recent):
            result[lang] = "too_soon"
            continue
        job = pick_hot(db, lang)
        if not job:
            result[lang] = "no_hot_jobs"
            continue
        text = build_hot(job, lang)
        if dry:
            result[lang] = text
            continue
        resp = _api("sendMessage", {"chat_id": chat, "text": text, "parse_mode": "HTML",
                                    "disable_web_page_preview": True})
        if resp.get("ok"):
            db.add(TgHotPost(job_id=job.id, channel=lang,
                             message_id=(resp.get("result") or {}).get("message_id")))
            db.commit()
            result[lang] = f"sent job {job.id}"
        else:
            result[lang] = f"error: {resp.get('description') or resp.get('error')}"
    return result or {"skipped": "no_channels"}


def _api(method: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/{method}", data=body,
        headers={"Content-Type": "application/json",
                 "User-Agent": "SpinHire/1.0 (+https://spinhire.io)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except Exception as exc:                                    # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def posted_today(db: Session, channel: str) -> bool:
    since = datetime.utcnow() - timedelta(hours=20)
    return bool(db.query(TgDigestPost)
                .filter(TgDigestPost.channel == channel, TgDigestPost.posted_at >= since)
                .first())


def recent_job_ids(db: Session, channel: str, days: int = 3) -> set:
    since = datetime.utcnow() - timedelta(days=days)
    out = set()
    for row in (db.query(TgDigestPost)
                .filter(TgDigestPost.channel == channel, TgDigestPost.posted_at >= since).all()):
        out.update(int(x) for x in (row.job_ids or "").split(",") if x.strip().isdigit())
    return out


def send_digest(db: Session, force: bool = False, dry: bool = False) -> dict:
    if not TOKEN:
        return {"skipped": "no_token"}
    result = {}
    for lang, chat in CHANNELS.items():
        if not chat:
            continue
        if not force and posted_today(db, lang):
            result[lang] = "already_posted"
            continue
        jobs, window = pick_jobs(db, exclude=recent_job_ids(db, lang), lang=lang)
        text, ids = build_digest(db, lang, jobs, window)
        if not text:
            result[lang] = "no_jobs"
            continue
        if dry:
            result[lang] = text
            continue
        resp = _api("sendMessage", {
            "chat_id": chat, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
        if resp.get("ok"):
            db.add(TgDigestPost(channel=lang, job_ids=",".join(map(str, ids)),
                                message_id=(resp.get("result") or {}).get("message_id")))
            db.commit()
            result[lang] = f"sent {len(ids)} jobs"
        else:
            result[lang] = f"error: {resp.get('description') or resp.get('error')}"
    return result or {"skipped": "no_channels"}


@router.post("/admin/tgpost/run")
def tgpost_run(request: Request, dry: int = 0, kind: str = "digest",
               db: Session = Depends(db_session)):
    """kind=digest — подборка дня, kind=hot — горячая вакансия; ?dry=1 — превью."""
    need_admin(request, db)
    send = send_hot if kind == "hot" else send_digest
    return JSONResponse(send(db, force=True, dry=bool(dry)))


@router.get("/admin/tgpost/preview")
def tgpost_preview(request: Request, db: Session = Depends(db_session)):
    need_admin(request, db)
    langs = [lang for lang in CHANNELS if CHANNELS[lang]] or ["en", "ru"]
    out = {}
    for lang in langs:
        job = pick_hot(db, lang)
        out[lang] = {"digest": build_digest(db, lang)[0],
                     "hot": build_hot(job, lang) if job else None}
    return JSONResponse(out)


def _scheduler():
    """Дайджест — раз в день в назначенный час; горячие вакансии — между делом,
    не чаще HOT_PER_DAY в сутки с паузой HOT_GAP_H часов."""
    while True:
        try:
            now = datetime.utcnow() + timedelta(hours=TZ_OFFSET)
            db = SessionLocal()
            try:
                if now.hour == DIGEST_AT:
                    res = send_digest(db)
                    if any(str(v).startswith("sent") for v in res.values()):
                        print(f"[tgpost] дайджест отправлен: {res}")
                elif HOUR_FROM <= now.hour < HOUR_TO:
                    res = send_hot(db)
                    if any(str(v).startswith("sent") for v in res.values()):
                        print(f"[tgpost] горячая вакансия: {res}")
            finally:
                db.close()
        except Exception as exc:                                # noqa: BLE001
            print(f"[tgpost] ошибка планировщика: {type(exc).__name__}: {exc}")
        time.sleep(1800)


def start_scheduler():
    if not TOKEN or not any(CHANNELS.values()):
        return
    threading.Thread(target=_scheduler, daemon=True).start()
    print(f"[tgpost] дайджест в {DIGEST_AT}:00 (+{TZ_OFFSET}) в каналы: "
          + ", ".join(k for k, v in CHANNELS.items() if v))
