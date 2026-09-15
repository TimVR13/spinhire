# -*- coding: utf-8 -*-
"""Краулер календаря iGaming-событий: thegamblest.com → таблица events.

Источник — публичный календарь TheGamblest (WordPress): sitemap
https://www.thegamblest.com/event-sitemap.xml перечисляет все страницы событий с
датой изменения, а каждая страница отдаёт schema.org/Event в JSON-LD (даты, город,
адрес площадки, организатор, соцсети, сайд-ивенты). Из HTML дополнительно берём
статус сайд-ивентов (Public / Invite only), отметку «Recommended» и полный текст
описания — в JSON-LD оно обрезано.

Что делает прогон (run):
  * читает sitemap, перекачивает только страницы с изменившимся lastmod
    (метки хранятся в data/events-crawler.json), остальные не трогает;
  * для каждой страницы собирает карточку и делает upsert по slug
    («<slug источника>-<год начала>»: страница у источника одна на все годы,
    у нас каждый выпуск — своя страница и своя история);
  * подхватывает ручные события с той же датой и похожим названием (сид,
    админка) — чтобы не плодить дубли;
  * переводит описание на русский (тот же переводчик, что у scripts/build_i18n.py);
  * гасит прошедшие события (active=False), никогда не включает скрытые админом;
  * докачивает фото города из Википедии, если для города нет нашей обложки
    (scripts/event_city_photos.py делает фирменные через Vertex), и печёт
    OG-карточку через server.event_covers.

Запуск вручную: python3 -m server.events_crawler [--force] [--limit N]
В проде крутится в воркере (server.app._events_scheduler), раз в 12 часов.
"""
from __future__ import annotations

import html as html_lib
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from server import terms

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_FILE = os.path.join(ROOT, "data", "events-crawler.json")
CITY_DIR = os.path.join(ROOT, "img", "events", "city")
SITEMAP_URL = "https://www.thegamblest.com/event-sitemap.xml"
SOURCE = "thegamblest"
USER_AGENT = "SpinHireBot/1.0 (+https://spinhire.io; hello@spinhire.io)"
REQUEST_PAUSE = float(os.environ.get("EVENTS_CRAWL_PAUSE", "0.7"))
TIMEOUT = 25

