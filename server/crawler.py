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
import os
import re
import sys
import threading
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse

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

# Официальные партнёрские JSON-фиды. URL хранятся только в секретах сервера.
# Ожидаемый формат: список вакансий либо {"jobs": [...]}.
PARTNER_FEEDS = {
    "grc.ua": os.environ.get("GRC_JOBS_FEED_URL", ""),
    "work.ua": os.environ.get("WORKUA_JOBS_FEED_URL", ""),
    "robota.ua": os.environ.get("ROBOTAUA_JOBS_FEED_URL", ""),
}

# Источники с JobPosting JSON-LD на странице листинга (url: (имя, source-ключ))
JSONLD_LISTINGS = {
    "https://djinni.co/jobs/?company_type=gambling":
        ("Djinni · gambling (UA)", "djinni"),
}

# Реестр источников для отображения в админке (что настроено и статус)
SOURCE_REGISTRY = [
    {"key": "softswiss", "name": "SOFTSWISS", "type": "WordPress REST API",
     "status": "работает", "note": "Все опубликованные вакансии и полные описания (до 100 за запуск)"},
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
    {"key": "partner:grc.ua", "name": "GRC.UA", "type": "Партнёрский JSON-фид",
     "status": "подключён" if PARTNER_FEEDS["grc.ua"] else "нужен доступ",
     "note": "Сайт блокирует серверный сбор (403). Коннектор готов; нужен официальный feed URL от GRC.UA."},
    {"key": "partner:work.ua", "name": "Work.ua", "type": "Партнёрский JSON-фид",
     "status": "подключён" if PARTNER_FEEDS["work.ua"] else "нужен доступ",
     "note": "Sitemap доступен, страницы вакансий возвращают 403. Нужен официальный экспорт/API или письменное разрешение."},
    {"key": "partner:robota.ua", "name": "robota.ua", "type": "Партнёрский JSON-фид",
     "status": "подключён" if PARTNER_FEEDS["robota.ua"] else "нужен доступ",
     "note": "Сайт и внутренний API закрыты Cloudflare. Коннектор готов к официальному feed URL."},
    {"key": "hh.ru", "name": "HeadHunter (hh.ru / hh.ua)", "type": "Публичный API — требует настройки",
     "status": "не подключён", "note": "api.hh.ru бесплатный (зарплата+город+работодатель), но из облака отдаёт 403 — нужен зарегистрированный app-токен ИЛИ запуск с разрешённого IP. Покрывает RU/UA/СНГ. Готов подключить."},
    {"key": "casino-discovery", "name": "Казино: 9 рынков", "type": "Career/hiring discovery",
     "status": "подключён", "note": "2 134 бренда из Blask; ежедневный пакетный обход официальных career/job страниц"},
]

RESUME_SOURCE_REGISTRY = [
    {"key": "spinhire:profiles", "name": "Профили SpinHire", "type": "Собственная база",
     "status": "работает", "note": "Анкеты, которые кандидаты сами создали и разрешили показывать работодателям."},
    {"key": "anonymous:partners", "name": "Анонимные партнёрские профили", "type": "Opt-in API",
     "status": "не подключён", "note": "Подключается только при явном согласии кандидата на передачу. Имя, email и контакты не импортируются."},
    {"key": "public:resume-sites", "name": "Открытые базы резюме", "type": "Сбор отключён",
     "status": "запрещён", "note": "Автоматический сбор персональных резюме не запускаем без лицензии источника и согласия кандидатов."},
    {"key": "partner:work.ua:resumes", "name": "Work.ua · база резюме", "type": "Доступ работодателя",
     "status": "нужен договор", "note": "Просмотр части анкет возможен, контакты регулируются настройками кандидата и тарифом. Массовый перенос требует отдельного разрешения."},
    {"key": "partner:robota.ua:resumes", "name": "robota.ua · база резюме", "type": "Доступ работодателя",
     "status": "нужен договор", "note": "База доступна зарегистрированным работодателям; автоматическое копирование в SpinHire без лицензии не включаем."},
    {"key": "partner:grc.ua:resumes", "name": "GRC.UA · резюме", "type": "Партнёрский доступ",
     "status": "нужен договор", "note": "Профили создают сами кандидаты. Импорт возможен только через разрешённый API/feed и с согласием на передачу."},
]

