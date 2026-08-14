# -*- coding: utf-8 -*-
"""SpinHire — краулер вакансий iGaming.

Собирает вакансии с ПУБЛИЧНЫХ источников и клонирует их полный контент в нашу БД
(полное описание на нашей странице /job/{id} + JobPosting-схема + категория).
Дедупликация по (source, ext_id). Повторный запуск обновляет/реактивирует.

Источники:
  1) Greenhouse Job Board API — публичный JSON с полным описанием вакансии.
     https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true
     Используют Betsson, десятки iGaming-компаний.
  2) (расширяемо) любой URL с JobPosting JSON-LD — парсер schema.org.

Запуск:
  python3 -m server.crawler            # разовый прогон
  вызывается также из админки и по systemd-таймеру.

Юридически: клонируем ОБЪЯВЛЕНИЯ КОМПАНИЙ (не персональные данные людей),
рерайтим/чистим текст, сохраняем ссылку на первоисточник. Персональные резюме
таким образом НЕ собираются — это было бы нарушением GDPR/152-ФЗ.
"""
import html
import json
import re
import sys
import urllib.request
from datetime import datetime

# Greenhouse-борды известных iGaming-работодателей (board_token: человекочитаемое имя)
GREENHOUSE_BOARDS = {
    "betsson": "Betsson Group",
    "kaizengaming": "Kaizen Gaming (Betano)",
    "geniussports": "Genius Sports",
}

UA = "SpinHireBot/1.0 (+https://spinhire.org; job aggregation)"
TIMEOUT = 25
MAX_PER_BOARD = 40           # не выкачиваем борд целиком — берём свежие
DESC_LIMIT = 6000            # ограничиваем длину описания


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace")