# Русские имена городов iGaming-маршрута. Чего нет — остаётся по-английски.
CITY_RU = {
    "lisbon": "Лиссабон", "lisboa": "Лиссабон", "porto": "Порту", "tbilisi": "Тбилиси", "batumi": "Батуми",
    "gaborone": "Габороне", "cancun": "Канкун", "cancún": "Канкун", "bogotá": "Богота", "bogota": "Богота",
    "cartagena": "Картахена", "mexico city": "Мехико", "mexico": "Мехико", "san juan": "Сан-Хуан",
    "santo domingo": "Санто-Доминго", "lagos": "Лагос", "nairobi": "Найроби", "dakar": "Дакар",
    "cape town": "Кейптаун", "johannesburg": "Йоханнесбург", "accra": "Аккра", "kampala": "Кампала",
    "kigali": "Кигали", "addis ababa": "Аддис-Абеба", "cairo": "Каир", "marrakech": "Марракеш",
    "casablanca": "Касабланка", "london": "Лондон", "manchester": "Манчестер", "birmingham": "Бирмингем",
    "edinburgh": "Эдинбург", "gibraltar": "Гибралтар", "douglas": "Дуглас", "dublin": "Дублин",
    "barcelona": "Барселона", "madrid": "Мадрид", "malaga": "Малага", "málaga": "Малага", "marbella": "Марбелья",
    "valencia": "Валенсия", "seville": "Севилья", "ibiza": "Ибица", "malta": "Мальта", "valletta": "Валлетта",
    "st julian's": "Сент-Джулианс", "st. julian's": "Сент-Джулианс", "sliema": "Слима", "limassol": "Лимасол",
    "nicosia": "Никосия", "larnaca": "Ларнака", "paphos": "Пафос", "prague": "Прага", "praha": "Прага",
    "brno": "Брно", "warsaw": "Варшава", "krakow": "Краков", "kraków": "Краков", "gdansk": "Гданьск",
    "wroclaw": "Вроцлав", "budapest": "Будапешт", "vienna": "Вена", "berlin": "Берлин", "munich": "Мюнхен",
    "hamburg": "Гамбург", "frankfurt": "Франкфурт", "cologne": "Кёльн", "düsseldorf": "Дюссельдорф",
    "amsterdam": "Амстердам", "rotterdam": "Роттердам", "brussels": "Брюссель", "antwerp": "Антверпен",
    "luxembourg": "Люксембург", "paris": "Париж", "nice": "Ницца", "lyon": "Лион", "monaco": "Монако",
    "zurich": "Цюрих", "geneva": "Женева", "rome": "Рим", "milan": "Милан", "naples": "Неаполь",
    "turin": "Турин", "florence": "Флоренция", "venice": "Венеция", "bologna": "Болонья",
    "copenhagen": "Копенгаген", "stockholm": "Стокгольм", "oslo": "Осло", "helsinki": "Хельсинки",
    "tallinn": "Таллин", "riga": "Рига", "vilnius": "Вильнюс", "sofia": "София", "plovdiv": "Пловдив",
    "varna": "Варна", "bucharest": "Бухарест", "cluj-napoca": "Клуж-Напока", "athens": "Афины",
    "thessaloniki": "Салоники", "istanbul": "Стамбул", "ankara": "Анкара", "belgrade": "Белград",
    "zagreb": "Загреб", "ljubljana": "Любляна", "bratislava": "Братислава", "sarajevo": "Сараево",
    "podgorica": "Подгорица", "skopje": "Скопье", "tirana": "Тирана", "chisinau": "Кишинёв", "kyiv": "Киев",
    "kiev": "Киев", "lviv": "Львов", "dubai": "Дубай", "abu dhabi": "Абу-Даби", "riyadh": "Эр-Рияд",
    "doha": "Доха", "tel aviv": "Тель-Авив", "yerevan": "Ереван", "baku": "Баку", "almaty": "Алматы",
    "astana": "Астана", "tashkent": "Ташкент", "bishkek": "Бишкек", "manila": "Манила", "singapore": "Сингапур",
    "bangkok": "Бангкок", "ho chi minh city": "Хошимин", "ho chi minh": "Хошимин", "hanoi": "Ханой",
    "kuala lumpur": "Куала-Лумпур", "jakarta": "Джакарта", "bali": "Бали", "goa": "Гоа", "new delhi": "Нью-Дели",
    "delhi": "Дели", "mumbai": "Мумбаи", "bangalore": "Бангалор", "colombo": "Коломбо", "hong kong": "Гонконг",
    "macau": "Макао", "macao": "Макао", "taipei": "Тайбэй", "tokyo": "Токио", "seoul": "Сеул", "sydney": "Сидней",
    "melbourne": "Мельбурн", "auckland": "Окленд", "port moresby": "Порт-Морсби", "las vegas": "Лас-Вегас",
    "new york": "Нью-Йорк", "miami": "Майами", "chicago": "Чикаго", "los angeles": "Лос-Анджелес",
    "san francisco": "Сан-Франциско", "washington": "Вашингтон", "boston": "Бостон", "atlanta": "Атланта",
    "dallas": "Даллас", "houston": "Хьюстон", "denver": "Денвер", "phoenix": "Финикс", "seattle": "Сиэтл",
    "orlando": "Орландо", "tampa": "Тампа", "atlantic city": "Атлантик-Сити", "reno": "Рино", "savannah": "Саванна",
    "toronto": "Торонто", "vancouver": "Ванкувер", "montreal": "Монреаль", "ottawa": "Оттава",
    "são paulo": "Сан-Паулу", "sao paulo": "Сан-Паулу", "rio de janeiro": "Рио-де-Жанейро", "brasília": "Бразилиа",
    "brasilia": "Бразилиа", "buenos aires": "Буэнос-Айрес", "lima": "Лима", "santiago": "Сантьяго",
    "montevideo": "Монтевидео", "asunción": "Асунсьон", "asuncion": "Асунсьон", "quito": "Кито",
    "panama city": "Панама", "san josé": "Сан-Хосе", "san jose": "Сан-Хосе", "medellin": "Медельин",
    "medellín": "Медельин", "havana": "Гавана", "kingston": "Кингстон", "nassau": "Нассау", "online": "онлайн",
}
# Страны, которых нет в CLDR-таблице витрины (server/i18n/terms.auto.json) или
# которые источник пишет по-своему.
COUNTRY_RU_EXTRA = {
    "botswana": "Ботсвана", "czech": "Чехия", "czechia": "Чехия", "papua new guinea": "Папуа — Новая Гвинея",
    "senegal": "Сенегал", "usa": "США", "united states": "США", "uk": "Великобритания",
    "united kingdom": "Великобритания", "uae": "ОАЭ", "online": "онлайн", "dominican republic": "Доминикана",
    "sri lanka": "Шри-Ланка", "south africa": "ЮАР", "nigeria": "Нигерия", "kenya": "Кения", "ghana": "Гана",
    "tanzania": "Танзания", "uganda": "Уганда", "rwanda": "Руанда", "zambia": "Замбия", "zimbabwe": "Зимбабве",
    "cameroon": "Камерун", "ivory coast": "Кот-д’Ивуар", "côte d'ivoire": "Кот-д’Ивуар", "morocco": "Марокко",
    "egypt": "Египет", "ethiopia": "Эфиопия", "mozambique": "Мозамбик", "angola": "Ангола",
    "puerto rico": "Пуэрто-Рико", "costa rica": "Коста-Рика", "panama": "Панама", "peru": "Перу",
    "chile": "Чили", "argentina": "Аргентина", "uruguay": "Уругвай", "paraguay": "Парагвай", "ecuador": "Эквадор",
    "guatemala": "Гватемала", "el salvador": "Сальвадор", "honduras": "Гондурас", "nicaragua": "Никарагуа",
    "cuba": "Куба", "jamaica": "Ямайка", "bahamas": "Багамы", "india": "Индия", "thailand": "Таиланд",
    "vietnam": "Вьетнам", "philippines": "Филиппины", "malaysia": "Малайзия", "indonesia": "Индонезия",
    "cambodia": "Камбоджа", "nepal": "Непал", "bangladesh": "Бангладеш", "pakistan": "Пакистан",
    "australia": "Австралия", "new zealand": "Новая Зеландия", "isle of man": "Остров Мэн",
    "gibraltar": "Гибралтар", "monaco": "Монако", "luxembourg": "Люксембург", "north macedonia": "Северная Македония",
    "bosnia and herzegovina": "Босния", "kosovo": "Косово", "montenegro": "Черногория", "albania": "Албания",
    "moldova": "Молдова", "belarus": "Беларусь", "armenia": "Армения", "azerbaijan": "Азербайджан",
    "kazakhstan": "Казахстан", "uzbekistan": "Узбекистан", "kyrgyzstan": "Киргизия", "mongolia": "Монголия",
    "qatar": "Катар", "saudi arabia": "Саудовская Аравия", "bahrain": "Бахрейн", "oman": "Оман",
    "jordan": "Иордания", "lebanon": "Ливан", "israel": "Израиль", "iceland": "Исландия",
}
COUNTRY_ISO_EXTRA = {
    "Ботсвана": "BW", "Чехия": "CZ", "Папуа — Новая Гвинея": "PG", "Сенегал": "SN", "Доминикана": "DO",
    "Шри-Ланка": "LK", "ЮАР": "ZA", "Нигерия": "NG", "Кения": "KE", "Гана": "GH", "Танзания": "TZ",
    "Уганда": "UG", "Руанда": "RW", "Замбия": "ZM", "Зимбабве": "ZW", "Камерун": "CM", "Кот-д’Ивуар": "CI",
    "Марокко": "MA", "Египет": "EG", "Эфиопия": "ET", "Мозамбик": "MZ", "Ангола": "AO", "Пуэрто-Рико": "PR",
    "Коста-Рика": "CR", "Панама": "PA", "Перу": "PE", "Чили": "CL", "Аргентина": "AR", "Уругвай": "UY",
    "Парагвай": "PY", "Эквадор": "EC", "Гватемала": "GT", "Сальвадор": "SV", "Гондурас": "HN", "Никарагуа": "NI",
    "Куба": "CU", "Ямайка": "JM", "Багамы": "BS", "Индия": "IN", "Таиланд": "TH", "Вьетнам": "VN",
    "Филиппины": "PH", "Малайзия": "MY", "Индонезия": "ID", "Камбоджа": "KH", "Непал": "NP", "Бангладеш": "BD",
    "Пакистан": "PK", "Австралия": "AU", "Новая Зеландия": "NZ", "Остров Мэн": "IM", "Гибралтар": "GI",
    "Монако": "MC", "Люксембург": "LU", "Северная Македония": "MK", "Босния": "BA", "Косово": "XK",
    "Черногория": "ME", "Албания": "AL", "Молдова": "MD", "Беларусь": "BY", "Армения": "AM", "Азербайджан": "AZ",
    "Казахстан": "KZ", "Узбекистан": "UZ", "Киргизия": "KG", "Монголия": "MN", "Катар": "QA",
    "Саудовская Аравия": "SA", "Бахрейн": "BH", "Оман": "OM", "Иордания": "JO", "Ливан": "LB", "Израиль": "IL",
    "Исландия": "IS", "США": "US", "Великобритания": "GB", "ОАЭ": "AE",
}

