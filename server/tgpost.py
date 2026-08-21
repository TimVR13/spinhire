# -*- coding: utf-8 -*-
"""Автопостинг вакансий в Telegram-каналы через Bot API.

Бот (создаётся в @BotFather) должен быть админом каналов. Настройка — env:

  SPINHIRE_TG_BOT_TOKEN    токен бота
  SPINHIRE_TG_CHANNEL_RU   @юзернейм или -100…id русского канала
  SPINHIRE_TG_CHANNEL_EN   то же для английского (не обязателен)
  SPINHIRE_TG_INTERVAL_MIN пауза между постами в канал, по умолчанию 240
  SPINHIRE_TG_HOURS        окно постинга «9-21» (часы по SPINHIRE_TG_TZ_OFFSET, +3)

Без токена и каналов всё молчит — можно деплоить заранее.
Подключается в конце app.py рядом с CRM.
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
from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Session

from server.app import BASE_URL, Base, Job, SessionLocal, db_session, need_admin

router = APIRouter()

TOKEN = os.environ.get("SPINHIRE_TG_BOT_TOKEN", "")
CHANNELS = {
    "ru": os.environ.get("SPINHIRE_TG_CHANNEL_RU", ""),
    "en": os.environ.get("SPINHIRE_TG_CHANNEL_EN", ""),
}
INTERVAL_MIN = max(30, int(os.environ.get("SPINHIRE_TG_INTERVAL_MIN", "240")))
TZ_OFFSET = int(os.environ.get("SPINHIRE_TG_TZ_OFFSET", "3"))
_hours = os.environ.get("SPINHIRE_TG_HOURS", "9-21").split("-")
HOUR_FROM, HOUR_TO = int(_hours[0]), int(_hours[-1])
SITE = (BASE_URL or "https://spinhire.io").rstrip("/")


class TgChannelPost(Base):
    """Что уже публиковали — чтобы не дублировать вакансии в канале."""
    __tablename__ = "tg_channel_posts"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, nullable=False)
    channel = Column(String, nullable=False)          # 'ru' | 'en'
    message_id = Column(Integer, nullable=True)
    posted_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("job_id", "channel", name="uq_tgpost_job_channel"),)


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _has_salary(job: Job) -> bool:
    return bool(re.search(r"\d", job.salary or ""))


def _is_english(job: Job) -> bool:
    """Для EN-канала: вакансия написана латиницей (без кириллицы)."""
    text = f"{job.title} {job.description[:400]}"
    return not re.search(r"[а-яА-ЯіїєґІЇЄҐ]", text)


FMT_EN = {"удалёнка": "remote", "офис": "office", "гибрид": "hybrid"}


def _hashtags(job: Job, lang: str) -> str:
    words = []
    if job.category:
        words.append(job.category)
    words += [t.strip() for t in (job.tags or "").split(",") if t.strip()][:3]
    tags = []
    for w in words[:4]:
        tag = re.sub(r"[^\wа-яА-Я]+", "", w.replace(" ", "_"))
        if lang == "en" and re.search(r"[а-яА-Я]", tag):
            continue  # в английском канале кириллические теги неуместны
        if tag and tag.lower() not in [t.lower() for t in tags]:
            tags.append(tag)
    return " ".join("#" + t for t in tags)


def format_post(job: Job, lang: str) -> str:
    url = (f"{SITE}/job/{job.id}?utm_source=telegram&utm_medium=channel"
           f"&utm_campaign=autopost_{lang}")
    lines = [f"🎰 <b>{_esc(job.title)}</b>"]
    fmt = FMT_EN.get(job.fmt, job.fmt) if lang == "en" else job.fmt
    meta = " · ".join(x for x in (_esc(job.company_name), _esc(job.location), _esc(fmt)) if x)
    if meta:
        lines.append(f"🏢 {meta}")
    if _has_salary(job):
        lines.append(f"💰 {_esc(job.salary)}")
    tags = _hashtags(job, lang)
    if tags:
        lines.append(tags)
    cta = "Подробнее и отклик" if lang == "ru" else "Details & apply"
    lines.append(f'➡️ <a href="{url}">{cta}</a>')
    return "\n".join(lines)


def _api(method: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/{method}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def pick_job(db: Session, channel: str):
    """Свежая непощенная вакансия; с вилкой — в приоритете."""
    posted = {r.job_id for r in db.query(TgChannelPost.job_id)
              .filter(TgChannelPost.channel == channel)}
    q = (db.query(Job).filter(Job.status == "approved")
         .order_by(Job.created_at.desc()).limit(300))
    fresh = [j for j in q if j.id not in posted]
    if channel == "en":
        fresh = [j for j in fresh if _is_english(j)]
    with_salary = [j for j in fresh if _has_salary(j)]
    return (with_salary or fresh or [None])[0]


def post_due(db: Session, force: bool = False, dry: bool = False) -> dict:
    """Постит по одной вакансии в каждый настроенный канал, если пришло время."""
    out = {}
    if not TOKEN and not dry:
        return {"skip": "SPINHIRE_TG_BOT_TOKEN не задан"}
    hour = (datetime.utcnow().hour + TZ_OFFSET) % 24
    if not force and not (HOUR_FROM <= hour < HOUR_TO):
        return {"skip": f"вне окна {HOUR_FROM}-{HOUR_TO} (сейчас {hour})"}
    for lang, chat in CHANNELS.items():
        if not chat and not dry:
            continue
        last = (db.query(TgChannelPost).filter_by(channel=lang)
                .order_by(TgChannelPost.posted_at.desc()).first())
        if not force and last and last.posted_at > datetime.utcnow() - timedelta(minutes=INTERVAL_MIN):
            out[lang] = "рано, интервал не вышел"
            continue
        job = pick_job(db, lang)
        if not job:
            out[lang] = "нет непощенных вакансий"
            continue
        text = format_post(job, lang)
        if dry:
            out[lang] = {"job_id": job.id, "preview": text}
            continue
        try:
            r = _api("sendMessage", {"chat_id": chat, "text": text,
                                     "parse_mode": "HTML",
                                     "disable_web_page_preview": True})
            mid = r.get("result", {}).get("message_id")
            db.add(TgChannelPost(job_id=job.id, channel=lang, message_id=mid))
            db.commit()
            out[lang] = {"job_id": job.id, "message_id": mid}
        except Exception as e:
            out[lang] = f"ошибка: {str(e)[:200]}"
    return out


@router.post("/admin/tgpost/run")
def tgpost_run(request: Request, db: Session = Depends(db_session)):
    """Ручной прогон из админки: ?dry=1 — показать пост, не отправляя."""
    need_admin(request, db)
    dry = request.query_params.get("dry") == "1"
    return JSONResponse(post_due(db, force=True, dry=dry))


def _scheduler():
    time.sleep(90)  # даём приложению подняться
    while True:
        try:
            with SessionLocal() as db:
                res = post_due(db)
                if res and "skip" not in res:
                    print(f"[tgpost] {res}")
        except Exception as e:
            print(f"[tgpost] сбой: {str(e)[:160]}")
        time.sleep(600)


def start_scheduler():
    """Запускается из app.py; без токена и каналов — просто не стартует."""
    if TOKEN and any(CHANNELS.values()):
        threading.Thread(target=_scheduler, name="tg-autopost", daemon=True).start()
