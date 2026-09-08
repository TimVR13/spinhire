"""Реестр публикаций: что, где и когда мы публикуем, со статусами.

Площадки: youtube, telegram, reddit, linkedin, blog. Статусы:
  planned   — в плане (есть тема/слот, материала ещё нет)
  created   — материал готов (рендер/текст), ещё не отправлен
  scheduled — отправлен на площадку с отложенной публикацией
  published — вышел
  error     — попытка не удалась (текст ошибки в error)
  cancelled — снят вручную

Источники строк:
  • Telegram — таблицы tg_channel_posts / tg_digest_posts (sync_telegram)
  • YouTube  — data/youtube-posts.json из репо (sync_youtube; коммитится конвейером) и POST /api/publications/upsert
  • Reddit/LinkedIn — POST /api/publications/upsert из скриптов (ключ SPINHIRE_PUBLISH_KEY)
Страница: /admin/publications.
"""
import json
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import Session

from server.app import ROOT, Base, db_session, need_admin, render
from server.tgpost import TgDigestPost, TgHotPost

router = APIRouter()

PLATFORMS = [("youtube", "YouTube"), ("telegram", "Telegram"), ("reddit", "Reddit"), ("linkedin", "LinkedIn"), ("blog", "Блог")]
PLATFORM_LABELS = dict(PLATFORMS)
STATUSES = [("planned", "В плане"), ("created", "Создано"), ("scheduled", "Запланировано"),
            ("published", "Опубликовано"), ("error", "Ошибка"), ("cancelled", "Снято")]
STATUS_LABELS = dict(STATUSES)
KINDS = {"short": "Short", "long": "Видео", "hot": "Горячая вакансия", "digest": "Дайджест", "post": "Пост",
         "article": "Статья", "report": "Отчёт"}
PUBLISH_KEY = os.environ.get("SPINHIRE_PUBLISH_KEY", "")


class Publication(Base):
    __tablename__ = "publications"
    id = Column(Integer, primary_key=True)
    platform = Column(String, nullable=False, index=True)     # youtube | telegram | reddit | linkedin | blog
    lang = Column(String, default="ru")                       # ru | en
    kind = Column(String, default="post")                     # short | long | hot | digest | post | article | report
    external_id = Column(String, unique=True, nullable=False)  # yt:<video_id>, tg:<lang>:<message_id>, reddit:<id>, plan:<slug>
    title = Column(String, default="")
    url = Column(String, default="")
    status = Column(String, default="planned", index=True)
    scheduled_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    error = Column(Text, default="")
    meta = Column(Text, default="{}")                         # JSON: формат, плейлист, вакансии, сабреддит…
    origin = Column(String, default="pipeline")               # pipeline | cloud | manual
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def meta_dict(self) -> dict:
        try:
            return json.loads(self.meta or "{}")
        except ValueError:
            return {}


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


def upsert(db: Session, external_id: str, **fields) -> Publication:
    row = db.query(Publication).filter_by(external_id=external_id).first()
    if not row:
        row = Publication(external_id=external_id)
        db.add(row)
    for k, v in fields.items():
        if k in ("scheduled_at", "published_at"):
            v = _parse_ts(v)
        if k == "meta" and isinstance(v, dict):
            v = json.dumps(v, ensure_ascii=False)
        if v is not None:
            setattr(row, k, v)
    return row


# ---------- синхронизация из существующих источников ----------

def sync_telegram(db: Session) -> int:
    n = 0
    known = {r.external_id for r in db.query(Publication.external_id).filter(Publication.platform == "telegram")}
    for r in db.query(TgHotPost).all():
        ext = f"tg:{r.channel}:hot:{r.message_id or r.id}"
        if ext in known:
            continue
        upsert(db, ext, platform="telegram", lang=r.channel, kind="hot", status="published", published_at=r.posted_at,
               title=f"Горячая вакансия #{r.job_id}", url=f"https://t.me/{'spinhire_ru' if r.channel == 'ru' else 'spinhire'}/{r.message_id or ''}",
               meta={"job_id": r.job_id})
        n += 1
    for r in db.query(TgDigestPost).all():
        ext = f"tg:{r.channel}:digest:{r.message_id or r.id}"
        if ext in known:
            continue
        upsert(db, ext, platform="telegram", lang=r.channel, kind="digest", status="published", published_at=r.posted_at,
               title="Дайджест самых дорогих вакансий", url=f"https://t.me/{'spinhire_ru' if r.channel == 'ru' else 'spinhire'}/{r.message_id or ''}",
               meta={"job_ids": r.job_ids})
        n += 1
    return n


def sync_youtube(db: Session) -> int:
    """Лог конвейера Shorts, закоммиченный в репо. Запланированные помечаем вышедшими, когда время прошло."""
    path = os.path.join(ROOT, "data", "youtube-posts.json")
    if not os.path.exists(path):
        return 0
    try:
        rows = json.load(open(path, encoding="utf-8"))
    except ValueError:
        return 0
    now = datetime.utcnow()
    n = 0
    for r in rows:
        if not r.get("video_id"):
            continue
        sched = _parse_ts(r.get("publish_at"))
        status = "published" if sched and sched <= now else ("scheduled" if sched else "created")
        row = upsert(db, f"yt:{r['video_id']}", platform="youtube", lang="ru", kind="short", title=r.get("title", ""),
                     url=r.get("url", ""), scheduled_at=sched, meta={"format": r.get("format"), "playlist": r.get("playlist"),
                                                                    "slug": r.get("slug"), "featured": r.get("featured", [])})
        if row.status not in ("cancelled", "error"):
            row.status = status
            if status == "published" and not row.published_at:
                row.published_at = sched
        n += 1
    fails = os.path.join(ROOT, "data", "youtube-failures.log")
    if os.path.exists(fails):
        for line in open(fails, encoding="utf-8"):
            line = line.strip()
            if line:
                upsert(db, f"ytfail:{line[:80]}", platform="youtube", lang="ru", kind="short", status="error", error=line,
                       title=line[:60])
    return n