UA = "SpinHireBot/1.0 (+https://spinhire.io; job aggregation)"
TIMEOUT = 25
MAX_PER_BOARD = 100          # крупные борды (SOFTSWISS сейчас 52) забираем целиком
DESC_LIMIT = 20000           # полное описание без обрезания обычных вакансий
SOFTSWISS_API = "https://careers.softswiss.com/wp-json/wp/v2/vacancy?per_page=100"
CASINO_SEEDS_PATH = Path(__file__).resolve().parent.parent / "data" / "casino-operators.json"
DISCOVERY_REPORT_PATH = Path(__file__).resolve().parent.parent / "data" / "casino-careers-report.json"
CAREER_WORDS = re.compile(r"(?i)(career|jobs?|vacanc|hiring|join[-_ ]?(us|team)|work[-_ ]?with[-_ ]?us)")
DISCOVERY_LOOKUPS_PER_RUN = int(os.environ.get("CASINO_DISCOVERY_LOOKUPS_PER_RUN", "40"))
SEARCH_EXCLUDED_HOSTS = ("linkedin.com", "facebook.com", "instagram.com", "wikipedia.org",
                         "casino.guru", "glassdoor.", "indeed.", "trustpilot.", "youtube.com")
_RUN_LOCK = threading.Lock()


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
        expanded = []
        while items:
            item = items.pop(0)
            if isinstance(item, list):
                items.extend(item)
            elif isinstance(item, dict):
                expanded.append(item)
                graph = item.get("@graph")
                if isinstance(graph, list):
                    items.extend(graph)
        items = expanded
        for it in items:
            types = it.get("@type") if isinstance(it, dict) else None
            types = types if isinstance(types, list) else [types]
            if not isinstance(it, dict) or "JobPosting" not in types:
                continue
            title = (it.get("title") or "").strip()
            if not title:
                continue
            org = it.get("hiringOrganization") or {}
            company = (org.get("name") if isinstance(org, dict) else "") or "iGaming-компания"
            desc = _clean_html(it.get("description", ""))
            u = str(it.get("url") or url)
            slug = u.rstrip("/").rsplit("/", 1)[-1]
            m = re.search(r"(\d+)", slug)
            ext = m.group(1) if m else slug[-80:]
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


def crawl_softswiss():
    """Все опубликованные вакансии SOFTSWISS из официального WordPress REST API."""
    jobs = json.loads(_fetch(SOFTSWISS_API))
    out = []
    for j in jobs:
        title = _clean_html((j.get("title") or {}).get("rendered", ""))
        description = _clean_html((j.get("content") or {}).get("rendered", ""))
        link = str(j.get("link") or "").strip()
        if not title or not description or not link:
            continue
        seo_title = str((j.get("yoast_head_json") or {}).get("title") or "")
        location = ""
        match = re.search(r"(?i)vacancy in (.+?)(?:\s*\|\s*SOFTSWISS|$)", seo_title)
        if match:
            location = match.group(1).replace(" & ", ", ").strip()
        out.append({
            "title": title, "company_name": "SOFTSWISS", "location": location,
            "fmt": _fmt_from(location, description),
            "tags": _tags_from(title, description, detect_lang(title, description)),
            "description": description, "source_url": link,
            "source": "softswiss", "ext_id": str(j.get("id") or j.get("slug") or link),
            "salary": "по запросу", "posted_at": str(j.get("date") or "")[:10],
            "deadline": "",
        })
    return out


def _links_from_html(page, base_url):
    """Абсолютные HTTP(S)-ссылки без mailto/javascript и дублей."""
    links = []
    for raw in re.findall(r'(?is)<a\b[^>]*?href=["\']([^"\']+)', page):
        url = urljoin(base_url, html.unescape(raw).strip()).split("#", 1)[0]
        if url.startswith(("http://", "https://")) and url not in links:
            links.append(url)
    return links


def discover_career_pages(homepage):
    """Найти career/hiring URL на официальном сайте и проверить типовые пути."""
    parsed = urlparse(homepage)
    root = f"{parsed.scheme or 'https'}://{parsed.netloc or parsed.path.strip('/')}"
    candidates = []
    try:
        page = _fetch_html(root)
        candidates.extend(url for url in _links_from_html(page, root) if CAREER_WORDS.search(url))
    except Exception:
        pass
    candidates.extend(urljoin(root + "/", path) for path in (
        "careers", "jobs", "vacancies", "about/careers", "company/careers", "join-us"))
    found = []
    for url in dict.fromkeys(candidates):
        try:
            page = _fetch_html(url)
        except Exception:
            continue
        text = _clean_html(page[:250000]).lower()
        if CAREER_WORDS.search(url) and any(word in text for word in ("job", "career", "vacan", "position", "role")):
            found.append(url)
        if len(found) >= 5:
            break
    return found


