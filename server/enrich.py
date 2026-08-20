"""Дообогащение вакансий контентом из первоисточника.

Вакансии с пустым или заглушечным описанием («position at X. Leading iGaming
company») дообираются со страницы источника: описание, зарплата, локация,
формат — из JSON-LD JobPosting или метатегов. Заодно собираются теги по
словарю навыков. Если источник не отдал ничего содержательного — вакансия
снимается с публикации: «смотрите в первоисточнике» на борде не живёт.

Запуск вручную:  python -m server.enrich [лимит]
Из краулера:     enrich_missing(db, Job, limit=N) после upsert.
"""
import json
import re
import time
from datetime import datetime

from .crawler import _fetch, _fetch_html, _clean_html, parse_salary, format_salary

MIN_DESC = 200          # короче — считаем, что описания нет
FETCH_DELAY = 0.35      # вежливая пауза между запросами к чужим ATS

# Заглушки, которые краулер лепит из названия и компании.
STUB_RE = re.compile(
    r"position at .{2,60}\.( (Leading|Global|Uses) .{2,80}\.?)?$|"
    r"смотрите? (в )?(перво)?источник|see (the )?original", re.I)

# Теги: (паттерн, тег, минимум вхождений). Для слов, живущих в корпоративном
# буквоедстве (affiliates, payments, fraud), требуем 2+ упоминаний — одно
# случайное в юридической сноске тегом быть не должно.
TAG_RULES = [
    (r"\bvip\b", "VIP", 1), (r"\bcrm\b", "CRM", 1), (r"\bretention\b|удержани", "retention", 1),
    (r"sportsbook|спортбук|\bbetting\b|беттинг", "беттинг", 2),
    (r"live[ -]?casino|лайв[ -]?казино", "live casino", 1),
    (r"\bslots?\b|слот", "слоты", 2), (r"\baml\b", "AML", 1), (r"\bkyc\b", "KYC", 1),
    (r"anti[- ]?fraud|антифрод|\bfraud\b", "антифрод", 2),
    (r"\bpayments?\b|платеж|\bpsp\b", "платежи", 2), (r"\bcrypto\b|\busdt\b|крипт", "крипто", 1),
    (r"\baffiliates?\b|аффилейт", "аффилейты", 2), (r"media[ -]?buy|медиабаинг", "медиабаинг", 1),
    (r"\bseo\b", "SEO", 1), (r"\bppc\b|paid (ads|media)", "PPC", 1),
    (r"\bsql\b", "SQL", 1), (r"\bpython\b", "Python", 1), (r"\bjava\b", "Java", 1),
    (r"\breact\b", "React", 1), (r"\bunity\b|\bunreal\b", "геймдев-движки", 1),
    (r"\btableau\b|power ?bi|\blooker\b", "BI-инструменты", 1),
    (r"relocat|релокац", "релокация", 1), (r"\bremote\b|удалён", "удалёнка", 1),
    (r"\bgerman\b|немецк|deutsch", "немецкий", 1), (r"\bfrench\b|французск", "французский", 1),
    (r"\bspanish\b|испанск", "испанский", 1), (r"\bportuguese\b|португальск", "португальский", 1),
    (r"\bitalian\b|итальянск", "итальянский", 1), (r"\bturkish\b|турецк", "турецкий", 1),
    (r"\bpolish\b|польск", "польский", 1), (r"\bjapanese\b|японск", "японский", 1),
]
MAX_TAGS = 6


def needs_enrichment(job) -> bool:
    desc = (job.description or "").strip()
    return len(desc) < MIN_DESC or bool(STUB_RE.search(desc))


def _jsonld_posting(page: str):
    """Вытащить JobPosting из всех ld+json на странице."""
    for block in re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                            page, re.S | re.I):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        queue = data if isinstance(data, list) else [data]
        while queue:
            item = queue.pop(0)
            if isinstance(item, list):
                queue.extend(item)
                continue
            if not isinstance(item, dict):
                continue
            types = item.get("@type")
            types = types if isinstance(types, list) else [types]
            if "JobPosting" in types:
                return item
            if isinstance(item.get("@graph"), list):
                queue.extend(item["@graph"])
    return None