def sync_all(db: Session) -> dict:
    out = {"telegram": sync_telegram(db), "youtube": sync_youtube(db)}
    db.commit()
    return out


# ---------- страница ----------

@router.get("/admin/publications", response_class=HTMLResponse)
def publications_page(request: Request, db: Session = Depends(db_session)):
    need_admin(request, db)
    sync_all(db)
    platform = request.query_params.get("platform") or ""
    status = request.query_params.get("status") or ""
    lang = request.query_params.get("lang") or ""
    q = db.query(Publication)
    if platform:
        q = q.filter(Publication.platform == platform)
    if status:
        q = q.filter(Publication.status == status)
    if lang:
        q = q.filter(Publication.lang == lang)
    rows = q.order_by(Publication.scheduled_at.desc().nullslast(), Publication.published_at.desc().nullslast(),
                      Publication.created_at.desc()).limit(300).all()
    # матрица площадка × статус
    matrix = {}
    for p in db.query(Publication).all():
        matrix.setdefault(p.platform, {}).setdefault(p.status, 0)
        matrix[p.platform][p.status] += 1
    week_ago = datetime.utcnow() - timedelta(days=7)
    stats = {
        "week": db.query(Publication).filter(Publication.status == "published", Publication.published_at >= week_ago).count(),
        "scheduled": db.query(Publication).filter(Publication.status == "scheduled").count(),
        "errors": db.query(Publication).filter(Publication.status == "error").count(),
        "planned": db.query(Publication).filter(Publication.status == "planned").count(),
    }
    upcoming = (db.query(Publication).filter(Publication.status.in_(("scheduled", "planned", "created")))
                .order_by(Publication.scheduled_at.asc().nullslast()).limit(30).all())
    return render(request, db, "admin/publications.html", rows=rows, matrix=matrix, stats=stats, upcoming=upcoming,
                  platforms=PLATFORMS, statuses=STATUSES, platform_labels=PLATFORM_LABELS, status_labels=STATUS_LABELS,
                  kinds=KINDS, f_platform=platform, f_status=status, f_lang=lang, msg=request.query_params.get("msg"))


@router.post("/admin/publications/{pid}/status")
def set_status(pid: int, request: Request, status: str = Form(...), db: Session = Depends(db_session)):
    need_admin(request, db)
    row = db.get(Publication, pid)
    if not row or status not in STATUS_LABELS:
        raise HTTPException(404)
    row.status = status
    if status == "published" and not row.published_at:
        row.published_at = datetime.utcnow()
    db.commit()
    return RedirectResponse("/admin/publications?msg=ok", status_code=303)


@router.post("/admin/publications/plan")
def add_plan(request: Request, platform: str = Form(...), lang: str = Form("ru"), kind: str = Form("post"),
             title: str = Form(...), scheduled_at: str = Form(""), db: Session = Depends(db_session)):
    """Ручная строка плана: тема на площадку и дату."""
    need_admin(request, db)
    ext = f"plan:{platform}:{int(datetime.utcnow().timestamp())}"
    upsert(db, ext, platform=platform, lang=lang, kind=kind, title=title.strip(), status="planned",
           scheduled_at=scheduled_at or None, origin="manual")
    db.commit()
    return RedirectResponse("/admin/publications?msg=planned", status_code=303)


# ---------- API для внешних конвейеров ----------

@router.post("/api/publications/upsert")
async def api_upsert(request: Request, x_publish_key: str = Header(default=""), db: Session = Depends(db_session)):
    if not PUBLISH_KEY or x_publish_key != PUBLISH_KEY:
        raise HTTPException(403, "bad key")
    body = await request.json()
    items = body if isinstance(body, list) else [body]
    out = []
    for it in items:
        if not it.get("external_id") or not it.get("platform"):
            raise HTTPException(400, "external_id и platform обязательны")
        row = upsert(db, it["external_id"], **{k: it.get(k) for k in
                     ("platform", "lang", "kind", "title", "url", "status", "scheduled_at", "published_at", "error", "meta", "origin")})
        out.append(row.external_id)
    db.commit()
    return JSONResponse({"ok": True, "upserted": out})


@router.get("/api/publications/plan")
def api_plan(request: Request, x_publish_key: str = Header(default=""), db: Session = Depends(db_session)):
    """План на ближайшие 7 дней — для облачных агентов, чтобы не публиковать лишнего."""
    if not PUBLISH_KEY or x_publish_key != PUBLISH_KEY:
        raise HTTPException(403, "bad key")
    until = datetime.utcnow() + timedelta(days=7)
    rows = (db.query(Publication).filter(Publication.status.in_(("planned", "created", "scheduled")),
                                         (Publication.scheduled_at.is_(None)) | (Publication.scheduled_at <= until))
            .order_by(Publication.scheduled_at.asc().nullslast()).all())
    return JSONResponse([{"id": r.id, "platform": r.platform, "lang": r.lang, "kind": r.kind, "title": r.title,
                          "status": r.status, "scheduled_at": r.scheduled_at.isoformat() + "Z" if r.scheduled_at else None,
                          "meta": r.meta_dict} for r in rows])