def discover_official_homepage(operator, country):
    """Найти вероятный официальный домен бренда; принять только домен с именем бренда."""
    brand = re.sub(r"[^a-z0-9]", "", operator.lower())
    brand = re.sub(r"(casino|bingo|betting)$", "", brand)
    if len(brand) < 4:
        return ""
    query = quote_plus(f'"{operator}" casino official {country}')
    page = _fetch_html(f"https://html.duckduckgo.com/html/?q={query}")
    for raw in re.findall(r'(?is)class="result__a"[^>]*href="([^"]+)"', page):
        link = html.unescape(raw)
        if link.startswith("//"):
            link = "https:" + link
        parsed = urlparse(link)
        if parsed.hostname == "duckduckgo.com":
            link = (parse_qs(parsed.query).get("uddg") or [""])[0]
            parsed = urlparse(link)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        compact_host = re.sub(r"[^a-z0-9]", "", host.split(".", 1)[0])
        if (parsed.scheme in ("http", "https") and host
                and not any(blocked in host for blocked in SEARCH_EXCLUDED_HOSTS)
                and (brand in compact_host or compact_host in brand)):
            return f"{parsed.scheme}://{host}/"
    return ""


def crawl_discovered_careers(seed):
    """Обойти подтверждённый сайт бренда, найти hiring-раздел и JobPosting-страницы."""
    company = str(seed.get("operator") or "").strip()
    homepage = str(seed.get("homepage") or "").strip()
    preset = str(seed.get("careers_url") or "").strip()
    pages = [preset] if preset else (discover_career_pages(homepage) if homepage else [])
    jobs = []
    checked = []
    for page_url in pages[:5]:
        try:
            listing = _fetch_html(page_url)
        except Exception:
            continue
        checked.append(page_url)
        jobs.extend(crawl_jsonld(page_url, f"discovered:{company}"))
        links = _links_from_html(listing, page_url)
        detail_links = [u for u in links if CAREER_WORDS.search(u)]
        greenhouse = set()
        lever = set()
        smart = set()
        for url in links:
            parsed = urlparse(url)
            parts = [p for p in parsed.path.split("/") if p]
            if parsed.hostname in ("boards.greenhouse.io", "job-boards.greenhouse.io") and parts:
                greenhouse.add(parts[0])
            elif parsed.hostname == "jobs.lever.co" and parts:
                lever.add(parts[0])
            elif parsed.hostname == "jobs.smartrecruiters.com" and parts:
                smart.add(parts[0])
        for board in greenhouse:
            try:
                jobs.extend(crawl_greenhouse(board, company))
            except Exception:
                pass
        for site in lever:
            try:
                jobs.extend(crawl_lever(site, company))
            except Exception:
                pass
        for company_id in smart:
            try:
                jobs.extend(crawl_smartrecruiters(company_id, company))
            except Exception:
                pass
        for detail_url in detail_links[:MAX_PER_BOARD]:
            try:
                jobs.extend(crawl_jsonld(detail_url, f"discovered:{company}"))
            except Exception:
                continue
    unique = {}
    for job in jobs:
        job["company_name"] = company or job["company_name"]
        unique[(job["source"], job["ext_id"])] = job
    return list(unique.values()), checked


