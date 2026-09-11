# -*- coding: utf-8 -*-
"""XML-фиды вакансий для внешних агрегаторов (Jooble, Careerjet, Adzuna, Talent.com…).

Формат — «Indeed XML»: он стал де-факто стандартом, и его читают почти все
агрегаторы, поэтому один файл закрывает сразу всех партнёров. Рядом лежит
RSS 2.0 — его просят каталоги джоб-бордов и телеграм-боты.

Каждому партнёру выдаём свою ссылку с ?src=<слаг>: так в аналитике видно, кто
сколько трафика привёл, и одного можно отключить, не трогая остальных.

Подключается в конце app.py:  from server import feeds; app.include_router(feeds.router)
"""
import html
import re
import time
from datetime import datetime, timezone
from email.utils import format_datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from server import terms
from server.app import COUNTRY_EN, COUNTRY_ISO, Job, country_of, db_session

router = APIRouter()

SITE = "https://spinhire.io"

# Слаг партнёра уходит в utm_source, поэтому список закрытый: иначе любой
# желающий проставит нам в аналитике произвольную метку.
PARTNERS = {
    "jooble", "careerjet", "adzuna", "talent", "jobsora", "jora", "whatjobs",
    "neuvoo", "trovit", "jobrapido", "joblift", "jobboardsearch", "test",
}

FEED_TTL = 1800      # полчаса: агрегатор забирает фид раз в сутки, чаще незачем
MIN_DESC = 160       # тонкие описания агрегаторы отклоняют целым фидом
MAX_DESC = 12000
RSS_LIMIT = 200

# Indeed-словарь типов занятости; наш employment_type уже в терминах schema.org
JOBTYPE = {"FULL_TIME": "fulltime", "PART_TIME": "parttime", "CONTRACTOR": "contract",
           "INTERN": "internship", "TEMPORARY": "temporary"}

_NOT_A_CITY = {"remote", "remote job", "удалёнка", "удаленка", "worldwide", "anywhere",
               "eu", "europe", "европа", "не указана", "various", "multiple locations"}

_cache: dict = {}


def _cached(key: tuple, build):
    """Фид тяжёлый (тысячи вакансий с полными описаниями) — держим его в памяти."""
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < FEED_TTL:
        return hit[1]
    value = build()
    _cache[key] = (time.time(), value)
    return value


def _cdata(value: str) -> str:
    """Внутри CDATA опасна одна последовательность — закрывающая."""
    return "<![CDATA[" + (value or "").replace("]]>", "]]&gt;") + "]]>"


