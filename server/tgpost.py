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
import html
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import Session

from server import postfilter, tgcards
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
    """В английский канал идёт только латиница — и в тексте вакансии, и во
    всех полях, которые увидит подписчик: заголовок, компания, гео, вилка.
    Одно «маркетинг» в посте — и канал выглядит русским."""
    if postfilter.has_cyrillic(f"{job.title} {(job.description or '')[:400]}"):
        return False
    return postfilter.en_ready(job, salary=pretty_salary(job.salary, "en"),
                               location=localize(job.location or "", "en"))


def _mix(rows, limit: int):
    """Две трети подборки отдаём Европе и СНГ, остальное добираем по вилке.

    Иначе дайджест «самых дорогих» превращается в список удалёнок: акцент
    канала — европейские офисы (Мальта, Кипр, Варшава), а не абстрактный
    remote. Не больше двух вакансий одной компании — это не её реклама.
    """
    picked, per_company, taken = [], {}, set()

    def take(pool, cap):
        for job in pool:
            if len(picked) >= cap:
                return
            key = (job.company_name or "").strip().lower()
            if job.id in taken or per_company.get(key, 0) >= 2:
                continue
            per_company[key] = per_company.get(key, 0) + 1
            taken.add(job.id)
            picked.append(job)

    take([j for j in rows if postfilter.geo_rank(j) <= 1], -(-limit * 2 // 3))
    take(rows, limit)
    picked.sort(key=salary_eur, reverse=True)
    return picked


def pick_jobs(db: Session, hours: int = 24, limit: int = TOP_N, exclude=(), lang: str = "ru"):
    """Топ по зарплате среди свежих вакансий; если их мало — расширяем окно.

    Окно расширяем и тогда, когда вакансий хватает, но европейских среди них
    почти нет: подборка из одних удалёнок обещанного акцента не даёт.
    """
    quota, picked = -(-limit * 2 // 3), []
    for window in (hours, hours * 3, hours * 7):
        since = datetime.utcnow() - timedelta(hours=window)
        rows = (db.query(Job)
                .filter(Job.status == "approved", Job.created_at >= since)
                .all())
        # верхняя планка та же, что у горячих: «€1 815 293 в год» у game
        # presenter — это ошибка парсера, а не самая дорогая вакансия недели
        rows = [j for j in rows
                if j.id not in exclude and 0 < salary_eur(j) <= HOT_EUR_MAX]
        # США не постим ни в один канал, остальной мир кроме Европы, СНГ и
        # удалёнки — тоже: подписчику из Варшавы вакансия в Маниле не нужна
        rows = [j for j in rows if postfilter.allowed(j)]
        if lang == "en":
            rows = [j for j in rows if is_english(j)]
        rows.sort(key=salary_eur, reverse=True)
        picked = _mix(rows, limit)
        europe = sum(1 for job in picked if postfilter.geo_rank(job) <= 1)
        if len(picked) >= limit and europe >= quota:
            return picked, window
    return picked, window



def localize(text: str, lang: str) -> str:
    """Гео и служебные слова — словарём языка канала (Польша → Poland),
    ISO-коды источников разворачиваем в страну: «Sofia, bg» → «Sofia,
    Болгария»."""
    text = postfilter.pretty_location(text, lang)
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
# «Remote · удалёнка» в одной строке — это одно и то же дважды
REMOTE_LABELS = {"remote", "удалёнка", "удалённо", "anywhere", "global",
                 "worldwide", "remote job", "global - remote"}


def place_of(job, lang: str) -> str:
    """«Мальта · офис» — гео и формат на языке канала, без повторов."""
    t = TEXT.get(lang, TEXT["en"])
    location = localize(job.location or "", lang).strip()
    fmt = t.get(FMT_KEY.get(job.fmt, ""), "")
    if fmt and location.lower() in REMOTE_LABELS:
        location = ""
    place = " · ".join(x for x in (location, fmt) if x)
    return postfilter.en_clean(place) if lang == "en" else place


def build_digest(db: Session, lang: str, jobs=None, window=24) -> tuple:
    """Готовый HTML-текст поста и список id вошедших вакансий."""
    t = TEXT.get(lang, TEXT["en"])
    if jobs is None:
        jobs, window = pick_jobs(db, lang=lang)
    if not jobs:
        return "", []
    period = t["today"] if window <= 24 else t["week"]
    day = datetime.utcnow() + timedelta(hours=TZ_OFFSET)
    lines = [f"{t['head']} — {period}", ""]
    prefix = "" if lang == "ru" else f"/{lang}"
    for i, job in enumerate(jobs, 1):
        url = f"{SITE}{prefix}/job/{job.id}?utm_source=telegram&utm_medium=digest&utm_campaign={lang}"
        title = _esc((job.title or "").strip())[:70]
        place = " · ".join(x for x in (_esc(job.company_name or ""),
                                       _esc(place_of(job, lang))) if x)
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


def job_bullets(job, limit: int = 4, lang: str = "ru") -> list:
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
        if lang == "en" and postfilter.has_cyrillic(item):
            continue          # русский буллет в английском канале недопустим
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
    place = _esc(place_of(job, lang))
    lines = [f"{t['hot']}",
             "",
             f"🎰 <b>{_esc((job.title or '').strip())}</b> — {_esc(job.company_name or '')}"]
    if place:
        lines.append(f"📍 {place}")
    lines.append(f"💰 <b>{_esc(pretty_salary(job.salary, lang))}</b>")
    bullets = job_bullets(job, lang=lang)
    if bullets:
        lines += ["", f"<i>{t['need']}</i>"]
        lines += [f"• {_esc(localize(b, lang))}" for b in bullets]
    lines += ["", f"➡️ <a href=\"{url}\">{t['apply']}</a>", "", t["tags"]]
    return "\n".join(lines)


HOT_EUR_MAX = float(os.environ.get("SPINHIRE_TG_HOT_EUR_MAX", "40000"))


def pick_hot(db: Session, lang: str):
    """Самая дорогая непощенная вакансия за последние двое суток от порога HOT_EUR."""
    posted = {r.job_id for r in db.query(TgHotPost.job_id).filter(TgHotPost.channel == lang)}
    since = datetime.utcnow() - timedelta(hours=48)
    rows = (db.query(Job).filter(Job.status == "approved", Job.created_at >= since).all())
    # верхняя планка: > €40 000/мес — почти всегда ошибка парсера («€1 815 293 в год» у game presenter)
    rows = [j for j in rows if j.id not in posted and HOT_EUR <= salary_eur(j) <= HOT_EUR_MAX]
    # отдельный пост — самое заметное место в канале: США мимо, гео обязательна
    rows = [j for j in rows if postfilter.allowed(j, strict=True)]
    if lang == "en":
        rows = [j for j in rows if is_english(j)]
    rows.sort(key=lambda job: (postfilter.geo_rank(job), -salary_eur(job)))
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
        text = en_guard(build_hot(job, lang), lang)
        if dry:
            result[lang] = text
            continue
        photo = tgcards.hot_card(lang, (job.title or "").strip(),
                                 pretty_salary(job.salary, lang),
                                 place_of(job, lang),
                                 (job.company_name or "").strip())
        resp = _send(chat, text, photo)
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


CAPTION_LIMIT = 1024


def _visible_len(text: str) -> int:
    """Телеграм меряет подпись после разбора разметки: ссылки в лимит не идут."""
    return len(html.unescape(re.sub(r"<[^>]+>", "", text or "")))


def _photo(chat_id: str, photo: bytes, caption: str) -> dict:
    """sendPhoto: multipart собираем руками, чтобы не тащить requests."""
    boundary = "spinhire" + uuid.uuid4().hex
    body = bytearray()
    for name, value in (("chat_id", chat_id), ("caption", caption),
                        ("parse_mode", "HTML")):
        body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                 f"name=\"{name}\"\r\n\r\n{value}\r\n").encode()
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; "
             f"filename=\"spinhire.png\"\r\nContent-Type: image/png\r\n\r\n").encode()
    body += photo + b"\r\n" + f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/sendPhoto", data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "User-Agent": "SpinHire/1.0 (+https://spinhire.io)"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except Exception as exc:                                    # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _send(chat_id: str, text: str, photo=None) -> dict:
    """Пост с картинкой; не получилось или подпись длинновата — уходит текстом."""
    if photo and _visible_len(text) <= CAPTION_LIMIT:
        resp = _photo(chat_id, photo, text)
        if resp.get("ok"):
            return resp
        print("[tgpost] фото не ушло "
              f"({resp.get('description') or resp.get('error')}), шлю текстом")
    return _api("sendMessage", {"chat_id": chat_id, "text": text,
                                "parse_mode": "HTML",
                                "disable_web_page_preview": True})


def en_guard(text: str, lang: str) -> str:
    """Страховка перед отправкой: в английском канале не остаётся ни одной
    строки с кириллицей. Отборы выше их уже отсеяли, но пост дороже строки."""
    if lang != "en" or not postfilter.has_cyrillic(text):
        return text
    kept = [line for line in text.split("\n") if not postfilter.has_cyrillic(line)]
    print("[tgpost] выбросил русские строки из английского поста")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept))


