"""Программные кластеры вакансий: страна × направление × язык.

Страницы вида /jobs/malta, /jobs/malta/compliance-aml, /jobs/remote/game-development,
/jobs/german-speaking — это то, что поисковики и ИИ-ассистенты берут в ответ на
«igaming jobs in Malta salary» или «работа в iGaming в Варшаве». Каждая страница
отвечает первым абзацем живыми цифрами из индекса, показывает вакансии, компании,
профессии с вилками и три вопроса-ответа. Тонкие срезы (меньше MIN_JOBS вакансий)
не существуют: отдают 404 и не попадают в sitemap.
"""
import re
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from server import app as core

router = APIRouter()

MIN_JOBS = 3
CACHE_SECONDS = 600

FAMILY_SLUGS = {
    "Операции казино": "casino-operations", "Беттинг и трейдинг": "betting-trading",
    "Разработка игр": "game-development", "Аффилейты и медиабаинг": "affiliates-media-buying",
    "Комплаенс и AML": "compliance-aml", "Платежи и антифрод": "payments-antifraud",
    "Поддержка игроков": "player-support", "Маркетинг и CRM": "marketing-crm",
    "Данные и BI": "data-bi", "Финансы, право и HR": "finance-legal-hr", "Топ-менеджмент": "executive",
}
FAMILY_BY_SLUG = {v: k for k, v in FAMILY_SLUGS.items()}
LANG_SLUGS = {code: f"{name}-speaking" for code, name in (
    ("en", "english"), ("uk", "ukrainian"), ("ru", "russian"), ("de", "german"),
    ("es", "spanish"), ("fr", "french"), ("pt", "portuguese"), ("pl", "polish"))}
LANG_BY_SLUG = {v: k for k, v in LANG_SLUGS.items()}
LANG_LABEL_EN = {"en": "English", "uk": "Ukrainian", "ru": "Russian", "de": "German",
                 "es": "Spanish", "fr": "French", "pt": "Portuguese", "pl": "Polish"}
LANG_LABEL_RU = {"en": "английским", "uk": "украинским", "ru": "русским", "de": "немецким",
                 "es": "испанским", "fr": "французским", "pt": "португальским", "pl": "польским"}
# «на Мальте», «в Польше» — предлог и падеж для русского заголовка
RU_IN = {
    "Мальта": "на Мальте", "Кипр": "на Кипре", "Польша": "в Польше", "Украина": "в Украине",
    "Великобритания": "в Великобритании", "Гибралтар": "в Гибралтаре", "Румыния": "в Румынии",
    "Болгария": "в Болгарии", "Греция": "в Греции", "Испания": "в Испании", "Португалия": "в Португалии",
    "Германия": "в Германии", "Бразилия": "в Бразилии", "США": "в США", "Канада": "в Канаде",
    "Грузия": "в Грузии", "Армения": "в Армении", "Сербия": "в Сербии", "Филиппины": "на Филиппинах",
    "Индия": "в Индии", "ЮАР": "в ЮАР", "ОАЭ": "в ОАЭ", "Швеция": "в Швеции", "Латвия": "в Латвии",
    "Эстония": "в Эстонии", "Литва": "в Литве", "Нидерланды": "в Нидерландах", "Ирландия": "в Ирландии",
    "Италия": "в Италии", "Мексика": "в Мексике", "Колумбия": "в Колумбии", "Перу": "в Перу",
    "Чили": "в Чили", "Аргентина": "в Аргентине", "Турция": "в Турции", "Австралия": "в Австралии",
    "Китай": "в Китае", "Япония": "в Японии", "Казахстан": "в Казахстане", "Удалёнка": "удалённо",
}
# регион зарплатных вилок картотеки для страны
MT_CY = {"Мальта", "Кипр", "Гибралтар", "Великобритания", "Ирландия", "Нидерланды", "Швеция", "Германия", "Испания", "Италия", "Португалия"}
REMOTE_BAND = {"Удалёнка", "Грузия", "Армения", "Украина", "Казахстан", "Сербия", "Филиппины", "Индия", "Бразилия", "Мексика", "Колумбия", "Перу", "Чили", "Аргентина", "Турция"}


