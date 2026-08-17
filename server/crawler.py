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
from pathlib import Path
from urllib.parse import urlparse

# Greenhouse-борды известных iGaming-работодателей (board_token: человекочитаемое имя)
GREENHOUSE_BOARDS = {
    "betsson": "Betsson Group",
    "kaizengaming": "Kaizen Gaming (Betano)",
    "geniussports": "Genius Sports",
    "gr8tech": "GR8 Tech",
}

# Публичные ATS API. Добавление новой компании — одна строка конфигурации.
LEVER_SITES = {}
SMARTRECRUITERS_COMPANIES = {"Evolution": "Evolution"}

# Только источники, которые явно разрешают повторное использование уже анонимных
# профилей. Пусто по умолчанию: персональные резюме не скрейпим.
ANONYMOUS_TALENT_SOURCES = {}

# Источники с JobPosting JSON-LD на странице листинга (url: (имя, source-ключ))
JSONLD_LISTINGS = {
    "https://djinni.co/jobs/?company_type=gambling":
        ("Djinni · gambling (UA)", "djinni"),
}

# Реестр источников для отображения в админке (что настроено и статус)
SOURCE_REGISTRY = [
    {"key": "greenhouse:betsson", "name": "Betsson Group", "type": "Greenhouse API",
     "status": "работает", "note": "Публичный JSON API, полное описание вакансии"},
    {"key": "greenhouse:kaizengaming", "name": "Kaizen Gaming (Betano)", "type": "Greenhouse API",
     "status": "работает", "note": "Публичный JSON API"},
    {"key": "greenhouse:geniussports", "name": "Genius Sports", "type": "Greenhouse API",
     "status": "работает", "note": "Публичный JSON API"},
    {"key": "greenhouse:gr8tech", "name": "GR8 Tech", "type": "Greenhouse API",
     "status": "подключён", "note": "Публичный JSON API; вакансии и метаданные компании"},
    {"key": "smartrecruiters:Evolution", "name": "Evolution", "type": "SmartRecruiters API",
     "status": "подключён", "note": "Публичный ATS API"},
    {"key": "djinni", "name": "Djinni · gambling (Украина)", "type": "JSON-LD парсер",
     "status": "подключён", "note": "15 вакансий/страница из JobPosting-разметки; зарплата/город в HTML (не в JSON-LD)"},
    {"key": "hh.ru", "name": "HeadHunter (hh.ru / hh.ua)", "type": "Публичный API — требует настройки",
     "status": "не подключён", "note": "api.hh.ru бесплатный (зарплата+город+работодатель), но из облака отдаёт 403 — нужен зарегистрированный app-токен ИЛИ запуск с разрешённого IP. Покрывает RU/UA/СНГ. Готов подключить."},
    {"key": "work.ua", "name": "work.ua", "type": "JobPosting-разметка — в планах",
     "status": "не подключён", "note": "Нет публичного API; на страницах есть JobPosting schema — парсим листинг HTML. Agressive anti-bot."},
    {"key": "robota.ua", "name": "robota.ua", "type": "в планах",
     "status": "не подключён", "note": "Украинский борд; есть внутренний API. Готов исследовать."},
]

RESUME_SOURCE_REGISTRY = [
    {"key": "spinhire:profiles", "name": "Профили SpinHire", "type": "Собственная база",
     "status": "работает", "note": "Анкеты, которые кандидаты сами создали и разрешили показывать работодателям."},
    {"key": "anonymous:partners", "name": "Анонимные партнёрские профили", "type": "Opt-in API",
     "status": "не подключён", "note": "Подключается только при явном согласии кандидата на передачу. Имя, email и контакты не импортируются."},
    {"key": "public:resume-sites", "name": "Открытые базы резюме", "type": "Сбор отключён",
     "status": "запрещён", "note": "Автоматический сбор персональных резюме не запускаем без лицензии источника и согласия кандидатов."},
]