def card_rows(jobs, lang: str) -> list:
    """Три верхние вакансии для картинки: заголовок, вилка, место."""
    rows = []
    for job in jobs[:3]:
        place = " · ".join(x for x in ((job.company_name or "").strip(),
                                       place_of(job, lang)) if x)
        rows.append(((job.title or "").strip(),
                     pretty_salary(job.salary, lang), place))
    return rows


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
        # подпись к фото — 1024 знака после разбора разметки; если не влезли,
        # укорачиваем подборку, а не режем текст на полуслове
        while len(jobs) > 3 and _visible_len(en_guard(text, lang)) > CAPTION_LIMIT:
            jobs = jobs[:-1]
            text, ids = build_digest(db, lang, jobs, window)
        text = en_guard(text, lang)
        if dry:
            result[lang] = text
            continue
        total = db.query(Job).filter(Job.status == "approved").count()
        photo = tgcards.digest_card(lang, card_rows(jobs, lang), total,
                                    extra=max(0, len(ids) - 3))
        resp = _send(chat, text, photo)
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


@router.get("/admin/tgpost/card")
def tgpost_card(request: Request, kind: str = "digest", lang: str = "ru",
                db: Session = Depends(db_session)):
    """Картинка поста как есть — посмотреть перед выходом в канал."""
    need_admin(request, db)
    if kind == "hot":
        job = pick_hot(db, lang)
        photo = job and tgcards.hot_card(
            lang, (job.title or "").strip(), pretty_salary(job.salary, lang),
            place_of(job, lang), (job.company_name or "").strip())
    else:
        jobs, _ = pick_jobs(db, lang=lang)
        total = db.query(Job).filter(Job.status == "approved").count()
        photo = jobs and tgcards.digest_card(lang, card_rows(jobs, lang), total,
                                             extra=max(0, len(jobs) - 3))
    if not photo:
        return JSONResponse({"error": "нечего рисовать"}, status_code=404)
    return Response(content=photo, media_type="image/png")


@router.get("/admin/tgpost/preview")
def tgpost_preview(request: Request, db: Session = Depends(db_session)):
    need_admin(request, db)
    langs = [lang for lang in CHANNELS if CHANNELS[lang]] or ["en", "ru"]
    out = {}
    for lang in langs:
        job = pick_hot(db, lang)
        out[lang] = {"digest": en_guard(build_digest(db, lang)[0], lang),
                     "hot": en_guard(build_hot(job, lang), lang) if job else None,
                     "card": f"/admin/tgpost/card?kind=digest&lang={lang}"}
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