_NOT_COUNTRIES = {"Не указана", "офис", "удалёнка", "гибрид", "не указан", "Другое"}


def country_slug(ru_name: str) -> str:
    en = core.COUNTRY_EN.get(ru_name)
    if not en or ru_name in _NOT_COUNTRIES:
        return ""
    return re.sub(r"[^a-z0-9]+", "-", en.lower()).strip("-")


COUNTRY_BY_SLUG = {country_slug(ru): ru for ru in core.COUNTRY_EN if country_slug(ru)}

_index = {"at": 0.0, "data": None}


def _build_index(db: Session) -> dict:
    jobs = db.query(core.Job).filter(core.Job.status == "approved").all()
    by_country: dict[str, list] = {}
    by_lang: dict[str, list] = {}
    for job in jobs:
        by_country.setdefault(core.country_of(job.location), []).append(job)
        for code, _label in job.language_list:
            by_lang.setdefault(code, []).append(job)
    return {"jobs": jobs, "by_country": by_country, "by_lang": by_lang}


def index(db: Session) -> dict:
    now = time.time()
    if _index["data"] is None or now - _index["at"] > CACHE_SECONDS:
        _index["data"] = _build_index(db)
        _index["at"] = now
    return _index["data"]


def _cluster_jobs(db: Session, country: str = "", family: str = "", lang_code: str = ""):
    data = index(db)
    if lang_code:
        rows = data["by_lang"].get(lang_code, [])
    elif country:
        rows = data["by_country"].get(country, [])
    else:
        rows = data["jobs"]
    if family:
        rows = [j for j in rows if (j.category or "") == family]
    return rows


def _summary(rows) -> dict:
    week_ago = datetime.utcnow() - timedelta(days=7)
    fresh = 0
    remote = 0
    with_salary = 0
    companies: dict[str, dict] = {}
    families: dict[str, int] = {}
    countries: dict[str, int] = {}
    for job in rows:
        posted = job.posted_at if re.match(r"^\d{4}-\d{2}-\d{2}$", job.posted_at or "") else ""
        published = datetime.fromisoformat(posted) if posted else job.created_at
        if published and published >= week_ago:
            fresh += 1
        if (job.fmt or "") == "удалёнка":
            remote += 1
        if job.has_salary:
            with_salary += 1
        slot = companies.setdefault(job.company_slug, {"slug": job.company_slug, "name": job.company_name,
                                                        "jobs": 0, "logo": job.logo_url, "initials": job.initials})
        slot["jobs"] += 1
        families[job.category or "Другое"] = families.get(job.category or "Другое", 0) + 1
        countries[core.country_of(job.location)] = countries.get(core.country_of(job.location), 0) + 1
    total = len(rows)
    return {
        "total": total, "fresh": fresh, "remote": remote,
        "remote_pct": round(remote * 100 / total) if total else 0,
        "with_salary": with_salary, "salary_pct": round(with_salary * 100 / total) if total else 0,
        "companies": sorted(companies.values(), key=lambda c: (-c["jobs"], c["name"].lower())),
        "families": sorted(families.items(), key=lambda kv: -kv[1]),
        "countries": sorted(((c, n) for c, n in countries.items() if country_slug(c)), key=lambda kv: -kv[1]),
    }


def _band_region(country: str) -> str:
    if country in MT_CY:
        return "mt_cy"
    if country in REMOTE_BAND:
        return "remote"
    return "eu"


def _professions_for(db: Session, family: str, country: str, lang: str, limit: int = 4) -> list:
    region = _band_region(country) if country else "mt_cy"
    out = []
    for role in core.professions_data(lang)["roles"]:
        base_role = core.profession_by_slug(role["slug"])  # семья в каноне — русская
        if family and base_role["family"] != family:
            continue
        band = role["salary"].get(region) or role["salary"]["mt_cy"]
        mid = band["middle"]
        out.append({"slug": role["slug"], "title": role["title"], "title_en": role["title_en"],
                    "family": role["family"],
                    "band": f"€{mid[0]:,}–{mid[1]:,}".replace(",", " "),
                    "jobs": core.role_jobs_count(db, role)})
    out.sort(key=lambda r: -r["jobs"])
    return out[:limit]