# Тип события по названию — для фильтров календаря и цвета карточки.
CATEGORY_RULES = (
    (re.compile(r"\bawards?\b", re.I), "Награды"),
    (re.compile(r"\baffiliate|affpapa|\baff\b", re.I), "Аффилейт"),
    (re.compile(r"\bexpo\b|exhibition|\bshow\b|\bfair\b|\bICE\b", re.I), "Выставка"),
    (re.compile(r"\bclub\b|meetup|dinner|party|networking|reunion|connect\b", re.I), "Нетворкинг"),
)
CATEGORY_DEFAULT = "Конференция"
STOPWORDS = {"the", "and", "of", "in", "at", "for", "a", "an", "&", "amp", "summit", "conference", "expo",
             "event", "events", "edition", "world", "global", "international"}


# ---------- сеть ----------

def fetch_text(url: str, timeout: int = TIMEOUT) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "text/html,application/xml;q=0.9,*/*;q=0.8",
                                               "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def fetch_bytes(url: str, timeout: int = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def sitemap_entries(xml_text: str) -> list[tuple[str, str]]:
    """[(url, lastmod)] страниц событий; корень /event/ и не-события отбрасываем."""
    out = []
    for block in re.findall(r"<url>(.*?)</url>", xml_text, re.S):
        loc = re.search(r"<loc>\s*([^<\s]+)\s*</loc>", block)
        if not loc:
            continue
        url = html_lib.unescape(loc.group(1))
        if not re.search(r"/event/[^/]+/?$", url):
            continue
        mod = re.search(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", block)
        out.append((url, mod.group(1) if mod else ""))
    return out


# ---------- разбор страницы ----------

def _strip_tags(fragment: str) -> str:
    fragment = re.sub(r"<(br|/p|/li|/h\d|/div)[^>]*>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html_lib.unescape(fragment)
    lines = [" ".join(line.split()) for line in fragment.split("\n")]
    return "\n".join(line for line in lines if line)


def _event_ld(html_text: str) -> dict | None:
    for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html_text, re.S):
        if '"Event"' not in raw:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            try:
                data = json.loads(html_lib.unescape(raw))
            except ValueError:
                continue
        if isinstance(data, dict) and data.get("@type") == "Event":
            return data
    return None


def _description(html_text: str, fallback: str) -> str:
    m = re.search(r'<div class="event_descr_content">(.*?)</div>\s*</div>', html_text, re.S)
    if not m:
        return " ".join(html_lib.unescape(fallback or "").replace("&hellip;", "…").split())
    text = _strip_tags(m.group(1))
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    return "\n\n".join(paragraphs)[:6000]


def _side_events_html(html_text: str) -> list[dict]:
    """Строки блока «Side events»: название, площадка, время, статус, отметка Recommended, день."""
    start = html_text.find("Side events")
    if start < 0:
        return []
    end = html_text.find('id="map"', start)
    section = html_text[start:end if end > 0 else start + 200000]
    rows = []
    day = ""
    # заголовок дня и строки идут вперемешку — режем по обоим маркерам, храня порядок
    for kind, chunk in re.findall(r'(<span class="h3">|<div class="responsive-event-list__row)(.*?)(?=<span class="h3">|<div class="responsive-event-list__row|$)',
                                  section, re.S):
        if kind.startswith("<span"):
            day = _strip_tags(chunk.split("</span>", 1)[0]).strip()
            continue
        name = re.search(r'event_item__title[^>]*>(.*?)</p>', chunk, re.S)
        if not name:
            continue
        link = re.search(r'<a href="([^"]+)"[^>]*>\s*<p class="p-name', chunk, re.S)
        venue = re.search(r'events_item__location">.*?<span>\s*(?:<svg.*?</svg>)?\s*<span>(.*?)</span>', chunk, re.S)
        when = re.search(r"(\d{1,2}:\d{2})", _strip_tags(chunk))
        status = re.findall(r'btn_cst_linear[^>]*>\s*([^<]+?)\s*</span>', chunk, re.S)
        rows.append({
            "name": " ".join(html_lib.unescape(name.group(1)).split()),
            "url": html_lib.unescape(link.group(1)) if link else "",
            "venue": " ".join(html_lib.unescape(venue.group(1)).split()) if venue else "",
            "time": when.group(1) if when else "",
            "access": "invite" if status and "invite" in status[-1].lower() else "public",
            "recommended": "recomended_side_event" in chunk[:400] or "recommended_side_event" in chunk[:400],
            "day": day,
        })
    return rows


def _day_to_date(day: str, start: str) -> str:
    """«28 September» + год основного события → YYYY-MM-DD (сайд-ивент декабря у январского события — прошлый год)."""
    m = re.match(r"(\d{1,2})\s+([A-Za-z]+)", day or "")
    if not m or not start:
        return ""
    try:
        year = int(start[:4])
        parsed = datetime.strptime(f"{m.group(1)} {m.group(2)[:3]} {year}", "%d %b %Y").date()
    except ValueError:
        return ""
    base = date.fromisoformat(start)
    if parsed - base > timedelta(days=200):
        parsed = parsed.replace(year=year - 1)
    elif base - parsed > timedelta(days=200):
        parsed = parsed.replace(year=year + 1)
    return parsed.isoformat()


def _merge_side_events(ld_subs: list, html_rows: list[dict], start: str) -> list[dict]:
    """JSON-LD даёт даты и ссылки, HTML — площадку, время и статус. Сшиваем по названию."""
    pool = list(ld_subs or [])
    out = []
    for row in html_rows:
        match = None
        for i, sub in enumerate(pool):
            if " ".join(str(sub.get("name", "")).split()).lower() == row["name"].lower():
                match = pool.pop(i)
                break
        when = (match or {}).get("startDate", "")[:10] or _day_to_date(row["day"], start)
        loc = (match or {}).get("location") or {}
        out.append({
            "date": when,
            "name": row["name"],
            "venue": row["venue"] or (loc.get("name") if isinstance(loc, dict) else "") or "",
            "time": row["time"] or (match or {}).get("doorTime", "") or "",
            "url": row["url"] or (match or {}).get("url", "") or "",
            "access": row["access"],
            "recommended": row["recommended"] or "Recommended" in ((match or {}).get("keywords") or []),
        })
    for sub in pool:  # в JSON-LD есть, в HTML не нашли — всё равно показываем
        loc = sub.get("location") or {}
        out.append({"date": str(sub.get("startDate", ""))[:10], "name": " ".join(str(sub.get("name", "")).split()),
                    "venue": loc.get("name", "") if isinstance(loc, dict) else "", "time": sub.get("doorTime", "") or "",
                    "url": sub.get("url", "") or "", "access": "public",
                    "recommended": "Recommended" in (sub.get("keywords") or [])})
    out.sort(key=lambda r: (r["date"], r["time"]))
    return out


def source_slug(source_url: str) -> str:
    return source_url.rstrip("/").rsplit("/", 1)[-1].lower()


def make_slug(src_slug: str, date_from: str) -> str:
    """Один выпуск — одна страница: к слагу источника добавляем год, если его там ещё нет."""
    year = (date_from or "")[:4]
    slug = re.sub(r"[^a-z0-9-]+", "-", src_slug.lower()).strip("-")
    if year and not re.search(rf"(^|-){year}$", slug):
        slug = f"{slug}-{year}"
    return slug


def ascii_slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def clean_city(city: str, country: str) -> str:
    """«Georgia, Savannah» → «Savannah»; «Mexico» при стране Mexico → «Mexico City»."""
    city = " ".join((city or "").replace("&#039;", "'").split())
    if "," in city:
        city = city.split(",")[-1].strip()
    if city.lower() == (country or "").lower() and city.lower() == "mexico":
        city = "Mexico City"
    return city


def country_ru(country_en: str) -> str:
    key = " ".join((country_en or "").split()).lower()
    if not key:
        return ""
    return COUNTRY_RU_EXTRA.get(key) or terms.COUNTRY_ALIASES.get(key) or country_en


def country_iso(ru_name: str) -> str:
    return terms.COUNTRY_ISO.get(ru_name) or COUNTRY_ISO_EXTRA.get(ru_name, "")


def flag(iso: str) -> str:
    iso = (iso or "").upper()
    if len(iso) != 2 or not iso.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso)