def _posting_salary(posting) -> str:
    base = posting.get("baseSalary")
    if not isinstance(base, dict):
        return ""
    value = base.get("value")
    currency = base.get("currency") or ""
    if isinstance(value, dict):
        lo, hi = value.get("minValue"), value.get("maxValue")
        unit = (value.get("unitText") or "").upper()
        suffix = {"HOUR": " в час", "YEAR": " в год", "MONTH": ""}.get(unit, "")
        sign = {"EUR": "€", "USD": "$", "GBP": "£"}.get(currency.upper(), currency + " ")
        try:
            if lo and hi and float(lo) > 0:
                return f"{sign}{int(float(lo)):,}–{int(float(hi)):,}{suffix}".replace(",", " ")
            if lo and float(lo) > 0:
                return f"от {sign}{int(float(lo)):,}{suffix}".replace(",", " ")
        except (TypeError, ValueError):
            return ""
    return ""


def _posting_location(posting) -> str:
    loc = posting.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if isinstance(loc, dict):
        addr = loc.get("address") or {}
        if isinstance(addr, dict):
            parts = [addr.get("addressLocality"), addr.get("addressCountry")]
            parts = [p if isinstance(p, str) else (p or {}).get("name", "") for p in parts]
            return ", ".join(p for p in parts if p)
    return ""


def derive_tags(title: str, description: str, existing: str = "") -> str:
    haystack = f"{title}\n{description}".lower()
    tags = [t.strip() for t in (existing or "").split(",") if t.strip()]
    for pattern, tag, min_hits in TAG_RULES:
        if len(tags) >= MAX_TAGS:
            break
        if tag in tags:
            continue
        hits = len(re.findall(pattern, haystack, re.I))
        # упоминание в названии — сигнал сам по себе, счётчик не нужен
        if hits >= min_hits or (hits and re.search(pattern, title, re.I)):
            tags.append(tag)
    return ", ".join(tags[:MAX_TAGS])


ACCEPT_DESC = 160       # добытое описание короче — считаем, что инфы нет

_WORKDAY_RE = re.compile(r"https://([^.]+)\.(wd\d+)\.myworkdayjobs\.com/"
                         r"(?:[a-z]{2}-[A-Z]{2}/)?([^/]+)/job/(.+)")


def _fetch_workday(url: str):
    """Workday прячет вакансию за SPA, но открытый cxs-API отдаёт всё."""
    m = _WORKDAY_RE.match(url)
    if not m:
        return None
    tenant, wd, site, rest = m.groups()
    try:
        data = json.loads(_fetch(f"https://{tenant}.{wd}.myworkdayjobs.com"
                                 f"/wday/cxs/{tenant}/{site}/job/{rest}"))
    except Exception:
        return None
    info = data.get("jobPostingInfo") or {}
    desc = _clean_html(info.get("jobDescription", ""))
    if not desc:
        return None
    fmt = "удалёнка" if "remote" in str(info.get("remoteType", "")).lower() else ""
    return {"description": desc, "salary": "",
            "location": info.get("location", "") or "", "fmt": fmt}


def _fetch_bamboohr(url: str):
    """BambooHR: /careers/{id}/detail — JSON с полным описанием."""
    if ".bamboohr.com/careers/" not in url:
        return None
    try:
        data = json.loads(_fetch(url.rstrip("/") + "/detail"))
    except Exception:
        return None
    opening = (data.get("result") or {}).get("jobOpening") or {}
    desc = _clean_html(opening.get("description", ""))
    if not desc:
        return None
    loc = opening.get("atsLocation") or opening.get("location") or {}
    loc_text = ", ".join(str(v) for v in (loc.get("city"), loc.get("country")) if v) \
        if isinstance(loc, dict) else str(loc)
    fmt = "удалёнка" if "remote" in str(opening.get("employmentType", "")).lower() else ""
    return {"description": desc, "salary": opening.get("compensation") or "",
            "location": loc_text, "fmt": fmt}