def _description_html(text: str) -> str:
    """Описания лежат простым текстом, а агрегаторы ждут HTML."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text or "") if b.strip()]
    out = []
    for block in blocks:
        lines = [html.escape(line.strip()) for line in block.split("\n") if line.strip()]
        if lines:
            out.append("<p>" + "<br/>".join(lines) + "</p>")
    return "".join(out)[:MAX_DESC]


def _city_of(job) -> str:
    """Город из свободной строки локации: всё, что не страна и не «удалёнка»."""
    country = country_of(job.location)
    country_names = {country.lower(), (COUNTRY_EN.get(country) or "").lower()}
    for part in re.split(r"[,|/]", job.location or ""):
        part = part.strip()
        if part and part.lower() not in country_names and part.lower() not in _NOT_A_CITY:
            return part
    return ""


def _rfc822(job) -> str:
    raw = job.posted_at if re.match(r"^\d{4}-\d{2}-\d{2}$", job.posted_at or "") else ""
    if raw:
        stamp = datetime.strptime(raw, "%Y-%m-%d")
    else:
        stamp = job.created_at or datetime.utcnow()
    return format_datetime(stamp.replace(tzinfo=timezone.utc))


def _job_url(job, src: str, lang: str) -> str:
    base = f"{SITE}/job/{job.id}" if lang == "ru" else f"{SITE}/{lang}/job/{job.id}"
    if not src:
        return base
    return f"{base}?utm_source={src}&utm_medium=feed&utm_campaign=jobs"


def _is_remote(job) -> bool:
    return (job.fmt or "") in ("удалёнка", "удалёнка ЕС")


def _feed_jobs(db: Session, limit: int):
    """Живые вакансии, пригодные для агрегатора.

    Отсекаем две категории, из-за которых фиды отклоняют: «тонкие» описания и
    вакансии, у которых не определились ни страна, ни город, ни удалёнка —
    агрегатор раскладывает объявления по географии, и такие ему некуда деть.
    """
    query = (db.query(Job).filter(Job.status == "approved")
             .order_by(Job.featured.desc(), Job.id.desc()))
    out = []
    for job in query:
        if len((job.description or "").strip()) < MIN_DESC:
            continue
        if not (COUNTRY_ISO.get(country_of(job.location), "") or _is_remote(job)
                or _city_of(job)):
            continue
        out.append(job)
        if limit and len(out) >= limit:
            break
    return out


def _en(value: str) -> str:
    """Направление/формат по-английски — партнёрам ru-названия ни о чём не говорят."""
    return terms.TERMS.get("en", {}).get(value, value)


def _build_indeed(db: Session, src: str, lang: str, limit: int) -> str:
    rows = ['<?xml version="1.0" encoding="utf-8"?>', "<source>",
            f"  <publisher>{_cdata('SpinHire')}</publisher>",
            f"  <publisherurl>{_cdata(SITE)}</publisherurl>",
            f"  <lastBuildDate>{_cdata(format_datetime(datetime.now(timezone.utc)))}</lastBuildDate>"]
    for job in _feed_jobs(db, limit):
        country = country_of(job.location)
        remote = _is_remote(job)
        # у удалённой вакансии города нет, а пустое поле агрегатор принимает
        # за брак — подставляем то слово, которое он умеет разбирать
        city = _city_of(job) or ("Remote" if remote else "")
        item = [
            "  <job>",
            f"    <title>{_cdata(job.title)}</title>",
            f"    <date>{_cdata(_rfc822(job))}</date>",
            f"    <referencenumber>{_cdata(str(job.id))}</referencenumber>",
            f"    <url>{_cdata(_job_url(job, src, lang))}</url>",
            f"    <company>{_cdata(job.company_name or 'iGaming')}</company>",
            f"    <city>{_cdata(city)}</city>",
            f"    <state>{_cdata('')}</state>",
            f"    <country>{_cdata(COUNTRY_ISO.get(country, ''))}</country>",
            f"    <description>{_cdata(_description_html(job.description))}</description>",
            f"    <jobtype>{_cdata(JOBTYPE.get(job.employment_type, 'fulltime'))}</jobtype>",
            f"    <category>{_cdata(_en(job.category))}</category>",
            f"    <expirationdate>{_cdata(job.valid_through)}</expirationdate>",
            f"    <remote>{_cdata('1' if remote else '0')}</remote>",
        ]
        if job.has_salary:
            item.append(f"    <salary>{_cdata(job.salary)}</salary>")
            if job.sal_min:
                item.append(f"    <salarymin>{_cdata(str(job.sal_min))}</salarymin>")
            if job.sal_max:
                item.append(f"    <salarymax>{_cdata(str(job.sal_max))}</salarymax>")
            item.append(f"    <salarycurrency>{_cdata(job.sal_currency)}</salarycurrency>")
            if job.sal_unit:
                item.append(f"    <salaryperiod>{_cdata(job.sal_unit.lower())}</salaryperiod>")
        item.append("  </job>")
        rows.extend(item)
    rows.append("</source>")
    return "\n".join(rows) + "\n"


def _build_rss(db: Session, src: str, lang: str, limit: int) -> str:
    title = "SpinHire — вакансии iGaming" if lang == "ru" else "SpinHire — iGaming jobs"
    home = SITE if lang == "ru" else f"{SITE}/{lang}"
    rows = ['<?xml version="1.0" encoding="utf-8"?>',
            '<rss version="2.0"><channel>',
            f"  <title>{html.escape(title)}</title>",
            f"  <link>{html.escape(home)}</link>",
            f"  <description>{html.escape('Свежие вакансии iGaming: операторы, провайдеры, аффилейты.' if lang == 'ru' else 'Fresh iGaming jobs: operators, providers, affiliates.')}</description>",
            f"  <language>{lang}</language>",
            f"  <lastBuildDate>{format_datetime(datetime.now(timezone.utc))}</lastBuildDate>"]
    for job in _feed_jobs(db, limit or RSS_LIMIT):
        url = _job_url(job, src, lang)
        where = job.location or ("Удалёнка" if lang == "ru" else "Remote")
        rows += [
            "  <item>",
            f"    <title>{html.escape(f'{job.title} — {job.company_name} ({where})')}</title>",
            f"    <link>{html.escape(url)}</link>",
            f'    <guid isPermaLink="true">{html.escape(url)}</guid>',
            f"    <pubDate>{_rfc822(job)}</pubDate>",
            f"    <category>{html.escape(_en(job.category))}</category>",
            f"    <description>{_cdata(_description_html(job.description))}</description>",
            "  </item>",
        ]
    rows.append("</channel></rss>")
    return "\n".join(rows) + "\n"


def _src(value: str) -> str:
    value = (value or "").strip().lower()
    return value if value in PARTNERS else ""


def _lang(value: str) -> str:
    from server.app import PATH_LANGS
    value = (value or "ru").strip().lower()
    return value if value == "ru" or value in PATH_LANGS else "ru"


def _xml(body: str) -> Response:
    return Response(body, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=1800"})


@router.get("/feed/jobs.xml")
def feed_jobs(src: str = Query(""), lang: str = Query("en"), limit: int = Query(0, ge=0, le=20000),
              db: Session = Depends(db_session)):
    """Фид для агрегаторов. По умолчанию англоязычные страницы — партнёры мировые."""
    src, lang = _src(src), _lang(lang)
    return _xml(_cached(("indeed", src, lang, limit), lambda: _build_indeed(db, src, lang, limit)))


@router.get("/feed/rss.xml")
def feed_rss(src: str = Query(""), lang: str = Query("ru"), limit: int = Query(RSS_LIMIT, ge=1, le=1000),
             db: Session = Depends(db_session)):
    """RSS свежих вакансий — для каталогов джоб-бордов и читалок."""
    src, lang = _src(src), _lang(lang)
    return _xml(_cached(("rss", src, lang, limit), lambda: _build_rss(db, src, lang, limit)))