def city_ru(city_en: str) -> str:
    return CITY_RU.get((city_en or "").lower(), city_en or "")


def city_label_ru(city_en: str, country_en: str) -> str:
    """Формат колонки city, как её показывает витрина: «🇵🇹 Лиссабон, Португалия»."""
    c_ru = country_ru(country_en)
    parts = [p for p in (city_ru(city_en), c_ru) if p]
    if len(parts) == 2 and parts[0] == parts[1]:
        parts = parts[:1]
    label = ", ".join(parts)
    fl = flag(country_iso(c_ru))
    return f"{fl} {label}".strip()


def guess_category(title: str) -> str:
    for rx, cat in CATEGORY_RULES:
        if rx.search(title or ""):
            return cat
    return CATEGORY_DEFAULT


def parse_event_page(html_text: str, source_url: str) -> dict | None:
    ld = _event_ld(html_text)
    if not ld:
        return None
    start = re.search(r'class="dt-start" datetime="(\d{4}-\d{2}-\d{2})"', html_text)
    end = re.search(r'class="dt-end" datetime="(\d{4}-\d{2}-\d{2})"', html_text)
    date_from = start.group(1) if start else str(ld.get("startDate", ""))[:10]
    date_to = end.group(1) if end else str(ld.get("endDate", ""))[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_from or ""):
        return None
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_to or "") or date_to < date_from:
        date_to = date_from
    addr = (ld.get("location") or {}).get("address") or {}
    if not isinstance(addr, dict):
        addr = {}
    country_en = " ".join(str(addr.get("addressCountry", "")).split())
    city_en = clean_city(str(addr.get("addressLocality", "")), country_en)
    street = " ".join(str(addr.get("streetAddress", "")).split())
    if street.lower() == city_en.lower():
        street = ""
    organizer = ld.get("organizer") or {}
    reg = re.search(r'<a href="([^"]+)"[^>]*class="btn_cst_fill btn_reg_profile"', html_text)
    if not reg:
        reg = re.search(r'class="btn_cst_fill btn_reg_profile"[^>]*href="([^"]+)"', html_text)
    url = str(ld.get("url") or (reg.group(1) if reg else "") or organizer.get("url") or "")
    cover = re.search(r'data-src="([^"]+)"\s+class="lazyload bg_event_img"', html_text)
    images = ld.get("image") or []
    cover_src = cover.group(1) if cover else (images[0] if isinstance(images, list) and images else str(images or ""))
    title = " ".join(html_lib.unescape(str(ld.get("name", ""))).split())
    subs = _merge_side_events(ld.get("subEvent") or [], _side_events_html(html_text), date_from)
    return {
        "title": title,
        "date_from": date_from,
        "date_to": date_to,
        "city_en": city_en,
        "country_en": country_en,
        "venue": street,
        "organizer": " ".join(str(organizer.get("name", "")).split()),
        "organizer_url": str(organizer.get("url", "") or ""),
        "url": html_lib.unescape(url),
        "socials": [s for s in (ld.get("sameAs") or []) if isinstance(s, str)],
        "cover_src": cover_src.split("?")[0] if cover_src else "",
        "description_en": _description(html_text, str(ld.get("description", ""))),
        "sub_events": subs,
        "source_url": source_url,
        "src_slug": source_slug(source_url),
        "category": guess_category(title),
    }