UA = "SpinHireBot/1.0 (+https://spinhire.io; job aggregation)"
TIMEOUT = 25
MAX_PER_BOARD = 40           # не выкачиваем борд целиком — берём свежие
DESC_LIMIT = 6000            # ограничиваем длину описания


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace")


def _fetch_html(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace")


def crawl_jsonld(url, source):
    """Собрать вакансии из JobPosting JSON-LD на странице листинга (Djinni и др.)."""
    import json as _json
    page = _fetch_html(url)
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    out = []
    for b in blocks:
        try:
            d = _json.loads(b)
        except Exception:
            continue
        items = d if isinstance(d, list) else [d]
        for it in items:
            if not isinstance(it, dict) or it.get("@type") != "JobPosting":
                continue
            title = (it.get("title") or "").strip()
            if not title:
                continue
            org = it.get("hiringOrganization") or {}
            company = (org.get("name") if isinstance(org, dict) else "") or "iGaming-компания"
            desc = _clean_html(it.get("description", ""))
            u = it.get("url", "")
            m = re.search(r"(\d+)", u.rsplit("/", 1)[-1])
            ext = m.group(1) if m else u[-24:]
            loc = ""
            jl = it.get("jobLocation")
            if isinstance(jl, list):
                jl = jl[0] if jl else None
            if isinstance(jl, dict):
                addr = jl.get("address") or {}
                if isinstance(addr, dict):
                    loc = addr.get("addressLocality", "") or ""
            if not isinstance(loc, str):
                loc = ""
            if it.get("jobLocationType") == "TELECOMMUTE":
                loc = loc or "Remote"
            lang = detect_lang(title, desc)
            out.append({
                "title": title, "company_name": company, "location": loc,
                "fmt": _fmt_from(loc, desc), "tags": _tags_from(title, desc, lang),
                "description": desc, "source_url": u, "source": source,
                "ext_id": str(ext), "salary": "по запросу",
                "posted_at": (it.get("datePosted") or "")[:10],
                "deadline": (it.get("validThrough") or "")[:10],
            })
    return out


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
    head = (content or "")[:600].lower()  # формат обычно указан в начале
    if "remote" in loc or "удал" in loc or "fully remote" in head or "100% remote" in head or "remote-first" in head:
        return "удалёнка ЕС" if ("eu" in loc or "europe" in loc or "europe" in head) else "удалёнка"
    if "hybrid" in loc or "гибрид" in loc or "hybrid" in head:
        return "гибрид"
    if "remote" in head:
        return "гибрид"  # упоминается remote, но не в локации — вероятно гибрид
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
        ("релокация", ("relocat", "relocation", "work permit", "visa sponsor", "переезд")),
        ("VIP", ("vip ", "vip-")), ("AML/KYC", ("aml", "kyc")),
        ("аффилейты", ("affiliate", "affil")), ("CRM", ("crm", "retention")),
        ("спортсбук", ("sportsbook",)), ("Unity", ("unity",)), ("Java", ("java ",)),
        (".NET", (".net", "c# ")), ("SQL/BI", ("sql", "power bi", "tableau")),
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


def _best_location(j):
    """Город + страна: приоритет offices[].location (полный адрес), потом location.name, потом metadata Country."""
    offices = j.get("offices") or []
    if offices and isinstance(offices, list):
        full = (offices[0] or {}).get("location") or (offices[0] or {}).get("name") or ""
        if full:
            # "Santiago, Santiago Metropolitan Region, Chile" → "Santiago, Chile"
            parts = [p.strip() for p in full.split(",") if p.strip()]
            if len(parts) >= 3:
                return f"{parts[0]}, {parts[-1]}"
            return full
    loc = (j.get("location") or {}).get("name", "")
    if loc:
        return loc
    for meta in (j.get("metadata") or []):
        if isinstance(meta, dict) and meta.get("name") == "Country":
            v = meta.get("value")
            return ", ".join(v) if isinstance(v, list) else str(v or "")
    return ""


def _dept_category(j):
    depts = j.get("departments") or []
    if depts and isinstance(depts, list):
        return (depts[0] or {}).get("name", "")
    return ""


def crawl_greenhouse(board, company):
    """Вернуть список dict-вакансий с полным описанием из Greenhouse API."""
    listing = json.loads(_fetch(
        f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"))
    jobs = listing.get("jobs", [])[:MAX_PER_BOARD]
    out = []
    for j in jobs:
        loc = _best_location(j)
        content = _clean_html(j.get("content", ""))
        title = (j.get("title") or "").strip()
        if not title:
            continue
        lang = detect_lang(title, content)
        dept = _dept_category(j)
        out.append({
            "title": title,
            "company_name": (j.get("company_name") or company).strip(),
            "location": loc,
            "fmt": _fmt_from(loc, content),
            "tags": _tags_from(f"{title} {dept}", content, lang),
            "description": content,
            "source_url": j.get("absolute_url", ""),
            "source": f"greenhouse:{board}",
            "ext_id": str(j.get("id", "")),
            "salary": "по запросу",  # greenhouse редко отдаёт вилку явно
            "posted_at": (j.get("first_published") or j.get("updated_at") or "")[:10],
            "deadline": (j.get("application_deadline") or "")[:10] if j.get("application_deadline") else "",
        })
    return out


def crawl_lever(site, company):
    """Вакансии из публичного Lever Postings API."""
    jobs = json.loads(_fetch(f"https://api.lever.co/v0/postings/{site}?mode=json"))[:MAX_PER_BOARD]
    out = []
    for j in jobs:
        title = (j.get("text") or "").strip()
        if not title:
            continue
        cats = j.get("categories") or {}
        loc = cats.get("location", "")
        desc = _clean_html("\n".join(filter(None, [j.get("descriptionPlain", ""), j.get("additionalPlain", "")])))
        out.append({"title": title, "company_name": company, "location": loc,
                    "fmt": _fmt_from(loc, desc), "tags": _tags_from(title, desc),
                    "description": desc, "source_url": j.get("hostedUrl", ""),
                    "source": f"lever:{site}", "ext_id": str(j.get("id", "")),
                    "salary": "по запросу", "posted_at": "", "deadline": ""})
    return out


def crawl_smartrecruiters(company_id, company):
    """Вакансии из публичного SmartRecruiters API."""
    data = json.loads(_fetch(f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings?limit={MAX_PER_BOARD}"))
    out = []
    for j in (data.get("content") or [])[:MAX_PER_BOARD]:
        title = (j.get("name") or "").strip()
        if not title:
            continue
        loc_data = j.get("location") or {}
        loc = ", ".join(filter(None, [loc_data.get("city"), loc_data.get("country")]))
        dept = ((j.get("department") or {}).get("label") or "")
        desc = _clean_html(" ".join(filter(None, [title, dept])))
        out.append({"title": title, "company_name": company, "location": loc,
                    "fmt": _fmt_from(loc, desc), "tags": _tags_from(f"{title} {dept}", desc),
                    "description": desc, "source_url": j.get("ref", ""),
                    "source": f"smartrecruiters:{company_id}", "ext_id": str(j.get("id", "")),
                    "salary": "по запросу", "posted_at": (j.get("releasedDate") or "")[:10], "deadline": ""})
    return out


def company_snapshot(items):
    """Агрегировать публичные данные компаний из вакансий без отдельного скрейпинга."""
    companies = {}
    for item in items:
        name = item.get("company_name") or "iGaming-компания"
        row = companies.setdefault(name, {"name": name, "open_jobs": 0, "locations": set(),
                                          "sources": set(), "career_url": "", "domain": ""})
        row["open_jobs"] += 1
        if item.get("location"):
            row["locations"].add(item["location"])
        row["sources"].add(item.get("source", ""))
        row["career_url"] = row["career_url"] or item.get("source_url", "")
        host = urlparse(row["career_url"]).hostname or ""
        row["domain"] = row["domain"] or host.removeprefix("www.")
    return [{**row, "locations": sorted(row["locations"]), "sources": sorted(row["sources"])}
            for row in companies.values()]


def sanitize_anonymous_talent(profile):
    """Оставить только неперсональные карьерные поля из opt-in источника."""
    if profile.get("consent_to_redistribute") is not True:
        return None
    allowed = ("headline", "skills", "seniority", "years_experience", "preferred_locations",
               "remote", "salary_expectation", "languages", "available_from")
    return {key: profile.get(key) for key in allowed if profile.get(key) not in (None, "", [])}


def save_status(payload):
    """Сохранить результат последнего запуска для панели администратора."""
    status_path = Path(__file__).resolve().parent.parent / "data" / "crawler-status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def collect():
    """Собрать вакансии со всех источников. Возвращает список dict."""
    items = []
    for board, company in GREENHOUSE_BOARDS.items():
        try:
            got = crawl_greenhouse(board, company)
            items.extend(got)
            print(f"[crawl] greenhouse:{board}: +{len(got)}")
        except Exception as e:
            print(f"[crawl] greenhouse:{board} FAILED: {str(e)[:120]}")
    for url, (name, source) in JSONLD_LISTINGS.items():
        try:
            got = crawl_jsonld(url, source)
            items.extend(got)
            print(f"[crawl] {source}: +{len(got)}")
        except Exception as e:
            print(f"[crawl] {source} FAILED: {str(e)[:120]}")
    for site, company in LEVER_SITES.items():
        try:
            got = crawl_lever(site, company); items.extend(got)
            print(f"[crawl] lever:{site}: +{len(got)}")
        except Exception as e:
            print(f"[crawl] lever:{site} FAILED: {str(e)[:120]}")
    for company_id, company in SMARTRECRUITERS_COMPANIES.items():
        try:
            got = crawl_smartrecruiters(company_id, company); items.extend(got)
            print(f"[crawl] smartrecruiters:{company_id}: +{len(got)}")
        except Exception as e:
            print(f"[crawl] smartrecruiters:{company_id} FAILED: {str(e)[:120]}")
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
            row.posted_at = it.get("posted_at", "") or row.posted_at
            row.deadline = it.get("deadline", "") or row.deadline
            if row.status in ("archived", "rejected"):
                row.status = "approved" if approve else "pending"
            updated += 1
        else:
            db.add(Job(title=it["title"], company_name=it["company_name"],
                       location=it["location"], fmt=it["fmt"], salary=it["salary"],
                       tags=it["tags"], description=it["description"],
                       source_url=it["source_url"], source=it["source"],
                       ext_id=it["ext_id"], category=cat,
                       posted_at=it.get("posted_at", ""), deadline=it.get("deadline", ""),
                       status="approved" if approve else "pending"))
            added += 1
    db.commit()
    return added, updated


def run(db, Job, guess_category, approve=True):
    items = collect()
    added, updated = upsert(db, Job, guess_category, items, approve=approve)
    profiles = company_snapshot(items)
    snapshot_path = Path(__file__).resolve().parent.parent / "data" / "companies.json"
    snapshot_path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
    source_counts = {}
    for item in items:
        source = item.get("source", "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1
    save_status({
        "last_run": datetime.utcnow().isoformat() + "Z", "ok": True,
        "collected": len(items), "added": added, "updated": updated,
        "companies": len(profiles), "source_counts": source_counts,
    })
    print(f"[crawl] готово: +{added} новых, {updated} обновлено, всего собрано {len(items)}")
    return {"collected": len(items), "added": added, "updated": updated,
            "companies": len(profiles), "at": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    sys.path.insert(0, __file__.rsplit("/server/", 1)[0])
    from server.app import SessionLocal, Job, guess_category, migrate, Base, engine
    Base.metadata.create_all(engine)
    with SessionLocal() as _db:
        migrate(_db)
        print(run(_db, Job, guess_category))