def _fetch_jobvite(page: str):
    m = re.search(r'<div[^>]+class="[^"]*jv-job-detail-description[^"]*"[^>]*>(.*?)</div>\s*'
                  r'(?:<div|<section|</main)', page, re.S | re.I)
    return _clean_html(m.group(1)) if m else ""


def fetch_details(url: str):
    """→ dict(description, salary, location, fmt) или None, если не достали."""
    for adapter in (_fetch_workday, _fetch_bamboohr):
        got = adapter(url)
        if got and len(got["description"]) >= ACCEPT_DESC:
            return got
    try:
        page = _fetch_html(url)
    except Exception:
        return None
    result = {"description": "", "salary": "", "location": "", "fmt": ""}
    posting = _jsonld_posting(page)
    if posting:
        result["description"] = _clean_html(posting.get("description", ""))
        result["salary"] = _posting_salary(posting)
        result["location"] = _posting_location(posting)
        jlt = posting.get("jobLocationType") or ""
        if "TELECOMMUTE" in str(jlt).upper():
            result["fmt"] = "удалёнка"
    if len(result["description"]) < ACCEPT_DESC and "jobvite.com" in url:
        candidate = _fetch_jobvite(page)
        if len(candidate) > len(result["description"]):
            result["description"] = candidate
    if len(result["description"]) < ACCEPT_DESC:
        m = re.search(r'<meta[^>]+(?:property="og:description"|name="description")[^>]+'
                      r'content="([^"]{100,})"', page, re.I)
        if m:
            candidate = _clean_html(m.group(1))
            if len(candidate) > len(result["description"]):
                result["description"] = candidate
    return result if len(result["description"]) >= ACCEPT_DESC else None


def enrich_missing(db, Job, limit: int = 120, delay: float = FETCH_DELAY,
                   log=print) -> dict:
    """Обогатить вакансии без описания; безнадёжные снять с публикации."""
    jobs = (db.query(Job).filter(Job.status == "approved", Job.source != "",
                                 Job.source_url != "")
            .order_by(Job.created_at.desc()).all())
    todo = [j for j in jobs if needs_enrichment(j)][:limit]
    enriched = rejected = 0
    for i, job in enumerate(todo):
        details = fetch_details(job.source_url)
        if details:
            job.description = details["description"]
            if details["salary"] and not any(ch.isdigit() for ch in (job.salary or "")):
                job.salary = details["salary"]
            elif not any(ch.isdigit() for ch in (job.salary or "")):
                found = format_salary(parse_salary(details["description"]))
                if found:
                    job.salary = found
            if details["location"] and not (job.location or "").strip():
                job.location = details["location"]
            if details["fmt"] and job.fmt != details["fmt"]:
                job.fmt = details["fmt"]
            job.tags = derive_tags(job.title, job.description, job.tags)
            enriched += 1
        else:
            # источник не отдал содержательного описания — с борда снимаем
            job.status = "rejected"
            job.closed_at = datetime.utcnow().date().isoformat()
            rejected += 1
        if i % 50 == 49:
            db.commit()
            log(f"[enrich] {i + 1}/{len(todo)}: +{enriched} обогащено, -{rejected} снято")
        time.sleep(delay)
    db.commit()
    # теги для тех, у кого описание есть, а тегов нет — без походов в сеть
    tagged = 0
    for job in jobs:
        if job.status == "approved" and not (job.tags or "").strip() \
                and len((job.description or "")) >= MIN_DESC:
            new_tags = derive_tags(job.title, job.description)
            if new_tags:
                job.tags = new_tags
                tagged += 1
    db.commit()
    summary = {"checked": len(todo), "enriched": enriched, "rejected": rejected,
               "tagged": tagged}
    log(f"[enrich] готово: {summary}")
    return summary


if __name__ == "__main__":
    import sys
    sys.path.insert(0, __file__.rsplit("/server/", 1)[0])
    from server.app import SessionLocal, Job
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    enrich_missing(SessionLocal(), Job, limit=limit)