# ---------- перевод описания ----------

_SPLIT = "\n__SH_SPLIT__\n"


def translate_ru(text: str) -> str:
    """Английское описание → русское. Ошибка сети → пустая строка (витрина покажет оригинал)."""
    text = (text or "").strip()
    if not text:
        return ""
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    out = []
    for i in range(0, len(paragraphs), 6):
        batch = paragraphs[i:i + 6]
        params = urllib.parse.urlencode({"client": "gtx", "sl": "en", "tl": "ru", "dt": "t", "q": _SPLIT.join(batch)})
        req = urllib.request.Request("https://translate.googleapis.com/translate_a/single?" + params,
                                     headers={"User-Agent": "SpinHire-events/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read())
            translated = "".join(part[0] for part in payload[0]).split(_SPLIT.strip())
            if len(translated) != len(batch):
                return ""
            out += [" ".join(t.split()) for t in translated]
        except Exception:  # noqa: BLE001 — переводчик неофициальный, падает без предупреждения
            return ""
    return "\n\n".join(out)


# ---------- фото города ----------

def city_photo_path(city_en: str) -> str:
    slug = ascii_slug(city_en)
    return os.path.join(CITY_DIR, f"{slug}.jpg") if slug else ""


def city_photo_url(city_en: str) -> str:
    path = city_photo_path(city_en)
    if path and os.path.exists(path):
        return f"/img/events/city/{os.path.basename(path)}"
    return ""


def ensure_city_photo(city_en: str, country_en: str, status: dict) -> str:
    """Фото города для обложки. Фирменное кладёт scripts/event_city_photos.py; здесь —
    запасной вариант из Википедии (лид-изображение статьи о городе), чтобы новый город
    в календаре не остался без картинки до следующего прогона скрипта."""
    path = city_photo_path(city_en)
    if not path or (city_en or "").lower() == "online":
        return ""
    if os.path.exists(path):
        return f"/img/events/city/{os.path.basename(path)}"
    credits = status.setdefault("city_photos", {})
    key = os.path.basename(path)
    if credits.get(key, {}).get("failed_at", "") > (datetime.utcnow() - timedelta(days=14)).isoformat():
        return ""
    try:
        from PIL import Image  # noqa: WPS433 — Pillow есть в requirements
        from io import BytesIO
        title = urllib.parse.quote(city_en.replace(" ", "_"))
        summary = json.loads(fetch_text(f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"))
        src = (summary.get("originalimage") or {}).get("source") or ""
        if not src or (summary.get("type") == "disambiguation"):
            raise ValueError("no lead image")
        im = Image.open(BytesIO(fetch_bytes(src))).convert("RGB")
        if im.width < 900:
            raise ValueError("too small")
        im.thumbnail((1600, 1600))
        os.makedirs(CITY_DIR, exist_ok=True)
        im.save(path, "JPEG", quality=84, optimize=True)
        credits[key] = {"source": "wikipedia", "url": src, "page": summary.get("content_urls", {}).get("desktop", {}).get("page", ""),
                        "city": city_en, "country": country_en, "at": datetime.utcnow().isoformat()}
        return f"/img/events/city/{key}"
    except Exception as exc:  # noqa: BLE001
        credits[key] = {"failed_at": datetime.utcnow().isoformat(), "error": str(exc)[:120], "city": city_en}
        return ""


# ---------- статус ----------

def load_status() -> dict:
    try:
        with open(STATUS_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return {}


def save_status(status: dict) -> None:
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    tmp = STATUS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(status, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, STATUS_FILE)


def crawl_is_due(interval_hours: int = 12) -> bool:
    last = load_status().get("last_run", "")
    if not last:
        return True
    try:
        return datetime.utcnow() - datetime.fromisoformat(last) >= timedelta(hours=interval_hours)
    except ValueError:
        return True


# ---------- база ----------

def _tokens(title: str) -> set[str]:
    words = re.findall(r"[a-zа-я0-9]+", (title or "").lower())
    return {w for w in words if w not in STOPWORDS and not re.fullmatch(r"20\d\d", w)}


def same_event(title_a: str, date_a: str, title_b: str, date_b: str) -> bool:
    """Ручное событие и событие источника — одно и то же: даты рядом и ≥2 общих слова."""
    try:
        gap = abs((date.fromisoformat(date_a) - date.fromisoformat(date_b)).days)
    except (TypeError, ValueError):
        return False
    if gap > 2:
        return False
    a, b = _tokens(title_a), _tokens(title_b)
    return len(a & b) >= 2 or (bool(a) and (a <= b or b <= a))


def upsert(db, Event, data: dict, status: dict, *, translate=translate_ru, make_og=None) -> tuple[object, str]:
    """Возвращает (event, 'created'|'updated'|'adopted')."""
    slug = make_slug(data["src_slug"], data["date_from"])
    ev = db.query(Event).filter(Event.slug == slug).first()
    action = "updated"
    if not ev:
        # ручное событие с теми же датами и названием → подхватываем, а не дублируем
        for cand in db.query(Event).filter(Event.source == "").all():
            if same_event(cand.title, cand.date_from, data["title"], data["date_from"]):
                ev, action = cand, "adopted"
                break
    if not ev:
        ev = Event(title=data["title"], date_from=data["date_from"])
        db.add(ev)
        action = "created"
    ev.slug = slug
    ev.source = SOURCE
    ev.source_url = data["source_url"]
    ev.title = data["title"]
    ev.date_from = data["date_from"]
    ev.date_to = data["date_to"]
    ev.city_en = data["city_en"]
    ev.country_en = data["country_en"]
    ev.country_iso = country_iso(country_ru(data["country_en"]))
    ev.city = city_label_ru(data["city_en"], data["country_en"])
    ev.venue = data["venue"]
    ev.organizer = data["organizer"]
    ev.organizer_url = data["organizer_url"]
    ev.url = data["url"] or ev.url or ""
    ev.socials = json.dumps(data["socials"], ensure_ascii=False)
    ev.cover_src = data["cover_src"]
    ev.sub_events = json.dumps(data["sub_events"], ensure_ascii=False)
    ev.category = data["category"] or ev.category or ""
    if data["description_en"] != (ev.description_en or ""):
        ev.description_en = data["description_en"]
        ev.description = translate(data["description_en"]) if translate else ""
    elif not (ev.description or "").strip() and translate:
        ev.description = translate(ev.description_en)
    ev.updated_at = datetime.utcnow()
    if not ev.image:
        ev.image = ensure_city_photo(data["city_en"], data["country_en"], status)
    if make_og:
        try:
            ev.og_image = make_og(ev) or ev.og_image or ""
        except Exception as exc:  # noqa: BLE001 — обложка не должна ронять прогон
            status.setdefault("errors", []).append(f"og {slug}: {str(exc)[:100]}")
    return ev, action


def deactivate_past(db, Event, today: date | None = None) -> int:
    """Прошедшие события уходят из календаря (страница остаётся). Скрытые админом не включаем."""
    today = today or date.today()
    n = 0
    for ev in db.query(Event).filter(Event.active == True).all():  # noqa: E712
        end = ev.date_to or ev.date_from
        try:
            if date.fromisoformat(end) < today - timedelta(days=1):
                ev.active = False
                n += 1
        except ValueError:
            continue
    return n


def run(SessionLocal, Event, *, force: bool = False, limit: int | None = None, make_og=None,
        translate=translate_ru, log=print) -> dict:
    """Полный прогон. Возвращает сводку и пишет её в data/events-crawler.json."""
    status = load_status()
    status["errors"] = []
    started = time.monotonic()
    summary = {"seen": 0, "fetched": 0, "created": 0, "updated": 0, "adopted": 0, "skipped": 0,
               "failed": 0, "deactivated": 0}
    try:
        entries = sitemap_entries(fetch_text(SITEMAP_URL))
    except Exception as exc:  # noqa: BLE001
        status["errors"].append(f"sitemap: {str(exc)[:160]}")
        status["last_error_at"] = datetime.utcnow().isoformat()
        save_status(status)
        log(f"[events] sitemap недоступен: {str(exc)[:120]}")
        return summary
    seen = status.setdefault("pages", {})
    known_slugs = set()
    with SessionLocal() as db:
        known_slugs = {s for (s,) in db.query(Event.slug).filter(Event.source == SOURCE).all() if s}
    todo = []
    for url, lastmod in entries:
        summary["seen"] += 1
        prev = seen.get(url, {})
        src = source_slug(url)
        fresh = prev.get("lastmod") == lastmod and any(s.startswith(src) for s in known_slugs)
        if fresh and not force:
            summary["skipped"] += 1
            continue
        todo.append((url, lastmod))
    if limit:
        todo = todo[:limit]
    log(f"[events] страниц в sitemap {summary['seen']}, к обходу {len(todo)}")
    for url, lastmod in todo:
        try:
            html_text = fetch_text(url)
            summary["fetched"] += 1
            data = parse_event_page(html_text, url)
            if not data:
                seen[url] = {"lastmod": lastmod, "at": datetime.utcnow().isoformat(), "skip": "no event"}
                continue
            with SessionLocal() as db:
                ev, action = upsert(db, Event, data, status, translate=translate, make_og=make_og)
                db.commit()
                summary[action] += 1
                log(f"[events] {action}: {ev.slug} ({data['date_from']}, {data['city_en']})")
            seen[url] = {"lastmod": lastmod, "at": datetime.utcnow().isoformat()}
        except Exception as exc:  # noqa: BLE001
            summary["failed"] += 1
            status["errors"].append(f"{source_slug(url)}: {str(exc)[:120]}")
            log(f"[events] ошибка {url}: {str(exc)[:120]}")
        time.sleep(REQUEST_PAUSE)
    with SessionLocal() as db:
        summary["deactivated"] = deactivate_past(db, Event)
        db.commit()
        summary["active"] = db.query(Event).filter(Event.active == True).count()  # noqa: E712
    status["last_run"] = datetime.utcnow().isoformat()
    status["last_summary"] = summary
    status["duration_s"] = round(time.monotonic() - started, 1)
    save_status(status)
    log(f"[events] готово за {status['duration_s']} c: {summary}")
    return summary


def rebake_covers(SessionLocal, Event, make_og, log=print) -> int:
    """Перепечь OG-карточки (после обновления фото городов) и подставить фото городов, где их не было."""
    n = 0
    status = load_status()
    with SessionLocal() as db:
        for ev in db.query(Event).filter(Event.slug != "").all():
            if not ev.image or ev.image.startswith("/img/events/city/"):
                ev.image = ensure_city_photo(ev.city_en or "", ev.country_en or "", status) if ev.city_en else ""
            try:
                ev.og_image = make_og(ev) or ""
                n += 1
            except Exception as exc:  # noqa: BLE001
                log(f"[events] og {ev.slug}: {str(exc)[:100]}")
        db.commit()
    save_status(status)
    log(f"[events] перепечено обложек: {n}")
    return n


if __name__ == "__main__":  # pragma: no cover — ручной прогон
    import argparse
    parser = argparse.ArgumentParser(description="Обход календаря TheGamblest → таблица events")
    parser.add_argument("--force", action="store_true", help="перекачать все страницы, не глядя на lastmod")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-translate", action="store_true")
    parser.add_argument("--og-only", action="store_true",
                        help="не ходить в источник: обновить фото городов и перепечь OG-карточки всех событий")
    args = parser.parse_args()
    from server import app as web
    from server import event_covers
    if args.og_only:
        rebake_covers(web.SessionLocal, web.Event, event_covers.make_og_for_event)
    else:
        run(web.SessionLocal, web.Event, force=args.force, limit=args.limit,
            make_og=event_covers.make_og_for_event, translate=None if args.no_translate else translate_ru)