def _clean_html(raw):
    """HTML описания → чистый читаемый текст (клонируем контент, не верстку источника)."""
    s = raw or ""
    # Greenhouse отдаёт дважды-закодированный HTML (&amp;lt;p&amp;gt;&amp;nbsp;) — декодируем 2 раза
    s = html.unescape(html.unescape(s))
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", s)
    s = re.sub(r"(?i)<\s*(br|/p|/div|/li|/h[1-6]|/tr)\s*/?>", "\n", s)
    s = re.sub(r"(?i)<\s*li[^>]*>", "• ", s)
    s = re.sub(r"(?i)<\s*h[1-6][^>]*>", "\n\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("\xa0", " ")                 # неразрывный пробел → обычный
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    # выкинуть пустые/мусорные строки (одни пробелы, точки, буллеты без текста)
    lines = [ln.strip() for ln in s.split("\n")]
    lines = [ln for ln in lines if ln and ln not in ("•", "·", "-", ".")]
    s = "\n".join(lines)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s[:DESC_LIMIT]


def _fmt_from(location, content):
    loc = (location or "").lower()
    text = (content or "").lower()
    if "remote" in loc or "удал" in loc:
        return "удалёнка ЕС" if ("eu" in loc or "europe" in text) else "удалёнка"
    if "hybrid" in text or "гибрид" in loc:
        return "гибрид"
    return "офис"


_LANGS = [
    ("немецкий", ("german", "deutsch", "немецк")), ("испанский", ("spanish", "español", "испанск")),
    ("португальский", ("portuguese", "português", "португальск")), ("итальянский", ("italian", "итальянск")),
    ("французский", ("french", "français", "французск")), ("турецкий", ("turkish", "турецк")),
    ("финский", ("finnish", "финск")), ("шведский", ("swedish", "шведск")),
    ("японский", ("japanese", "японск")), ("греческий", ("greek", "греческ")),
    ("польский", ("polish", "польск")), ("нидерландский", ("dutch", "нидерланд")),
    ("украинский", ("ukrainian", "українськ", "украинск")), ("русский", ("russian", "русск")),
    ("английский", ("english", "английск")),
]


def detect_lang(title, content):
    """Основной требуемый язык вакансии (или English по умолчанию)."""
    text = f"{title} {content}".lower()
    for label, keys in _LANGS:
        if any(k in text for k in keys) and label != "английский":
            return label
    if any(k in text for k in ("english", "английск")):
        return "английский"
    return ""


def _tags_from(title, content, lang=""):
    text = f"{title} {content}".lower()
    pool = [
        ("релокация", ("relocat", "relocation", "work permit", "visa", "переезд")),
        ("удалёнка", ("remote", "remote-first")), ("VIP", ("vip ", "vip-")),
        ("AML/KYC", ("aml", "kyc")), ("аффилейты", ("affiliate", "affil")),
        ("CRM", ("crm", "retention")), ("спортсбук", ("sportsbook", "trading")),
        ("Unity", ("unity",)), ("Java", ("java ",)), (".NET", (".net", "c#")),
        ("SQL/BI", ("sql", "power bi", "tableau")),
    ]
    out = []
    if lang:
        out.append(lang)
    for label, keys in pool:
        if any(k in text for k in keys) and label not in out:
            out.append(label)
        if len(out) >= 3:
            break
    return ", ".join(out)


def crawl_greenhouse(board, company):
    """Вернуть список dict-вакансий с полным описанием из Greenhouse API."""
    listing = json.loads(_fetch(
        f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"))
    jobs = listing.get("jobs", [])[:MAX_PER_BOARD]
    out = []
    for j in jobs:
        loc = (j.get("location") or {}).get("name", "")
        content = _clean_html(j.get("content", ""))
        title = (j.get("title") or "").strip()
        if not title:
            continue
        lang = detect_lang(title, content)
        out.append({
            "title": title,
            "company_name": company,
            "location": loc,
            "fmt": _fmt_from(loc, content),
            "tags": _tags_from(title, content, lang),
            "description": content,
            "source_url": j.get("absolute_url", ""),
            "source": f"greenhouse:{board}",
            "ext_id": str(j.get("id", "")),
            "salary": "по запросу",  # greenhouse редко отдаёт вилку явно
        })
    return out


def collect():
    """Собрать вакансии со всех источников. Возвращает список dict."""
    items = []
    for board, company in GREENHOUSE_BOARDS.items():
        try:
            got = crawl_greenhouse(board, company)
            items.extend(got)
            print(f"[crawl] {board}: +{len(got)}")
        except Exception as e:
            print(f"[crawl] {board} FAILED: {str(e)[:120]}")
    return items


def upsert(db, Job, guess_category, items, approve=True):
    """Записать/обновить вакансии в БД по (source, ext_id). Вернуть (added, updated)."""
    added = updated = 0
    seen = set()
    for it in items:
        key = (it["source"], it["ext_id"])
        seen.add(key)
        row = None
        if it["ext_id"]:
            row = db.query(Job).filter(Job.source == it["source"],
                                       Job.ext_id == it["ext_id"]).first()
        cat = guess_category(it["title"], it["tags"])
        if row:
            row.title, row.company_name = it["title"], it["company_name"]
            row.location, row.fmt = it["location"], it["fmt"]
            row.tags, row.description = it["tags"], it["description"]
            row.source_url, row.category = it["source_url"], cat
            if row.status in ("archived", "rejected"):
                row.status = "approved" if approve else "pending"
            updated += 1
        else:
            db.add(Job(title=it["title"], company_name=it["company_name"],
                       location=it["location"], fmt=it["fmt"], salary=it["salary"],
                       tags=it["tags"], description=it["description"],
                       source_url=it["source_url"], source=it["source"],
                       ext_id=it["ext_id"], category=cat,
                       status="approved" if approve else "pending"))
            added += 1
    db.commit()
    return added, updated


def run(db, Job, guess_category, approve=True):
    items = collect()
    added, updated = upsert(db, Job, guess_category, items, approve=approve)
    print(f"[crawl] готово: +{added} новых, {updated} обновлено, всего собрано {len(items)}")
    return {"collected": len(items), "added": added, "updated": updated,
            "at": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    sys.path.insert(0, __file__.rsplit("/server/", 1)[0])
    from server.app import SessionLocal, Job, guess_category, migrate, Base, engine
    Base.metadata.create_all(engine)
    with SessionLocal() as _db:
        migrate(_db)
        print(run(_db, Job, guess_category))