def describe(kind: str, country: str, family: str, lang_code: str, lang: str) -> dict:
    """Названия для заголовков: страна/направление/язык на языке страницы."""
    en = lang != "ru"
    fam_name = core.loc_name(family, "en") if (family and en) else family
    # title — для <h1>; phrase — для середины предложения («… открыто N вакансий iGaming на Мальте»)
    if kind == "lang":
        where_en = f"{LANG_LABEL_EN[lang_code]}-speaking"
        where_ru = f"со знанием {LANG_LABEL_RU[lang_code]}"
        title_en = f"{where_en} iGaming jobs" + (f" in {fam_name}" if family else "")
        title_ru = (f"Вакансии iGaming {where_ru}" if not family else f"{family}: вакансии iGaming {where_ru}")
        phrase_en = f"iGaming positions for {where_en} candidates" + (f" in {fam_name}" if family else "")
        phrase_ru = f"вакансий iGaming {where_ru}" + (f" в направлении «{family}»" if family else "")
    elif kind == "family":
        title_en = f"{fam_name} jobs in iGaming"
        title_ru = f"{family}: вакансии в iGaming"
        phrase_en = f"iGaming positions in {fam_name}"
        phrase_ru = f"вакансий iGaming в направлении «{family}»"
    else:
        c_en = core.COUNTRY_EN.get(country, country)
        c_ru = RU_IN.get(country, f"в {country}")
        if country == "Удалёнка":
            title_en = f"Remote {fam_name} jobs in iGaming" if family else "Remote iGaming jobs"
            title_ru = f"{family}: удалённые вакансии iGaming" if family else "Удалённые вакансии iGaming"
            phrase_en = "remote iGaming positions" + (f" in {fam_name}" if family else "")
            phrase_ru = "удалённых вакансий iGaming" + (f" в направлении «{family}»" if family else "")
        else:
            title_en = (f"{fam_name} jobs in {c_en} (iGaming)" if family else f"iGaming jobs in {c_en}")
            title_ru = (f"{family}: вакансии iGaming {c_ru}" if family else f"Вакансии iGaming {c_ru}")
            phrase_en = f"iGaming positions in {c_en}" + (f" in {fam_name}" if family else "")
            phrase_ru = f"вакансий iGaming {c_ru}" + (f" в направлении «{family}»" if family else "")
    return {"title": title_en if en else title_ru, "phrase": phrase_en if en else phrase_ru,
            "family_name": fam_name,
            "country_name": core.COUNTRY_EN.get(country, country) if en else country}