def crawl_casino_seed_registry():
    """Пройти список казино Украины/UK; результаты обнаружения сохранить для аудита."""
    if not CASINO_SEEDS_PATH.exists():
        return []
    payload = json.loads(CASINO_SEEDS_PATH.read_text(encoding="utf-8"))
    records = payload.get("operators", []) if isinstance(payload, dict) else payload
    # Interleave countries by market rank so one large market cannot block all others.
    records = sorted(records, key=lambda row: (row.get("rank") or 10**9, row.get("country") or ""))
    previous = {}
    if DISCOVERY_REPORT_PATH.exists():
        try:
            old = json.loads(DISCOVERY_REPORT_PATH.read_text(encoding="utf-8"))
            old_rows = old.get("operators", []) if isinstance(old, dict) else old
            previous = {(row.get("country"), row.get("operator")): row for row in old_rows}
        except Exception:
            previous = {}
    all_jobs, report, lookups = [], [], 0
    for seed in records:
        prior = previous.get((seed.get("country"), seed.get("operator")), {})
        if not seed.get("homepage") and prior.get("homepage"):
            seed = {**seed, "homepage": prior["homepage"]}
        if not (seed.get("homepage") or seed.get("careers_url")):
            homepage = ""
            attempted = False
            retry_at = prior.get("next_retry_at", "")
            retry_due = not retry_at
            if retry_at:
                try:
                    retry_due = datetime.fromisoformat(retry_at.replace("Z", "+00:00")).replace(tzinfo=None) <= datetime.utcnow()
                except ValueError:
                    retry_due = True
            if retry_due and lookups < DISCOVERY_LOOKUPS_PER_RUN:
                lookups += 1
                attempted = True
                try:
                    homepage = discover_official_homepage(seed.get("operator", ""), seed.get("country", ""))
                except Exception:
                    homepage = ""
            if homepage:
                seed = {**seed, "homepage": homepage}
            else:
                status = "homepage_not_found" if attempted else "domain_pending"
                row = {"operator": seed.get("operator"), "country": seed.get("country"),
                       "status": status, "career_pages": [], "jobs": 0}
                if attempted:
                    row["next_retry_at"] = (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"
                elif retry_at:
                    row["next_retry_at"] = retry_at
                report.append(row)
                continue
        try:
            jobs, pages = crawl_discovered_careers(seed)
            all_jobs.extend(jobs)
            report.append({"operator": seed.get("operator"), "country": seed.get("country"),
                           "homepage": seed.get("homepage", ""),
                           "status": "jobs_found" if jobs else ("career_found" if pages else "not_found"),
                           "career_pages": pages, "jobs": len(jobs)})
        except Exception as exc:
            report.append({"operator": seed.get("operator"), "country": seed.get("country"),
                           "status": "error", "error": str(exc)[:160], "career_pages": [], "jobs": 0})
    summary = {}
    for row in report:
        summary[row["status"]] = summary.get(row["status"], 0) + 1
    output = {"generated_at": datetime.utcnow().isoformat() + "Z", "lookups_this_run": lookups,
              "summary": summary, "operators": report}
    DISCOVERY_REPORT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return all_jobs


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
            "company_name": company.strip(),
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
        detail = {}
        try:
            detail = json.loads(_fetch(
                f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings/{j.get('id')}"))
        except Exception as e:
            print(f"[crawl] smartrecruiters:{company_id}:{j.get('id')} detail FAILED: {str(e)[:100]}")
        sections = (((detail.get("jobAd") or {}).get("sections") or {})
                    if isinstance(detail, dict) else {})
        description_parts = []
        for section in sections.values():
            if not isinstance(section, dict):
                continue
            heading = str(section.get("title") or "").strip()
            text = str(section.get("text") or "").strip()
            if text:
                description_parts.append(f"{heading}\n{text}" if heading else text)
        desc = _clean_html("\n\n".join(description_parts))
        if not desc:
            desc = _clean_html(" ".join(filter(None, [title, dept])))
        source_url = detail.get("applyUrl") or j.get("ref", "")
        out.append({"title": title, "company_name": company, "location": loc,
                    "fmt": _fmt_from(loc, desc), "tags": _tags_from(f"{title} {dept}", desc),
                    "description": desc, "source_url": source_url,
                    "source": f"smartrecruiters:{company_id}", "ext_id": str(j.get("id", "")),
                    "salary": "по запросу", "posted_at": (j.get("releasedDate") or "")[:10], "deadline": ""})
    return out


def crawl_partner_feed(url, source):
    """Импортировать официальный JSON-фид партнёра без привязки к его схеме API."""
    data = json.loads(_fetch(url))
    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    if not isinstance(jobs, list):
        raise ValueError("partner feed must be a list or an object with jobs[]")
    out = []
    for j in jobs[:MAX_PER_BOARD]:
        if not isinstance(j, dict):
            continue
        title = str(j.get("title") or j.get("name") or "").strip()
        company = str(j.get("company_name") or j.get("company") or "").strip()
        link = str(j.get("url") or j.get("source_url") or "").strip()
        if not title or not link:
            continue
        location = str(j.get("location") or j.get("city") or "").strip()
        description = _clean_html(str(j.get("description") or j.get("content") or ""))
        ext_id = str(j.get("id") or j.get("external_id") or link[-80:])
        out.append({"title": title, "company_name": company or "iGaming-компания",
                    "location": location, "fmt": _fmt_from(location, description),
                    "tags": _tags_from(title, description), "description": description,
                    "source_url": link, "source": f"partner:{source}", "ext_id": ext_id,
                    "salary": str(j.get("salary") or "по запросу"),
                    "posted_at": str(j.get("posted_at") or j.get("date") or "")[:10],
                    "deadline": str(j.get("deadline") or "")[:10]})
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


def last_successful_run():
    """Return the last successful crawl timestamp, if the status file is valid."""
    status_path = Path(__file__).resolve().parent.parent / "data" / "crawler-status.json"
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
        if payload.get("ok") and payload.get("last_run"):
            return datetime.fromisoformat(payload["last_run"].replace("Z", "+00:00")).replace(tzinfo=None)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return None


def crawl_is_due(interval_hours=24):
    last_run = last_successful_run()
    return last_run is None or datetime.utcnow() - last_run >= timedelta(hours=interval_hours)


def collect(with_metadata=False):
    """Собрать вакансии со всех источников. Возвращает список dict."""
    items = []
    complete_sources = set()
    try:
        got = crawl_softswiss()
        items.extend(got)
        if len(got) < MAX_PER_BOARD:
            complete_sources.add("softswiss")
        print(f"[crawl] softswiss: +{len(got)}")
    except Exception as e:
        print(f"[crawl] softswiss FAILED: {str(e)[:120]}")
    for board, company in GREENHOUSE_BOARDS.items():
        try:
            got = crawl_greenhouse(board, company)
            items.extend(got)
            if len(got) < MAX_PER_BOARD:
                complete_sources.add(f"greenhouse:{board}")
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
            if len(got) < MAX_PER_BOARD:
                complete_sources.add(f"lever:{site}")
            print(f"[crawl] lever:{site}: +{len(got)}")
        except Exception as e:
            print(f"[crawl] lever:{site} FAILED: {str(e)[:120]}")
    for company_id, company in SMARTRECRUITERS_COMPANIES.items():
        try:
            got = crawl_smartrecruiters(company_id, company); items.extend(got)
            if len(got) < MAX_PER_BOARD:
                complete_sources.add(f"smartrecruiters:{company_id}")
            print(f"[crawl] smartrecruiters:{company_id}: +{len(got)}")
        except Exception as e:
            print(f"[crawl] smartrecruiters:{company_id} FAILED: {str(e)[:120]}")
    for source, url in PARTNER_FEEDS.items():
        if not url:
            continue
        try:
            got = crawl_partner_feed(url, source); items.extend(got)
            if len(got) < MAX_PER_BOARD:
                complete_sources.add(f"partner:{source}")
            print(f"[crawl] partner:{source}: +{len(got)}")
        except Exception as e:
            print(f"[crawl] partner:{source} FAILED: {str(e)[:120]}")
    try:
        got = crawl_casino_seed_registry()
        items.extend(got)
        print(f"[crawl] casino-discovery: +{len(got)}")
    except Exception as e:
        print(f"[crawl] casino-discovery FAILED: {str(e)[:120]}")
    return (items, complete_sources) if with_metadata else items


def upsert(db, Job, guess_category, items, approve=True, complete_sources=None):
    """Upsert jobs and archive IDs missing from successfully fetched complete sources."""
    added = updated = closed = 0
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
                row.closed_at = ""
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
    for source in complete_sources or ():
        active_ids = {it["ext_id"] for it in items if it["source"] == source and it["ext_id"]}
        stale = (db.query(Job).filter(Job.source == source, Job.status == "approved")
                 .filter(~Job.ext_id.in_(active_ids) if active_ids else Job.ext_id != "").all())
        for row in stale:
            row.status = "archived"
            row.closed_at = datetime.utcnow().date().isoformat()
            closed += 1
    db.commit()
    return added, updated, closed


def run(db, Job, guess_category, approve=True):
    if not _RUN_LOCK.acquire(blocking=False):
        return {"skipped": "already_running", "at": datetime.utcnow().isoformat()}
    try:
        items, complete_sources = collect(with_metadata=True)
        added, updated, closed = upsert(
            db, Job, guess_category, items, approve=approve, complete_sources=complete_sources)
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
            "closed": closed,
            "companies": len(profiles), "source_counts": source_counts,
        })
        print(f"[crawl] готово: +{added} новых, {updated} обновлено, {closed} закрыто, собрано {len(items)}")
        return {"collected": len(items), "added": added, "updated": updated,
                "closed": closed, "companies": len(profiles), "at": datetime.utcnow().isoformat()}
    finally:
        _RUN_LOCK.release()


if __name__ == "__main__":
    sys.path.insert(0, __file__.rsplit("/server/", 1)[0])
    from server.app import SessionLocal, Job, guess_category, migrate, Base, engine
    Base.metadata.create_all(engine)
    with SessionLocal() as _db:
        migrate(_db)
        print(run(_db, Job, guess_category))
