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
import time
import urllib.parse
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
# Реестр источников для отображения в админке (что настроено и статус)
# hh.ru: публичный API отдаёт вилку, город и работодателя, но из дата-центров
# отвечает 403 — нужен токен приложения с dev.hh.ru в HH_APP_TOKEN.
# Определяем до SOURCE_REGISTRY: реестр читает токен, чтобы показать статус источника.
HH_TOKEN = os.environ.get("HH_APP_TOKEN", "").strip()

SOURCE_REGISTRY = [
    {"key": "rabota.ua", "name": "robota.ua", "type": "Открытый JSON API",
     "status": "подключён", "note": "Поиск по iGaming-словарю и брендам (FAVBET, Cosmolot, VBET…), "
                                    "полные описания и вилки в гривнах через api.rabota.ua"},
    {"key": "justjoin.it", "name": "justjoin.it (Польша)", "type": "Открытый JSON API + RSC",
     "status": "подключён", "note": "Весь листинг крупнейшего IT-борда Польши, свой фильтр по "
                                    "iGaming-брендам (Betsson, Evolution, Betclic, STS…) и ключам; "
                                    "вилки в злотых, описания из RSC-потока"},
    {"key": "arbeitnow", "name": "Arbeitnow (Германия/ЕС)", "type": "Открытый JSON API",
     "status": "подключён", "note": "Пагинируемый фид вакансий ЕС; фильтр по iGaming-брендам "
                                    "(Smarkets, Tipico, Merkur…) и отраслевым ключам"},
    {"key": "dev.bg", "name": "dev.bg (Болгария)", "type": "HTML + JSON-LD",
     "status": "подключён", "note": "Поиск по iGaming-словарю, JobPosting-разметка на карточках; "
                                    "София — заметный iGaming-хаб (EGT, Amusnet…)"},
    {"key": "jobsinmalta", "name": "jobsinmalta.com", "type": "Sitemap + JSON-LD",
     "status": "подключён", "note": "Категория gambling целиком + iGaming-роли из других категорий "
                                    "по слагу; полные описания из JobPosting-разметки карточек"},
    {"key": "work.ua", "name": "work.ua", "type": "HTML + страницы поиска",
     "status": "подключён", "note": "Страницы поиска по iGaming-словарю, описание из карточки; "
                                    "смысловой фильтр отсекает боулинги и случайные «ставки»"},
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
    {"key": "djinni", "name": "Djinni · gambling (Украина)", "type": "JSON-LD парсер с пагинацией",
     "status": "подключён", "note": "15 вакансий на страницу, обходим до 20 страниц (DJINNI_MAX_PAGES). Зарплата и город лежат в HTML, а не в JSON-LD"},
    {"key": "partner:grc.ua", "name": "GRC.UA", "type": "Партнёрский JSON-фид",
     "status": "подключён" if PARTNER_FEEDS["grc.ua"] else "нужен доступ",
     "note": "Сайт блокирует серверный сбор (403). Коннектор готов; нужен официальный feed URL от GRC.UA."},
    {"key": "partner:work.ua", "name": "Work.ua", "type": "Партнёрский JSON-фид",
     "status": "подключён" if PARTNER_FEEDS["work.ua"] else "нужен доступ",
     "note": "Sitemap доступен, страницы вакансий возвращают 403. Нужен официальный экспорт/API или письменное разрешение."},
    {"key": "partner:robota.ua", "name": "robota.ua", "type": "Партнёрский JSON-фид",
     "status": "подключён" if PARTNER_FEEDS["robota.ua"] else "нужен доступ",
     "note": "Сайт и внутренний API закрыты Cloudflare. Коннектор готов к официальному feed URL."},
    {"key": "hh.ru", "name": "HeadHunter (hh.ru)", "type": "Публичный API — нужен токен приложения",
     "status": "подключён" if HH_TOKEN else "нужен токен",
     "note": "Коннектор готов: 5 отраслевых запросов, вилка/город/работодатель. api.hh.ru отвечает 403 и из облака, и с обычного IP — нужен токен приложения с dev.hh.ru в переменной HH_APP_TOKEN, после чего источник включается сам."},
    {"key": "telegram", "name": "Telegram: betting_job, igaming_work, igamingjobs, GamblingServices",
     "type": "Веб-превью t.me/s/", "status": "подключён",
     "note": "Открытые страницы каналов без авторизации. Разбираем «Должность в Компания» из первой строки, формат и вилку — из второй. Каналы с резюме не берём"},
    {"key": "vendor-seeds", "name": "B2B-вендоры iGaming (55 компаний)", "type": "Карьерные страницы по списку",
     "status": "подключён", "note": "data/vendor-seeds.json: провайдеры слотов, платформы и агрегаторы. У 27 из 55 найдена карьерная страница; описания компаний идут в карточки"},
    {"key": "bamboohr", "name": "BambooHR: Altenar, Kalamba, Hacksaw", "type": "Публичный карьерный портал",
     "status": "подключён", "note": "Эндпоинты /careers/list и /careers/{id}/detail отдают вакансию с полным описанием. Новую студию подключить = строка в BAMBOO_ACCOUNTS"},
    {"key": "igamingcareers", "name": "iGamingCareers.co", "type": "Публичный JSON API агрегатора",
     "status": "подключён", "note": "~1 360 вакансий, 14 страниц по 100. Ссылка ведёт на карьерную страницу работодателя (applicationUrl), заглушки «No job postings» отбрасываем"},
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
DISCOVERY_LOOKUPS_PER_RUN = int(os.environ.get("CASINO_DISCOVERY_LOOKUPS_PER_RUN", "120"))
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



# Djinni: страница листинга отдаёт 15 JobPosting в JSON-LD, страницы пагинируются.
DJINNI_LISTINGS = {
    "https://djinni.co/jobs/?company_type=gambling": "djinni",
}
DJINNI_MAX_PAGES = int(os.environ.get("DJINNI_MAX_PAGES", "20"))


def crawl_jsonld_paged(url, source, max_pages=DJINNI_MAX_PAGES):
    """Пройти листинг постранично, пока приходят новые вакансии."""
    out, seen = [], set()
    separator = "&" if "?" in url else "?"
    for page in range(1, max_pages + 1):
        page_url = url if page == 1 else f"{url}{separator}page={page}"
        try:
            items = crawl_jsonld(page_url, source)
        except Exception:
            break
        fresh = [item for item in items if item["ext_id"] not in seen]
        if not fresh:
            break                       # страница без новых вакансий — листинг закончился
        seen.update(item["ext_id"] for item in fresh)
        out.extend(fresh)
        time.sleep(0.6)                 # не долбим чужой сайт
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



VENDOR_SEEDS_PATH = Path(__file__).resolve().parent.parent / "data" / "vendor-seeds.json"


def vendor_seeds():
    """Список B2B-вендоров iGaming с подтверждёнными карьерными страницами."""
    if not VENDOR_SEEDS_PATH.exists():
        return []
    payload = json.loads(VENDOR_SEEDS_PATH.read_text(encoding="utf-8"))
    return payload.get("vendors", []) if isinstance(payload, dict) else payload


def crawl_vendor_seeds():
    """Обойти карьерные страницы вендоров: JSON-LD, ATS-ссылки и страницы вакансий."""
    jobs = []
    for seed in vendor_seeds():
        if not seed.get("careers_url"):
            continue          # карьерная страница не найдена — оставляем на следующий прогон
        try:
            found, _pages = crawl_discovered_careers({
                "operator": seed.get("operator", ""),
                "homepage": seed.get("homepage", ""),
                "careers_url": seed["careers_url"]})
            jobs.extend(found)
        except Exception:
            continue
    return jobs


def vendor_company_profiles():
    """Описания и сайты вендоров для карточек компаний — без обращения к сети."""
    rows = []
    for seed in vendor_seeds():
        rows.append({
            "name": seed.get("operator", ""),
            "description_ru": seed.get("description", ""),
            "description": "",
            "website": seed.get("homepage", ""),
            "careers_url": seed.get("careers_url", ""),
            "industry": seed.get("vertical", ""),
            "founded_year": seed.get("founded_year"),
            "headquarters": "",
            "tagline": "",
            "size": "",
            "source": "vendor-seeds",
        })
    return rows


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


try:  # как часть пакета: from server import crawler
    from .salary import format_salary, parse_salary
except ImportError:  # как скрипт: python server/crawler.py
    from salary import format_salary, parse_salary


def _clean_text(raw):
    """Короткое поле (заголовок, компания, город) → чистый текст.

    Часть источников отдаёт заголовки с HTML-сущностями (`&#8211;`, `&amp;`),
    и они утекали в разметку JobPosting — Google показывал их буквально.
    """
    s = html.unescape(html.unescape(raw or ""))
    return " ".join(s.replace("\xa0", " ").split())


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
    if ("remote" in loc or "удал" in loc or "віддал" in loc
            or re.search(r"(fully remote|100% remote|remote-first|remote work|"
                         r"удал[её]нн?(ая|ка|о)|віддален|work mode:\s*remote)", head)):
        return "удалёнка"
    if ("hybrid" in loc or "гибрид" in loc
            or re.search(r"(hybrid|гибрид|гібрид|work mode:\s*hybrid)", head)):
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



# BambooHR — второй по популярности ATS у iGaming-студий после Greenhouse.
# Публичные эндпоинты: /careers/list (список) и /careers/{id}/detail (описание).
BAMBOO_ACCOUNTS = {
    "altenar": "Altenar",
    "kalambagames": "Kalamba Games",
    "hacksawoperations": "Hacksaw Gaming",
}


def crawl_bamboohr(account, company):
    """Вакансии из публичного карьерного портала BambooHR."""
    listing = json.loads(_fetch(f"https://{account}.bamboohr.com/careers/list"))
    rows = listing.get("result") if isinstance(listing, dict) else listing
    out = []
    for row in (rows or [])[:MAX_PER_BOARD]:
        job_id = str(row.get("id") or "")
        title = (row.get("jobOpeningName") or "").strip()
        if not job_id or not title:
            continue
        loc = row.get("location") or {}
        location = ", ".join(part for part in (loc.get("city"), loc.get("state")) if part)
        description = ""
        try:
            detail = json.loads(_fetch(f"https://{account}.bamboohr.com/careers/{job_id}/detail"))
            opening = (detail.get("result") or {}).get("jobOpening") or {}
            description = _clean_html(opening.get("description") or "")
            if not location:
                place = opening.get("location") or {}
                location = ", ".join(part for part in (place.get("city"),
                                                       place.get("addressCountry")) if part)
        except Exception:
            pass
        lang = detect_lang(title, description)
        out.append({
            "title": title, "company_name": company, "location": location,
            "fmt": "удалёнка" if row.get("isRemote") else _fmt_from(location, description),
            "tags": _tags_from(title, description, lang),
            "description": description,
            "source_url": f"https://{account}.bamboohr.com/careers/{job_id}",
            "source": f"bamboohr:{account}", "ext_id": job_id,
            "salary": "по запросу", "posted_at": "", "deadline": "",
        })
        time.sleep(0.15)
    return out



# Публичные Telegram-каналы с вакансиями iGaming. Читаем веб-превью t.me/s/<канал> —
# это открытая страница без авторизации. Каналы с резюме (igaming_cv) не берём:
# резюме мы принципиально не клонируем, только вакансии.
TELEGRAM_CHANNELS = {
    "betting_job": "Работа в ставках",
    "igaming_work": "iGaming jobs",
    "igamingjobs": "iGaming Jobs",
    "GamblingServices": "Гемблинг объявления",
}
TELEGRAM_PAGES = int(os.environ.get("TELEGRAM_PAGES", "4"))
TG_JOB_WORDS = ("ваканс", "ищем", "ищет", "требуется", "в команду", "открыта позиция",
                "зарплат", "оклад", "we are looking", "hiring", "join our team", "position")
TG_SKIP_WORDS = ("резюме", "ищу работу", "cv:", "рассмотрю предложения", "ищу проект")
TG_MONEY = re.compile(r"(?:от\s*)?[€$₴]\s?\d[\d\s.,]*(?:\s?[-–—]\s?[€$₴]?\s?\d[\d\s.,]*)?"
                      r"(?:\s?(?:usdt|usd|eur|k))?", re.I)


def _tg_messages(channel, pages=TELEGRAM_PAGES):
    """Сообщения канала с конца ленты, постранично через ?before=."""
    seen, out, before = set(), [], None
    for _ in range(pages):
        url = f"https://t.me/s/{channel}" + (f"?before={before}" if before else "")
        try:
            page = _fetch_html(url)
        except Exception:
            break
        # Разбираем ленту по кускам: один пост = от data-post до следующего.
        chunks = re.split(r'(?=<div class="tgme_widget_message[^"]*"[^>]*data-post=")', page)
        ids = []
        for chunk in chunks:
            post_match = re.search(r'data-post="([^"]+)"', chunk)
            if not post_match:
                continue
            post = post_match.group(1)
            post_id = post.rsplit("/", 1)[-1]
            if not post_id.isdigit() or post_id in seen:
                continue
            seen.add(post_id)
            ids.append(int(post_id))
            text_match = re.search(
                r'(?is)<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>\s*(?:<div|</div>)',
                chunk)
            if not text_match:
                continue
            text = re.sub(r"(?i)<br\s*/?>", "\n", text_match.group(1))
            text = html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
            when = re.search(r'<time datetime="([^"]+)"', chunk)
            if text:
                out.append({"id": post_id, "post": post, "text": text,
                            "date": when.group(1)[:10] if when else ""})
        if not chunks:
            break
        if not ids:
            break
        before = min(ids)
        time.sleep(0.5)
    return out


def _tg_parse(message, channel_title):
    """Разобрать пост-вакансию: заголовок, компания, формат, зарплата."""
    text = message["text"]
    low = text.lower()
    if len(text) < 120 or any(word in low for word in TG_SKIP_WORDS):
        return None
    if not any(word in low for word in TG_JOB_WORDS):
        return None
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return None
    head = re.sub(r"^[#\W_]+", "", lines[0]).strip()[:160]
    head = re.sub(r"\s*\|\s*ID:\s*\d+\s*$", "", head)      # «Payment manager | ID: 1802»
    if not head:
        return None
    company = ""
    # часть каналов пишет поля явно: Company / Work mode / Industry
    field = re.search(r"(?im)^Company:\s*(.+)$", text)
    if field:
        value = field.group(1).strip()
        if value.upper() not in ("NDA", "N/A", "-", "СКРЫТО"):
            company = value[:60]
    if not company:
        match = re.search(r"\s+в\s+(?:в\s+)?([^,|(]{2,60})$", head)
        if match:
            company = match.group(1).strip(" .—–-")
            head = head[: match.start()].strip()
    salary_line = lines[1] if len(lines) > 1 else ""
    money = TG_MONEY.search(salary_line) or TG_MONEY.search(text[:400])
    salary = money.group(0).strip() if money else "по запросу"
    body = "\n".join(lines[1:])[:6000]
    location = ""
    place = re.search(r"\(([^)]{3,40})\)", salary_line)
    if place:
        location = place.group(1).strip()
    lang = detect_lang(head, body)
    return {
        "title": head,
        "company_name": company or "Компания не указана",
        "location": location,
        "fmt": _fmt_from(location, salary_line + " " + body),
        "tags": _tags_from(head, body, lang),
        "description": body,
        "source_url": f"https://t.me/{message['post']}",
        "source": f"telegram:{message['post'].split('/')[0]}",
        "ext_id": message["id"],
        "salary": salary[:60],
        "posted_at": message["date"],
        "deadline": "",
    }


def crawl_telegram(channel, channel_title):
    out = []
    for message in _tg_messages(channel):
        parsed = _tg_parse(message, channel_title)
        if parsed:
            out.append(parsed)
    return out[:MAX_PER_BOARD]



HH_QUERIES = ("гемблинг", "беттинг", "iGaming", "букмекер", "казино онлайн")
HH_PER_PAGE = 50


def crawl_hh(query, pages=2):
    """Вакансии hh.ru по отраслевому запросу. Без токена источник пропускается."""
    if not HH_TOKEN:
        raise RuntimeError("HH_APP_TOKEN не задан — hh.ru отвечает 403 без токена приложения")
    out = []
    for page in range(pages):
        url = (f"https://api.hh.ru/vacancies?text={quote_plus(query)}"
               f"&per_page={HH_PER_PAGE}&page={page}&only_with_salary=false")
        request = urllib.request.Request(url, headers={
            "User-Agent": UA, "Authorization": f"Bearer {HH_TOKEN}", "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            payload = json.loads(response.read())
        items = payload.get("items") or []
        if not items:
            break
        for item in items:
            title = (item.get("name") or "").strip()
            if not title:
                continue
            employer = ((item.get("employer") or {}).get("name") or "").strip()
            area = ((item.get("area") or {}).get("name") or "").strip()
            snippet = item.get("snippet") or {}
            description = _clean_html(" ".join(filter(None, (snippet.get("responsibility"),
                                                             snippet.get("requirement")))))
            salary = "по запросу"
            money = item.get("salary") or {}
            if money.get("from") or money.get("to"):
                currency = {"RUR": "₽", "USD": "$", "EUR": "€", "UAH": "₴"}.get(
                    money.get("currency") or "", money.get("currency") or "")
                low, high = money.get("from"), money.get("to")
                salary = (f"{low:,}–{high:,} {currency}" if low and high
                          else f"от {low:,} {currency}" if low else f"до {high:,} {currency}")
                salary = salary.replace(",", " ")
            schedule = ((item.get("schedule") or {}).get("name") or "")
            lang = detect_lang(title, description)
            out.append({
                "title": title, "company_name": employer or "Компания не указана",
                "location": area, "fmt": _fmt_from(area, schedule + " " + description),
                "tags": _tags_from(title, description, lang), "description": description,
                "source_url": item.get("alternate_url") or "",
                "source": "hh.ru", "ext_id": str(item.get("id") or ""),
                "salary": salary, "posted_at": (item.get("published_at") or "")[:10],
                "deadline": "",
            })
        if page + 1 >= (payload.get("pages") or 1):
            break
        time.sleep(0.3)
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



IGC_API = "https://www.igamingcareers.co/api/jobs"
IGC_MAX_PAGES = 14           # 1 364 вакансии по 100 на страницу
IGC_PLACEHOLDER = "no job postings currently open"


def crawl_igamingcareers(max_pages=IGC_MAX_PAGES):
    """Агрегатор iGamingCareers: открытый JSON API со ссылкой на карьерную страницу работодателя.

    Ссылку ведём на applicationUrl — это ATS или сайт самой компании, а не борд-посредник,
    поэтому кандидат попадает к работодателю напрямую, как и по остальным нашим источникам.
    """
    out = []
    for page in range(1, max_pages + 1):
        payload = json.loads(_fetch(f"{IGC_API}?limit=100&page={page}"))
        jobs = payload.get("jobs") or []
        if not jobs:
            break
        for j in jobs:
            title = (j.get("title") or "").strip()
            company = (j.get("company") or "").strip()
            link = (j.get("applicationUrl") or "").strip()
            if not title or not link or not j.get("isActive"):
                continue
            if IGC_PLACEHOLDER in title.lower():
                continue          # компания-заглушка без реальных вакансий
            description = _clean_html(j.get("descriptionHtml") or j.get("description") or "")
            requirements = _clean_html(j.get("requirementsHtml") or j.get("requirements") or "")
            if requirements:
                description = f"{description}\n\nТребования\n{requirements}".strip()
            location = (j.get("location") or j.get("country") or "").strip()
            lang = detect_lang(title, description)
            out.append({
                "title": title,
                "company_name": company or "iGaming-компания",
                "location": location,
                "fmt": _fmt_from(location, description),
                "tags": _tags_from(title, description, lang),
                "description": description,
                "source_url": link,
                "source": "igamingcareers",
                "ext_id": str(j.get("id") or j.get("slug") or link[-80:]),
                "salary": _igc_salary(j),
                "posted_at": str(j.get("postedDate") or "")[:10],
                "deadline": str(j.get("expiresAt") or "")[:10],
                "company_ref": (j.get("companySlug") or "").strip(),
            })
        if not (payload.get("pagination") or {}).get("hasNextPage"):
            break
        time.sleep(0.4)
    return out


def _igc_salary(job):
    """Собрать вилку из отдельных полей API — строкового поля salary там почти нет."""
    if job.get("salary"):
        return str(job["salary"])[:120]
    low, high = job.get("salaryMin"), job.get("salaryMax")
    if not low and not high:
        return "по запросу"
    currency = {"EUR": "€", "USD": "$", "GBP": "£"}.get(job.get("salaryCurrency") or "EUR", "")
    period = {"year": "/ год", "month": "/ мес", "day": "/ день", "hour": "/ час"}.get(
        job.get("salaryPeriod") or "", "")
    if low and high and low != high:
        return f"{currency}{int(low):,} – {currency}{int(high):,} {period}".replace(",", " ").strip()
    return f"{currency}{int(low or high):,} {period}".replace(",", " ").strip()



IGC_COMPANY_API = "https://www.igamingcareers.co/api/companies/by-slug/"

# Из профиля берём только публичные данные компании. Контактные и биллинговые поля
# (contactEmail, billingEmail, contactPhone, contactName) сознательно не импортируем:
# это персональные данные сотрудников, а не описание работодателя.
IGC_COMPANY_FIELDS = ("name", "slug", "description", "tagline", "website", "careersUrl",
                      "headquarters", "foundedYear", "industry", "employeeCount", "logoUrl")



def _translate_ru(text: str) -> str:
    """Перевести описание компании на русский. Молча возвращает пустую строку при сбое —
    страница тогда покажет оригинал."""
    text = (text or "").strip()
    if not text or not re.search(r"[A-Za-z]", text):
        return ""
    try:
        params = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": "ru",
                                         "dt": "t", "q": text[:4000]})
        request = urllib.request.Request(
            "https://translate.googleapis.com/translate_a/single?" + params,
            headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read())
        return "".join(part[0] for part in payload[0]).strip()
    except Exception:
        return ""


def crawl_igamingcareers_companies(slugs, limit=250):
    """Публичные профили работодателей: описание, сайт, карьерная страница, HQ, год основания."""
    out = []
    for slug in list(dict.fromkeys(s for s in slugs if s))[:limit]:
        try:
            raw = json.loads(_fetch(IGC_COMPANY_API + quote_plus(slug)))
        except Exception:
            continue
        if not isinstance(raw, dict) or raw.get("error") or not raw.get("name"):
            continue
        profile = {key: raw.get(key) for key in IGC_COMPANY_FIELDS}
        description = _clean_html(profile.get("description") or raw.get("aboutHtml") or "")
        website = (profile.get("website") or "").strip()
        careers = (profile.get("careersUrl") or "").strip()
        if not description and not website:
            continue          # пустышка без полезных данных — не заводим профиль
        out.append({
            "name": (profile["name"] or "").strip(),
            "slug": (profile["slug"] or slug).strip(),
            "description": description[:4000],
            "description_ru": _translate_ru(description[:4000]),
            "tagline": (profile.get("tagline") or "").strip()[:200],
            "website": website[:300],
            "careers_url": careers[:300],
            "headquarters": (profile.get("headquarters") or "").strip()[:120],
            "founded_year": profile.get("foundedYear") or None,
            "industry": (profile.get("industry") or "").strip()[:80],
            "size": (profile.get("employeeCount") or "").strip()[:40],
            "source": "igamingcareers",
        })
        time.sleep(0.25)
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
    history_path = status_path.with_name("crawler-history.json")
    try:
        history = json.loads(history_path.read_text(encoding="utf-8"))
        if not isinstance(history, list):
            history = []
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        history = []
    history.append(payload)
    history_path.write_text(json.dumps(history[-30:], ensure_ascii=False, indent=2), encoding="utf-8")


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
    health = []

    def fetch_source(key, callback, complete=False, attempts=2):
        started = time.monotonic()
        error = ""
        got = []
        used_attempts = 0
        for attempt in range(1, attempts + 1):
            used_attempts = attempt
            try:
                got = callback()
                error = ""
                break
            except Exception as exc:
                error = str(exc)[:300]
        ok = not error
        if ok:
            items.extend(got)
            if complete and len(got) < MAX_PER_BOARD:
                complete_sources.add(key)
            print(f"[crawl] {key}: +{len(got)}")
        else:
            print(f"[crawl] {key} FAILED after {used_attempts} attempts: {error[:120]}")
        health.append({
            "key": key, "ok": ok, "count": len(got), "attempts": used_attempts,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "error": error, "checked_at": datetime.utcnow().isoformat() + "Z",
        })
        return got

    fetch_source("softswiss", crawl_softswiss, complete=True)
    for board, company in GREENHOUSE_BOARDS.items():
        fetch_source(f"greenhouse:{board}", lambda b=board, c=company: crawl_greenhouse(b, c), complete=True)
    for url, source in DJINNI_LISTINGS.items():
        fetch_source(source, lambda u=url, s=source: crawl_jsonld_paged(u, s))
    for site, company in LEVER_SITES.items():
        fetch_source(f"lever:{site}", lambda s=site, c=company: crawl_lever(s, c), complete=True)
    for account, company in BAMBOO_ACCOUNTS.items():
        fetch_source(f"bamboohr:{account}",
                     lambda a=account, c=company: crawl_bamboohr(a, c), complete=True)
    for company_id, company in SMARTRECRUITERS_COMPANIES.items():
        fetch_source(f"smartrecruiters:{company_id}",
                     lambda i=company_id, c=company: crawl_smartrecruiters(i, c), complete=True)
    for source, url in PARTNER_FEEDS.items():
        if not url:
            continue
        fetch_source(f"partner:{source}", lambda u=url, s=source: crawl_partner_feed(u, s), complete=True)
    if HH_TOKEN:
        for query in HH_QUERIES:
            fetch_source(f"hh.ru:{query}", lambda q=query: crawl_hh(q))
    for channel, channel_title in TELEGRAM_CHANNELS.items():
        fetch_source(f"telegram:{channel}",
                     lambda c=channel, t=channel_title: crawl_telegram(c, t))
    fetch_source("vendor-seeds", crawl_vendor_seeds)
    fetch_source("igamingcareers", crawl_igamingcareers)
    fetch_source("rabota.ua", crawl_rabota_ua)
    fetch_source("work.ua", crawl_work_ua)
    fetch_source("justjoin.it", crawl_justjoin)
    fetch_source("arbeitnow", crawl_arbeitnow)
    fetch_source("dev.bg", crawl_devbg)
    fetch_source("jobsinmalta", crawl_jobsinmalta)
    fetch_source("casino-discovery", crawl_casino_seed_registry)
    return (items, complete_sources, health) if with_metadata else items


# ---------- rabota.ua: открытый JSON-API ----------
# Сайт закрыт Cloudflare, но api.rabota.ua отвечает без ключа. Ищем по словарю
# iGaming-запросов и брендов, детали тянем по id (полное описание, вилка в грн).
RABOTA_UA_QUERIES = [
    "казино", "igaming", "gambling", "гембл", "беттінг", "беттинг", "букмекер",
    "betting", "sportsbook", "favbet", "cosmolot", "vbet", "ggbet", "slots city",
    "pin-up", "parimatch", "1win", "slotoking", "космолот", "крупє", "крупье",
]


def crawl_rabota_ua(max_details: int = 250):
    import urllib.parse as _up
    seen, out = set(), []
    for query in RABOTA_UA_QUERIES:
        start = 0
        while True:
            url = ("https://api.rabota.ua/vacancy/search?"
                   f"keyWords={_up.quote(query)}&count=40&start={start}")
            try:
                data = json.loads(_fetch(url))
            except Exception:
                break
            docs = data.get("documents") or []
            for doc in docs:
                seen.add(str(doc.get("id")))
            if len(docs) < 40:
                break
            start += 40
    for vid in sorted(seen)[:max_details]:
        try:
            d = json.loads(_fetch(f"https://api.rabota.ua/vacancy?id={vid}"))
        except Exception:
            continue
        if not d.get("isActive", True):
            continue
        title = (d.get("name") or "").strip()
        if not title:
            continue
        desc = _clean_html(d.get("description") or "")
        probe = {"title": title, "company_name": d.get("companyName") or "",
                 "description": desc}
        if not _ua_item_relevant(probe):
            continue
        lo, hi = d.get("salaryFrom") or 0, d.get("salaryTo") or 0
        if lo and hi:
            salary = f"₴{lo:,}–{hi:,}".replace(",", " ")
        elif d.get("salary"):
            salary = f"₴{d['salary']:,}".replace(",", " ")
        else:
            salary = "по запросу"
        city = (d.get("cityName") or "").strip()
        fmt = "удалёнка" if re.search(r"віддален|удалённ|remote", desc, re.I) else "офис"
        out.append({
            "title": title,
            "company_name": (d.get("companyName") or "").strip() or "iGaming-компания",
            "location": f"{city}, Украина" if city else "Украина",
            "fmt": fmt, "salary": salary, "tags": "", "description": desc,
            "source": "rabota.ua", "ext_id": str(vid),
            "source_url": f"https://robota.ua/company{d.get('notebookId')}/vacancy{vid}",
        })
        time.sleep(0.2)
    return out


# Общий смысловой фильтр для генералистских украинских бордов: берём вакансию,
# только если компания — известный iGaming-бренд или в тексте ≥2 отраслевых
# маркеров. Иначе по слову «казино» приезжают боулинги и P&G по «ставкам».
_UA_IGAMING_RE = re.compile(
    r"казино|casino|гембл|gambl|igaming|беттінг|беттинг|betting|букмекер|"
    r"sportsbook|ставк[аи] на спорт|ставок на спорт|\bslots?\b|слот|крупє|"
    r"круп'є|крупье|poker|покер|live[ -]?dealer", re.I)
_UA_BRANDS_RE = re.compile(
    r"favbet|фавбет|cosmolot|космолот|vbet|ggbet|pin-?up|пін-?ап|parimatch|"
    r"парімач|1win|slotoking|slots ?city|betking|прематч", re.I)


def _ua_item_relevant(item) -> bool:
    # Procter & Gamble — «Проктер енд Гембл»: единственная компания, чьё имя
    # буквально содержит «гембл», не имея отношения к индустрии
    if re.search(r"procter|проктер", item["company_name"], re.I):
        return False
    if _UA_BRANDS_RE.search(item["company_name"]):
        return True
    haystack = f"{item['company_name']} {item['title']} {item['description']}"
    return len(_UA_IGAMING_RE.findall(haystack)) >= 2


WORK_UA_QUERIES = ["казино", "гемблінг", "igaming", "ставки", "крупє", "беттинг", "gambling"]


def crawl_work_ua(max_details: int = 120):
    """work.ua: страницы поиска отдаются с браузерным UA, описание — в
    div#job-description; JSON-LD на карточках нет, парсим разметку."""
    import urllib.parse as _up
    ids = set()
    for query in WORK_UA_QUERIES:
        for lang in ("", "ru/"):
            try:
                page = _fetch_html(f"https://www.work.ua/{lang}jobs-{_up.quote(query)}/")
            except Exception:
                continue
            ids.update(re.findall(r'/(?:ru/)?jobs/(\d+)', page))
    out = []
    for vid in sorted(ids)[:max_details]:
        try:
            page = _fetch_html(f"https://www.work.ua/jobs/{vid}/")
        except Exception:
            continue
        title_m = re.search(r'<h1[^>]*id="h1-name"[^>]*>(.*?)</h1>', page, re.S)
        if not title_m:
            continue
        title = _clean_text(re.sub(r"<[^>]+>", "", title_m.group(1)))
        company_m = re.search(r'/jobs/by-company/\d+/"[^>]*>\s*<span class="strong-500">([^<]+)</span>', page)
        company = _clean_text(company_m.group(1)) if company_m else "iGaming-компания"
        desc_m = re.search(r'id="job-description"[^>]*>(.*?)</div>', page, re.S)
        desc = _clean_html(desc_m.group(1)) if desc_m else ""
        salary_m = re.search(r'>([\d\s \xa0]{4,12})\s*грн', page)
        salary = f"₴{_clean_text(salary_m.group(1))}" if salary_m else "по запросу"
        city_m = re.search(r'glyphicon-map-marker[^<]*</span>\s*([^<]{2,40})', page)
        city = _clean_text(city_m.group(1)).strip(" ,·") if city_m else ""
        fmt = "удалёнка" if re.search(r"віддален|удалённ|remote", desc, re.I) else "офис"
        item = {"title": title, "company_name": company,
                "location": f"{city}, Украина" if city else "Украина",
                "fmt": fmt, "salary": salary, "tags": "", "description": desc,
                "source": "work.ua", "ext_id": str(vid),
                "source_url": f"https://www.work.ua/jobs/{vid}/"}
        if _ua_item_relevant(item):
            out.append(item)
        time.sleep(0.25)
    return out


# ---------- justjoin.it: крупнейший IT-борд Польши ----------
# API отдаёт весь листинг (заголовок Version: 2 обязателен), keyword игнорирует —
# фильтруем сами по брендам и ключам. Описание лежит в RSC-потоке страницы
# оффера по ссылке вида body:"$5c" → секция "5c:T…,<html>".
_PL_BRANDS_RE = re.compile(
    r"betsson|evolution|sportradar|betclic|superbet|fortuna|\bsts\b|pragmatic play|"
    r"playtech|kindred|livescore|betfan|totalbet|entain|bwin|\b888\b|softswiss|"
    r"betgames|casumo|leovegas|yolo group|hero gaming|greentube|wazdan|booongo|"
    r"evoplay|slotegrator|betby|stakelogic|relax gaming|"
    # европейские бренды за пределами Польши: DE/UK/BG-операторы и провайдеры
    r"smarkets|tipico|merkur|gauselmann|l[öo]wen play|bet365|kaizen|betano|"
    r"aura gaming|amusnet|\begt\b|efbet|palms bet|winbet|sesame|flutter|"
    r"william hill|ladbrokes|paddy power|unibet|mr ?green|gamomat|hölle ?games", re.I)


def _eu_item_relevant(item) -> bool:
    if _PL_BRANDS_RE.search(item["company_name"]):
        return True
    haystack = f"{item['company_name']} {item['title']} {item['description']}"
    return len(_UA_IGAMING_RE.findall(haystack)) >= 2
_PL_KEYWORD_RE = re.compile(r"casino|igaming|gambling|betting|bukmacher|sportsbook|slots?\b", re.I)


def _justjoin_api(url):
    req = urllib.request.Request(url, headers={"Version": "2", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def _justjoin_body(slug: str) -> str:
    """Достать HTML описания оффера из RSC-потока страницы."""
    try:
        page = _fetch_html(f"https://justjoin.it/job-offer/{slug}")
    except Exception:
        return ""
    joined = "".join(re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', page, re.S))
    ref = re.search(r'body\\+":\\+"\$(\w+)\\+"', joined)
    if not ref:
        return ""
    # переносы строк внутри потока экранированы: секции разделены «\n5c:T2f0a,…»,
    # где T2f0a — hex-длина текста секции: по ней и отрезаем
    m = re.search(rf'\\n{ref.group(1)}:T([0-9a-f]+),(.*?)(?=\\n[0-9a-f]{{1,4}}:|\Z)',
                  joined, re.S)
    if not m:
        return ""
    try:
        raw = json.loads('"' + m.group(2) + '"')
    except Exception:
        raw = m.group(2)
    try:
        raw = raw[:int(m.group(1), 16)]
    except ValueError:
        pass
    # если в захват всё же попал заголовок следующей RSC-секции — отрезаем
    raw = re.split(r"\n[0-9a-f]{1,4}:T[0-9a-f]+,", raw)[0]
    # GDPR-приписку про обработку персональных данных кандидату читать незачем
    raw = re.split(r"Informujemy, że administratorem|Administratorem (?:Twoich |Pani/Pana )?danych",
                   raw, flags=re.I)[0]
    return _clean_html(raw)


def crawl_justjoin(max_pages: int = 120, max_details: int = 60):
    out, page = [], 1
    candidates = []
    while page <= max_pages:
        try:
            data = _justjoin_api("https://api.justjoin.it/v2/user-panel/offers"
                                 f"?perPage=100&page={page}")
        except Exception:
            break
        offers = data.get("data") or []
        for o in offers:
            company = o.get("companyName") or ""
            title = o.get("title") or ""
            if _PL_BRANDS_RE.search(company) or _PL_KEYWORD_RE.search(f"{title} {company}"):
                candidates.append(o)
        meta = data.get("meta") or {}
        if page >= (meta.get("totalPages") or 1):
            break
        page += 1
        time.sleep(0.12)
    for o in candidates[:max_details]:
        slug = o.get("slug") or ""
        desc = _justjoin_body(slug)
        pay = ""
        for et in (o.get("employmentTypes") or []):
            lo, hi = et.get("from"), et.get("to")
            cur = (et.get("currency") or "pln").upper()
            if lo and hi:
                pay = f"{lo:,}–{hi:,} {cur}".replace(",", " ")
                break
        wt = (o.get("workplaceType") or "").lower()
        fmt = {"remote": "удалёнка", "hybrid": "гибрид"}.get(wt, "офис")
        city = o.get("city") or ""
        skills = ", ".join(s.get("name", "") if isinstance(s, dict) else str(s)
                           for s in (o.get("requiredSkills") or [])[:5])
        out.append({
            "title": (o.get("title") or "").strip(),
            "company_name": (o.get("companyName") or "").strip() or "iGaming-компания",
            "location": f"{city}, Польша" if city else "Польша",
            "fmt": fmt, "salary": pay or "по запросу", "tags": skills,
            "description": desc,
            "source": "justjoin.it", "ext_id": slug,
            "source_url": f"https://justjoin.it/job-offer/{slug}",
        })
        time.sleep(0.2)
    return out


# ---------- arbeitnow.com: открытый API, Германия и ЕС ----------
def crawl_arbeitnow(max_pages: int = 15):
    out, url = [], "https://www.arbeitnow.com/api/job-board-api"
    for _ in range(max_pages):
        try:
            data = json.loads(_fetch(url))
        except Exception:
            break
        for o in data.get("data") or []:
            item = {"title": (o.get("title") or "").strip(),
                    "company_name": (o.get("company_name") or "").strip(),
                    "description": _clean_html(o.get("description") or "")}
            if not item["title"] or not _eu_item_relevant(item):
                continue
            tags = ", ".join(t for t in (o.get("tags") or []) if isinstance(t, str))[:120]
            item.update({
                "location": o.get("location") or "",
                "fmt": "удалёнка" if o.get("remote") else "офис",
                "salary": "по запросу", "tags": tags,
                "source": "arbeitnow", "ext_id": o.get("slug") or "",
                "source_url": o.get("url") or "",
            })
            out.append(item)
        url = (data.get("links") or {}).get("next")
        if not url:
            break
        time.sleep(0.15)
    return out


# ---------- dev.bg: IT-борд Болгарии (София — iGaming-хаб) ----------
DEVBG_QUERIES = ["igaming", "casino", "gambling", "betting"]


def crawl_devbg(max_details: int = 40):
    links = set()
    for query in DEVBG_QUERIES:
        try:
            page = _fetch_html(f"https://dev.bg/?s={query}")
        except Exception:
            continue
        links.update(re.findall(r'href="(https://dev\.bg/company/jobads/[^"]+)"', page))
    out = []
    for url in sorted(links)[:max_details]:
        try:
            page = _fetch_html(url)
        except Exception:
            continue
        posting = None
        for block in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>',
                                page, re.S):
            try:
                data = json.loads(block)
            except Exception:
                continue
            items = data if isinstance(data, list) else [data]
            posting = next((x for x in items if isinstance(x, dict)
                            and "JobPosting" in (x.get("@type") if isinstance(x.get("@type"), list)
                                                 else [x.get("@type")])), posting)
        if not posting:
            continue
        # JSON-LD у dev.bg содержит лишь превью; полный текст — в div.job_description,
        # компания — в span.company-name
        company_m = re.search(r'class="company-name\s*"[^>]*>\s*([^<]+)', page)
        desc_m = re.search(r'<div class="job_description">(.*?)</div>\s*<(?:div|section|aside)', page, re.S)
        item = {"title": _clean_text(posting.get("title") or ""),
                "company_name": _clean_text(company_m.group(1)) if company_m else "iGaming-компания",
                "description": _clean_html(desc_m.group(1) if desc_m
                                           else posting.get("description") or "")}
        if not item["title"] or not _eu_item_relevant(item):
            continue
        loc = posting.get("jobLocation")
        loc = loc[0] if isinstance(loc, list) and loc else loc
        city = ""
        if isinstance(loc, dict):
            addr = loc.get("address") or {}
            city = addr.get("addressLocality", "") if isinstance(addr, dict) else ""
        remote = "TELECOMMUTE" in str(posting.get("jobLocationType") or "").upper()
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        item.update({
            "location": f"{city}, Болгария" if city else "Болгария",
            "fmt": "удалёнка" if remote else "офис",
            "salary": "по запросу", "tags": "",
            "source": "dev.bg", "ext_id": slug, "source_url": url,
        })
        out.append(item)
        time.sleep(0.2)
    return out


# ---------- jobsinmalta.com: главный борд Мальты ----------
# Листинг и фильтры рендерятся клиентом, зато sitemap отдаёт все ~1900 вакансий
# с категорией в пути. Берём категорию gambling целиком + вакансии других
# категорий, у которых iGaming-слово прямо в слаге, — их прогоняем через фильтр.
_JIM_SLUG_RE = re.compile(r"casino|igaming|gambling|betting|sportsbook|slot|game-?(?:dev|design|math)", re.I)


def crawl_jobsinmalta(max_details: int = 80):
    try:
        sitemap = _fetch_html("https://jobsinmalta.com/sitemap.xml")
    except Exception:
        return []
    urls = re.findall(r"<loc>(https://jobsinmalta\.com/job/[^<]+)</loc>", sitemap)
    picked = []
    for u in urls:
        category, _, slug = u.split("/job/")[1].partition("/")
        if category == "gambling" or _JIM_SLUG_RE.search(slug):
            picked.append((u, category == "gambling"))
    out = []
    for url, sure in picked[:max_details]:
        try:
            page = _fetch_html(url)
        except Exception:
            continue
        posting = None
        for block in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>',
                                page, re.S):
            try:
                data = json.loads(block)
            except Exception:
                continue
            for cand in (data if isinstance(data, list) else [data]):
                types = cand.get("@type") if isinstance(cand, dict) else None
                if "JobPosting" in (types if isinstance(types, list) else [types]):
                    posting = cand
        if not posting:
            continue
        org = posting.get("hiringOrganization") or {}
        item = {"title": _clean_text(posting.get("title") or ""),
                "company_name": _clean_text((org.get("name") if isinstance(org, dict) else "") or "iGaming-компания"),
                "description": _clean_html(posting.get("description") or "")}
        if not item["title"] or (not sure and not _eu_item_relevant(item)):
            continue
        loc = posting.get("jobLocation")
        loc = loc[0] if isinstance(loc, list) and loc else loc
        city = ""
        if isinstance(loc, dict):
            addr = loc.get("address") or {}
            city = addr.get("addressLocality", "") if isinstance(addr, dict) else ""
        location = f"{city}, Мальта" if city and "malta" not in city.lower() else "Мальта"
        # у части агрегированных ролей город зашит в скобки заголовка (Gdansk, NSW…)
        bracket = re.search(r"\(([^)]*(?:,\s*\w{2,3}|Gdansk|Warsaw|Sofia|London|Remote)[^)]*)\)",
                            item["title"], re.I)
        if not city and bracket:
            location = bracket.group(1).strip()
        item.update({
            "location": location,
            "fmt": "гибрид" if re.search(r"hybrid", item["description"], re.I) else "офис",
            "salary": "по запросу", "tags": "",
            "source": "jobsinmalta", "ext_id": url.rsplit("-", 1)[-1],
            "source_url": url,
        })
        out.append(item)
        time.sleep(0.25)
    return out


# ---------- фильтр релевантности ----------
# Борд — про карьеры в iGaming. Физические/сервисные роли наземных казино и
# офисов (уборка, кухня, охрана, склад) не публикуем, даже если компания наша.
_RELEVANT_OVERRIDE_RE = re.compile(r"game\s+(?:host|presenter)|croupier|dealer", re.I)
_IRRELEVANT_TITLE_RE = re.compile(
    r"\b("
    r"housekeep\w*|cleaner|cleaning|janitor|steward\w*|laundry|"
    r"security\s+(?:officer|guard)|guard\b|"
    r"driver|courier|chauffeur|valet|"
    r"chef|cook|kitchen|waiter|waitress|bartender|barista|barman|busser|"
    r"food\s+(?:and|&)\s+beverage|f&b|"
    r"gardener|landscap\w*|handyman|electrician|plumber|hvac|carpenter|painter|"
    r"facilities\s+(?:technician|assistant|coordinator)|"
    r"maintenance\s+(?:technician|engineer|worker|mechanic|man)\w*|"
    r"nurse|paramedic|physician|"
    r"(?<!data\s)warehouse|forklift|general\s+worker|porter|"
    r"уборщи\w*|клинер|горничн\w*|охранник\w*|водитель\w*|курьер\w*|повар\w*|"
    r"официант\w*|бармен\w*|сантехник\w*|электрик\w*|кладовщик\w*|грузчик\w*|"
    r"разнорабоч\w*|медсестр\w*|"
    r"охорон\w*|прибиральн\w*|покоївк\w*|кухар\w*|офіціант\w*|водій|кур'?єр\w*|"
    r"вантажник\w*|різнороб\w*|адміністратор\w* (?:на|у) ресепшн|ресепшн"
    r")\b", re.I)


def job_is_irrelevant(title: str) -> bool:
    """Название говорит, что роль не про iGaming-карьеру."""
    t = title or ""
    if _RELEVANT_OVERRIDE_RE.search(t):
        return False
    return bool(_IRRELEVANT_TITLE_RE.search(t))


def sweep_irrelevant(db, Job) -> int:
    """Снять с публикации уже одобренные нерелевантные вакансии краулера.
    Компании без живых вакансий сами исчезают из каталога и с /company/…"""
    rows = (db.query(Job).filter(Job.status == "approved", Job.source != "")
            .all())
    rejected = 0
    for row in rows:
        if job_is_irrelevant(row.title):
            row.status = "rejected"
            row.closed_at = datetime.utcnow().date().isoformat()
            rejected += 1
    if rejected:
        db.commit()
    return rejected


def upsert(db, Job, guess_category, items, approve=True, complete_sources=None):
    """Upsert jobs and archive IDs missing from successfully fetched complete sources."""
    added = updated = closed = 0
    changed_rows, closed_rows = [], []
    seen = set()
    for it in items:
        key = (it["source"], it["ext_id"])
        seen.add(key)
        row = None
        if it["ext_id"]:
            row = db.query(Job).filter(Job.source == it["source"],
                                       Job.ext_id == it["ext_id"]).first()
        for field in ("title", "company_name", "location"):
            it[field] = _clean_text(it.get(field))
        # Источник часто не заполняет поле с вилкой, хотя в тексте она есть
        if not any(ch.isdigit() for ch in (it.get("salary") or "")):
            found = format_salary(parse_salary(it.get("description")))
            if found:
                it["salary"] = found
        cat = guess_category(it["title"], it["tags"])
        if row:
            before = (row.title, row.company_name, row.location, row.fmt, row.tags,
                      row.description, row.source_url, row.category, row.posted_at,
                      row.deadline, row.status, row.salary)
            row.title, row.company_name = it["title"], it["company_name"]
            row.location, row.fmt = it["location"], it["fmt"]
            row.tags, row.description = it["tags"], it["description"]
            row.source_url, row.category = it["source_url"], cat
            # Вилку не перетираем: у уже размещённой вакансии она могла быть
            # уточнена вручную. Заполняем только там, где её не было.
            if not any(ch.isdigit() for ch in (row.salary or "")) and \
                    any(ch.isdigit() for ch in (it.get("salary") or "")):
                row.salary = it["salary"]
            row.posted_at = it.get("posted_at", "") or row.posted_at
            row.deadline = it.get("deadline", "") or row.deadline
            if job_is_irrelevant(row.title):
                if row.status == "approved":
                    row.status = "rejected"
                    row.closed_at = datetime.utcnow().date().isoformat()
            elif row.status in ("archived", "rejected"):
                row.status = "approved" if approve else "pending"
                row.closed_at = ""
            after = (row.title, row.company_name, row.location, row.fmt, row.tags,
                     row.description, row.source_url, row.category, row.posted_at,
                     row.deadline, row.status, row.salary)
            if before != after:
                changed_rows.append(row)
            updated += 1
        else:
            row = Job(title=it["title"], company_name=it["company_name"],
                      location=it["location"], fmt=it["fmt"], salary=it["salary"],
                      tags=it["tags"], description=it["description"],
                      source_url=it["source_url"], source=it["source"],
                      ext_id=it["ext_id"], category=cat,
                      posted_at=it.get("posted_at", ""), deadline=it.get("deadline", ""),
                      status="rejected" if job_is_irrelevant(it["title"])
                             else ("approved" if approve else "pending"))
            db.add(row)
            changed_rows.append(row)
            added += 1
    for source in complete_sources or ():
        active_ids = {it["ext_id"] for it in items if it["source"] == source and it["ext_id"]}
        stale = (db.query(Job).filter(Job.source == source, Job.status == "approved")
                 .filter(~Job.ext_id.in_(active_ids) if active_ids else Job.ext_id != "").all())
        for row in stale:
            row.status = "archived"
            row.closed_at = datetime.utcnow().date().isoformat()
            closed_rows.append(row)
            closed += 1
    db.flush()
    db.commit()
    return added, updated, closed, [row.id for row in changed_rows], [row.id for row in closed_rows]


def notify_indexnow(urls):
    """Push changed URLs to Yandex/IndexNow when INDEXNOW_KEY is configured."""
    key = os.environ.get("INDEXNOW_KEY", "").strip()
    if not key or not urls:
        return 0
    body = json.dumps({"host": "spinhire.io", "key": key,
                       "keyLocation": "https://spinhire.io/indexnow-key.txt",
                       "urlList": urls[:10000]}).encode()
    req = urllib.request.Request("https://yandex.com/indexnow", data=body,
                                 headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        response.read()
    return len(urls[:10000])


def notify_google_indexing(updated_urls, deleted_urls):
    """Notify Google's JobPosting Indexing API when service-account JSON is configured."""
    raw = os.environ.get("GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        return 0
    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
        info = json.loads(raw) if raw.startswith("{") else json.loads(Path(raw).read_text())
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/indexing"])
        session = AuthorizedSession(credentials)
        limit = max(1, int(os.environ.get("GOOGLE_INDEXING_MAX_PER_RUN", "180")))
        sent = 0
        for url, kind in ([(url, "URL_UPDATED") for url in updated_urls]
                          + [(url, "URL_DELETED") for url in deleted_urls])[:limit]:
            response = session.post("https://indexing.googleapis.com/v3/urlNotifications:publish",
                                    json={"url": url, "type": kind}, timeout=TIMEOUT)
            response.raise_for_status()
            sent += 1
        return sent
    except ImportError:
        print("[indexing] google-auth is not installed")
        return 0


def notify_search_engines(changed_ids, closed_ids):
    base = "https://spinhire.io/job/"
    updated_urls = [base + str(job_id) for job_id in changed_ids]
    deleted_urls = [base + str(job_id) for job_id in closed_ids]
    try:
        indexnow = notify_indexnow(updated_urls + deleted_urls)
        print(f"[indexing] IndexNow: {indexnow}")
    except Exception as exc:
        print(f"[indexing] IndexNow failed: {str(exc)[:120]}")
    try:
        google = notify_google_indexing(updated_urls, deleted_urls)
        print(f"[indexing] Google: {google}")
    except Exception as exc:
        print(f"[indexing] Google failed: {str(exc)[:120]}")


def run(db, Job, guess_category, approve=True, upsert_companies=None):
    if not _RUN_LOCK.acquire(blocking=False):
        return {"skipped": "already_running", "at": datetime.utcnow().isoformat()}
    try:
        started = time.monotonic()
        items, complete_sources, health = collect(with_metadata=True)
        added, updated, closed, changed_ids, closed_ids = upsert(
            db, Job, guess_category, items, approve=approve, complete_sources=complete_sources)
        swept = sweep_irrelevant(db, Job)
        if swept:
            print(f"[crawl] нерелевантных вакансий снято с публикации: {swept}")
        try:
            from .enrich import enrich_missing
            enrich_missing(db, Job, limit=int(os.environ.get("ENRICH_PER_RUN", "150")))
        except Exception as exc:  # noqa: BLE001 — обогащение не должно ронять кроул
            print(f"[enrich] пропущено: {type(exc).__name__}: {exc}")
        notify_search_engines(changed_ids, closed_ids)
        profiles = company_snapshot(items)
        company_rows = 0
        if upsert_companies:
            # публичные профили работодателей: описание, сайт, карьерная страница, HQ
            slugs = [item.get("company_ref") for item in items if item.get("company_ref")]
            profiles_in = vendor_company_profiles() + crawl_igamingcareers_companies(slugs)
            company_rows = upsert_companies(profiles_in)
            print(f"[crawl] профилей компаний обновлено: {company_rows}")
        snapshot_path = Path(__file__).resolve().parent.parent / "data" / "companies.json"
        snapshot_path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
        source_counts = {}
        for item in items:
            source = item.get("source", "unknown")
            source_counts[source] = source_counts.get(source, 0) + 1
        failed = [row for row in health if not row["ok"]]
        stale_days = max(1, int(os.environ.get("CRAWLER_STALE_DAYS", "120")))
        stale_cutoff = datetime.utcnow() - timedelta(days=stale_days)
        stale_candidates = db.query(Job).filter(
            Job.status == "approved", Job.created_at < stale_cutoff,
            Job.source.notin_(("manual", "employer"))).count()
        status = {
            "last_run": datetime.utcnow().isoformat() + "Z", "ok": True,
            "collected": len(items), "added": added, "updated": updated,
            "closed": closed,
            "companies": len(profiles), "company_profiles": company_rows,
            "source_counts": source_counts, "sources": health,
            "failed_sources": len(failed), "stale_candidates": stale_candidates,
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
        save_status(status)
        print(f"[crawl] готово: +{added} новых, {updated} обновлено, {closed} закрыто, собрано {len(items)}")
        return {"collected": len(items), "added": added, "updated": updated,
                "closed": closed, "companies": len(profiles),
                "company_profiles": company_rows, "failed_sources": len(failed),
                "at": datetime.utcnow().isoformat()}
    finally:
        _RUN_LOCK.release()


if __name__ == "__main__":
    sys.path.insert(0, __file__.rsplit("/server/", 1)[0])
    from server.app import (SessionLocal, Job, guess_category, migrate, Base, engine,
                            upsert_company_profiles)
    Base.metadata.create_all(engine)
    with SessionLocal() as _db:
        migrate(_db)
        print(run(_db, Job, guess_category,
                  upsert_companies=lambda rows: upsert_company_profiles(_db, rows)))