def _page(request: Request, db: Session, kind: str, country: str = "", family: str = "", lang_code: str = ""):
    rows = _cluster_jobs(db, country=country, family=family, lang_code=lang_code)
    if len(rows) < MIN_JOBS:
        raise HTTPException(404)
    lang = core.request_lang(request)
    summary = _summary(rows)
    rows_sorted = sorted(rows, key=lambda j: (not j.featured, -(j.created_at.timestamp() if j.created_at else 0)))
    cards = core._landing_pick(rows_sorted, 8)
    today = datetime.utcnow().date()
    names = describe(kind, country, family, lang_code, lang)
    # ссылки на соседние срезы
    if kind == "country":
        base = f"/jobs/{country_slug(country)}"
    elif kind == "lang":
        base = f"/jobs/{LANG_SLUGS[lang_code]}"
    else:
        base = f"/jobs/{FAMILY_SLUGS[family]}"
    family_links = [] if kind == "family" else [
        (f"{base}/{FAMILY_SLUGS[f]}" if kind in ("country", "lang") else f"/jobs/{FAMILY_SLUGS[f]}",
         core.loc_name(f, "en") if lang != "ru" else f, n)
        for f, n in summary["families"] if f in FAMILY_SLUGS and n >= MIN_JOBS and f != family]
    country_links = [(f"/jobs/{country_slug(c)}" + (f"/{FAMILY_SLUGS[family]}" if family else ""),
                      core.COUNTRY_EN.get(c, c) if lang != "ru" else c, n)
                     for c, n in summary["countries"] if n >= MIN_JOBS][:14]
    if kind == "country" and not family:
        country_links = [(p, n_, c_) for p, n_, c_ in country_links if p != base][:12]
    if kind == "country" and family:
        # тот же срез в других странах — без текущей
        country_links = [row for row in country_links if row[0] != f"{base}/{FAMILY_SLUGS[family]}"][:12]
    all_link = "/jobs?"
    if kind == "lang":
        all_link += f"lang={lang_code}"
    elif country == "Удалёнка":
        all_link += "fmt=remote"
    else:
        all_link += f"q={core.COUNTRY_EN.get(country, country)}"
    if family:
        all_link += f"&cat={family}"
    path = request.scope.get("path") or "/jobs"
    professions = _professions_for(db, family, country, lang)
    en = lang != "ru"
    region_label = core.professions_data(lang)["regions"].get(_band_region(country) if country else "mt_cy", "")
    n_companies = len(summary["companies"])
    fam_top = ", ".join(f"{name} ({n})" for _, name, n in family_links[:3])
    prof_line = ", ".join(f"{p['title']} {p['band']}" for p in professions)
    faq = [
        ((f"How many {names['phrase']} are open right now?" if en
          else f"Сколько сейчас открыто {names['phrase']}?"),
         (f"As of {core.human_date(today, lang)}, SpinHire lists {summary['total']} open positions at "
          f"{n_companies} companies; {summary['fresh']} were added in the last 7 days. The index is refreshed every 6 hours."
          if en else
          f"На {core.human_date(today, lang)} на SpinHire открыто {summary['total']} позиций у {n_companies} компаний, "
          f"{summary['fresh']} появились за последние 7 дней. Индекс обновляется каждые 6 часов.")),
        (("Which departments hire most?" if en else "Какие направления нанимают больше всего?"),
         ((f"Largest departments: {fam_top}." if fam_top else f"This page covers one department: {names['family_name']}.")
          if en else
          (f"Больше всего вакансий в направлениях: {fam_top}." if fam_top else f"Эта страница — одно направление: {family}."))),
        (("What do these roles pay?" if en else "Сколько платят на этих позициях?"),
         (f"Only {summary['salary_pct']}% of postings publish a salary. SpinHire mid-level benchmark ({region_label}): {prof_line} per month."
          if en else
          f"Зарплату публикуют лишь {summary['salary_pct']}% объявлений. Ориентир SpinHire для middle ({region_label}): {prof_line} в месяц.")),
    ]
    schema_collection = {
        "@context": "https://schema.org", "@type": "CollectionPage", "name": names["title"],
        "url": f"https://spinhire.io{path}", "dateModified": today.isoformat(),
        "isPartOf": {"@type": "WebSite", "name": "SpinHire", "url": "https://spinhire.io/"},
        "mainEntity": {"@type": "ItemList", "numberOfItems": summary["total"],
                       "itemListElement": [{"@type": "ListItem", "position": i + 1,
                                            "url": f"https://spinhire.io/job/{j.id}", "name": j.title}
                                           for i, j in enumerate(cards)]},
    }
    schema_breadcrumbs = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home" if en else "Главная", "item": "https://spinhire.io/"},
            {"@type": "ListItem", "position": 2, "name": "Jobs" if en else "Вакансии", "item": "https://spinhire.io/jobs"},
            {"@type": "ListItem", "position": 3, "name": names["title"], "item": f"https://spinhire.io{path}"}],
    }
    schema_faq = {"@context": "https://schema.org", "@type": "FAQPage",
                  "mainEntity": [{"@type": "Question", "name": q,
                                  "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
    return core.render(request, db, "cluster.html",
                       schema_collection=schema_collection, schema_breadcrumbs=schema_breadcrumbs,
                       schema_faq=schema_faq, faq=faq,
                       kind=kind, country=country, family=family, lang_code=lang_code,
                       names=names, s=summary, jobs=cards, total=summary["total"],
                       professions=professions,
                       family_links=family_links, country_links=country_links,
                       all_link=all_link, path=path,
                       today=today.isoformat(), today_human=core.human_date(today, lang),
                       band_region=_band_region(country) if country else "mt_cy",
                       region_label=region_label)


@router.get("/jobs/browse", response_class=HTMLResponse)
def browse(request: Request, db: Session = Depends(core.db_session)):
    """Хаб всех срезов: по странам, направлениям и языкам — точка входа для краулеров."""
    lang = core.request_lang(request)
    data = index(db)
    en = lang != "ru"
    countries = [(f"/jobs/{country_slug(c)}", core.COUNTRY_EN.get(c, c) if en else c, len(rows))
                 for c, rows in data["by_country"].items() if country_slug(c) and len(rows) >= MIN_JOBS]
    countries.sort(key=lambda r: -r[2])
    families = []
    for fam, slug in FAMILY_SLUGS.items():
        n = sum(1 for j in data["jobs"] if (j.category or "") == fam)
        if n >= MIN_JOBS:
            families.append((f"/jobs/{slug}", core.loc_name(fam, "en") if en else fam, n))
    families.sort(key=lambda r: -r[2])
    langs = [(f"/jobs/{LANG_SLUGS[code]}", LANG_LABEL_EN[code] if en else core.LANG_LABELS.get(code, code), len(rows))
             for code, rows in data["by_lang"].items() if code in LANG_SLUGS and len(rows) >= MIN_JOBS]
    langs.sort(key=lambda r: -r[2])
    # страна × направление — только живые пары
    matrix = []
    for c, rows in sorted(data["by_country"].items(), key=lambda kv: -len(kv[1])):
        if not country_slug(c) or len(rows) < MIN_JOBS:
            continue
        cells = []
        for fam, slug in FAMILY_SLUGS.items():
            n = sum(1 for j in rows if (j.category or "") == fam)
            if n >= MIN_JOBS:
                cells.append((f"/jobs/{country_slug(c)}/{slug}", core.loc_name(fam, "en") if en else fam, n))
        if cells:
            matrix.append((core.COUNTRY_EN.get(c, c) if en else c, f"/jobs/{country_slug(c)}", cells))
    return core.render(request, db, "cluster_browse.html", countries=countries, families=families,
                       langs=langs, matrix=matrix[:20], total=len(data["jobs"]))


@router.get("/jobs/{first}", response_class=HTMLResponse)
def cluster_one(first: str, request: Request, db: Session = Depends(core.db_session)):
    if first in LANG_BY_SLUG:
        return _page(request, db, "lang", lang_code=LANG_BY_SLUG[first])
    if first in FAMILY_BY_SLUG:
        return _page(request, db, "family", family=FAMILY_BY_SLUG[first])
    if first in COUNTRY_BY_SLUG:
        return _page(request, db, "country", country=COUNTRY_BY_SLUG[first])
    raise HTTPException(404)


@router.get("/jobs/{first}/{second}", response_class=HTMLResponse)
def cluster_two(first: str, second: str, request: Request, db: Session = Depends(core.db_session)):
    if second not in FAMILY_BY_SLUG:
        raise HTTPException(404)
    family = FAMILY_BY_SLUG[second]
    if first in COUNTRY_BY_SLUG:
        return _page(request, db, "country", country=COUNTRY_BY_SLUG[first], family=family)
    if first in LANG_BY_SLUG:
        return _page(request, db, "lang", lang_code=LANG_BY_SLUG[first], family=family)
    raise HTTPException(404)


def sitemap_paths(db: Session) -> list[str]:
    """Все живые срезы для sitemap (без ведущего слэша)."""
    data = index(db)
    out = ["jobs/browse"]
    for c, rows in data["by_country"].items():
        slug = country_slug(c)
        if not slug or len(rows) < MIN_JOBS:
            continue
        out.append(f"jobs/{slug}")
        for fam, fslug in FAMILY_SLUGS.items():
            if sum(1 for j in rows if (j.category or "") == fam) >= MIN_JOBS:
                out.append(f"jobs/{slug}/{fslug}")
    for fam, fslug in FAMILY_SLUGS.items():
        if sum(1 for j in data["jobs"] if (j.category or "") == fam) >= MIN_JOBS:
            out.append(f"jobs/{fslug}")
    for code, rows in data["by_lang"].items():
        if code in LANG_SLUGS and len(rows) >= MIN_JOBS:
            out.append(f"jobs/{LANG_SLUGS[code]}")
    return out
