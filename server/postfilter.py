# -*- coding: utf-8 -*-
"""Что можно публиковать во внешние каналы: гео-правила и чистота языка.

Правила владельца (сентябрь 2026):

  • вакансии из США не идут ни в один канал — ни в английский, ни в русский;
  • акцент на Европу, следом СНГ (Тбилиси, Ереван, Киев) и удалёнка,
    остальное (Бразилия, Индия, Филиппины, Австралия) в каналы не идёт;
  • в английском посте не должно быть ни одного русского слова.

Локация в базе — свободный текст из десятка источников: «Las Vegas, NV, US»,
«Sliema, mt», «Киев, Украина», «Remote - US», «Europe - Remote». Поэтому
решаем по маркерам: слово-страна, слово-город, ISO-код после запятой.
Двухбуквенные коды берём только в позиции «…, mt» — иначе английские слова
«at», «is», «me», «in» превращаются в Австрию, Исландию, Черногорию и Индию.
Любой намёк на США перевешивает остальное: «London / New York» не постим.
"""
import os
import re

from server import terms as _terms

# ---------- языки ----------

CYRILLIC = re.compile(r"[а-яА-ЯёЁіїєґІЇЄҐ]")


def has_cyrillic(text: str) -> bool:
    return bool(CYRILLIC.search(text or ""))


# ---------- гео: слова ----------

US_WORDS = (
    "united states", "u.s.a", "u.s.", "сша", "штаты", "all us", "us only",
    "us-based", "remote - us", "remote, us", "remote (us",
    # города — только однозначные (Birmingham, Manchester, Cambridge,
    # Portland есть и в Европе, их не берём)
    "new york", "brooklyn", "new jersey", "jersey city", "hoboken",
    "las vegas", "atlantic city", "los angeles", "san francisco", "san diego",
    "san jose", "silicon valley", "atlanta", "denver", "miami", "orlando",
    "tampa", "jacksonville", "chicago", "boston", "philadelphia", "austin",
    "dallas", "houston", "san antonio", "seattle", "portland, or", "phoenix",
    "sacramento", "baltimore", "pittsburgh", "cleveland", "cincinnati",
    "detroit", "southfield", "minneapolis", "kansas city", "st. louis",
    "salt lake city", "indianapolis", "milwaukee", "louisville", "memphis",
    "nashville", "charlotte", "raleigh", "richmond, va", "lake tahoe",
    "washington, dc", "washington d.c", "wilmington, de", "west coast",
    "east coast", "north america", "северная америка",
    # штаты (Georgia пропущена намеренно — это ещё и страна СНГ)
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "illinois", "indiana", "iowa",
    "kansas", "kentucky", "louisiana", "maryland", "massachusetts",
    "michigan", "minnesota", "mississippi", "missouri", "montana",
    "nebraska", "nevada", "new hampshire", "new mexico", "north carolina",
    "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania",
    "rhode island", "south carolina", "south dakota", "tennessee", "texas",
    "utah", "vermont", "virginia", "west virginia", "wisconsin", "wyoming",
)
# Признаки американского оффера в тексте вакансии — смотрим, только когда
# страна нигде не названа («Remote», пустая локация): 401(k) не бывает у мальтийца.
US_HINTS = ("401(k)", "401k", "green card", "u.s. citizen", "us citizen",
            "united states", "authorized to work in the u", "eeo employer",
            "e-verify", "americans with disabilities", "pay transparency act",
            "u.s. work", "us work authorization", "sms/mms", "w-2")

EUROPE_WORDS = (
    "europe", "european union", "emea", "европ",
    "malta", "мальта", "valletta", "sliema", "st julian", "st. julian",
    "birkirkara", "gzira", "msida", "pieta", "pietà", "ta' xbiex", "swieqi",
    "san gwann", "naxxar", "mosta", "qormi", "marsa", "ta'xbiex",
    "cyprus", "кипр", "limassol", "nicosia", "larnaca", "paphos",
    "united kingdom", "великобритания", "england", "scotland", "wales",
    "london", "manchester", "edinburgh", "glasgow", "leeds", "birmingham",
    "stoke-on-trent", "hammersmith", "brighton", "bristol", "cardiff",
    "ireland", "ирландия", "dublin", "gibraltar", "гибралтар",
    "isle of man", "jersey, channel", "guernsey", "luxembourg", "люксембург",
    "monaco", "монако", "andorra",
    "poland", "польша", "warsaw", "warszawa", "krakow", "kraków", "poznan",
    "wroclaw", "gdansk", "katowice",
    "germany", "германия", "berlin", "munich", "münchen", "hamburg",
    "frankfurt", "cologne", "düsseldorf",
    "france", "франция", "paris", "bordeaux", "lyon", "marseille", "nice,",
    "spain", "испания", "madrid", "barcelona", "valencia", "malaga", "ceuta",
    "portugal", "португалия", "lisbon", "lisboa", "porto", "madeira",
    "italy", "италия", "rome", "roma", "milan", "milano", "turin",
    "netherlands", "нидерланды", "amsterdam", "rotterdam", "utrecht", "hague",
    "belgium", "бельгия", "brussels", "antwerp",
    "austria", "австрия", "vienna", "wien",
    "switzerland", "швейцария", "zurich", "geneva", "zug",
    "sweden", "швеция", "stockholm", "gothenburg", "malmo", "malmö",
    "norway", "норвегия", "oslo", "denmark", "дания", "copenhagen",
    "finland", "финляндия", "helsinki", "iceland", "исландия", "reykjavik",
    "estonia", "эстония", "tallinn", "tartu", "latvia", "латвия", "riga",
    "lithuania", "литва", "vilnius", "kaunas",
    "czech", "чехия", "prague", "praha", "brno",
    "slovakia", "словакия", "bratislava", "hungary", "венгрия", "budapest",
    "romania", "румыния", "bucharest", "bucurești", "bucuresti", "cluj",
    "iasi", "timisoara", "brasov",
    "bulgaria", "болгария", "sofia", "plovdiv", "varna", "burgas",
    "greece", "греция", "athens", "thessaloniki", "afины",
    "croatia", "хорватия", "zagreb", "split,", "slovenia", "словения",
    "ljubljana", "serbia", "сербия", "belgrade", "beograd", "novi sad",
    "montenegro", "черногория", "podgorica", "budva",
    "bosnia", "босния", "sarajevo", "banja luka",
    "macedonia", "македония", "skopje", "albania", "албания", "tirana",
    "moldova", "молдова", "молдавия", "chisinau", "chișinău",
    "ukraine", "украина", "україна", "kyiv", "kiev", "київ", "киев", "lviv",
    "львов", "l'viv", "odesa", "odessa", "kharkiv", "харьков", "dnipro",
    "днепр", "братислава", "будапешт", "варшава", "лондон", "прага", "рига",
)

CIS_WORDS = (
    "tbilisi", "t'bilisi", "тбилиси", "batumi", "батуми", "грузия",
    "georgia (country)",
    "yerevan", "ереван", "армения", "armenia", "gyumri",
    "kazakhstan", "казахстан", "almaty", "алматы", "astana", "астана",
    "uzbekistan", "узбекистан", "tashkent", "ташкент",
    "kyrgyz", "киргизия", "кыргызстан", "bishkek", "бишкек",
    "azerbaijan", "азербайджан", "baku", "баку",
    "belarus", "беларусь", "белоруссия", "minsk", "минск",
    "russia", "россия", "moscow", "москва", "санкт-петербург",
    "saint petersburg", "st petersburg",
)

OTHER_WORDS = (
    "brazil", "бразилия", "são paulo", "sao paulo", "rio de janeiro",
    "argentina", "buenos aires", "colombia", "medellín", "medellin",
    "bogotá", "bogota", "peru", "lima,", "chile", "santiago", "uruguay",
    "montevideo", "mexico", "мексика", "canada", "канада", "toronto",
    "vancouver", "montreal", "india", "индия", "bangalore", "bengaluru",
    "mumbai", "delhi", "noida", "gurugram", "pune", "hyderabad", "chennai",
    "philippines", "филиппины", "manila", "cebu", "australia", "австралия",
    "sydney", "melbourne", "brisbane", "perth", "nsw", "new zealand",
    "auckland", "south africa", "юар", "cape town", "johannesburg",
    "durban", "za-", "israel", "израиль", "tel aviv", "uae", "оаэ", "dubai",
    "дубай", "abu dhabi", "ras al-khaimah", "china", "китай", "shanghai",
    "beijing", "hong kong", "singapore", "japan", "япония", "tokyo",
    "korea", "seoul", "vietnam", "hanoi", "thailand", "bangkok",
    "malaysia", "kuala lumpur", "indonesia", "jakarta", "turkey", "турция",
    "istanbul", "стамбул", "nigeria", "kenya", "ghana", "egypt", "cairo",
    "morocco", "curacao", "curaçao", "кюрасао", "costa rica", "panama",
    "paraguay", "latam", "apac", "latin america", "латинская америка",
    "asia", "азия", "colombo", "шри-ланка", "sri lanka", "коста-рика",
    "san josé, коста", "africa", "африка", "saudi", "riyadh", "эр-рияд",
    "pretoria", "sao paolo", "qatar", "doha", "kuwait", "pakistan",
)

REMOTE_WORDS = ("remote", "удал", "віддал", "anywhere", "worldwide", "global",
                "distributed", "work from home", "wfh", "hybrid")

# ---------- гео: ISO-коды и коды штатов ----------

# Код берём только в позиции «…, mt» / «…(mt)», иначе английские слова
# «at», «is», «me», «in» превращаются в Австрию, Исландию, Черногорию, Индию.
ISO_RE = re.compile(r"[,(]\s*([A-Za-z]{2})\s*(?=[,)]|$)")
US_PREFIX_RE = re.compile(r"(?<![a-z])us-[a-z]{2}-", re.I)
US_WORD_RE = re.compile(r"(?<![a-z])(usa|u\.s\.?a?|us)(?![a-z])", re.I)
# В заголовке засчитываем только явное «USA»: одинокое «us» там — это «join us»
US_TITLE_RE = re.compile(r"(?<![a-z])(usa|u\.s\.a?)(?![a-z])", re.I)
EUROPE_TOKEN_RE = re.compile(r"(?<![a-z])(uk|eu)(?![a-z])", re.I)

EU_CODES = {"mt", "cy", "gb", "uk", "ie", "gi", "im", "pl", "de", "fr", "es",
            "pt", "it", "nl", "be", "at", "ch", "se", "no", "dk", "fi", "is",
            "ee", "lv", "lt", "cz", "sk", "hu", "ro", "bg", "gr", "hr", "si",
            "rs", "me", "ba", "mk", "al", "md", "ua", "lu", "mc", "eu"}
CIS_CODES = {"ge", "am", "kz", "uz", "kg", "az", "by", "ru"}
OTHER_CODES = {"br", "ar", "cl", "pe", "mx", "uy", "ca", "in", "ph", "au",
               "nz", "za", "il", "ae", "tr", "cn", "hk", "sg", "jp", "kr",
               "vn", "th", "my", "id", "ng", "ke", "eg", "ma", "cw", "co",
               "cr", "sa", "qa", "kw", "pk", "bd", "lk", "gh", "tz", "pa"}
US_STATES = {"ak", "al", "ar", "az", "ca", "co", "ct", "de", "fl", "ga", "hi",
             "ia", "id", "il", "in", "ks", "ky", "la", "ma", "md", "me", "mi",
             "mn", "mo", "ms", "mt", "nc", "nd", "ne", "nh", "nj", "nm", "nv",
             "ny", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut",
             "va", "vt", "wa", "wi", "wv", "wy"}
# Коды, которые одновременно штат и страна («mt» — Мальта и Монтана,
# «ca» — Канада и Калифорния). Различаем регистром: источники США пишут
# штат заглавными («Boston, MA»), ISO-источники страну строчными («Sliema, mt»).
AMBIGUOUS = US_STATES & (EU_CODES | CIS_CODES | OTHER_CODES)


# Имена стран для кодов, которые встречаются в локациях источников:
# «Sofia, bg» подписчик читать не должен. Таблица общая с сайтом
# (server/terms.py) — своя копия здесь уже отставала на десяток стран.
CODE_NAMES = {row["iso"].lower(): ru for ru, row in _terms.COUNTRIES.items()}

PRETTY_RE = re.compile(r"([,(])\s*([A-Za-z]{2})(?=[,)]|$)")


def pretty_location(location: str, lang: str = "ru") -> str:
    """«Sofia, bg» → «Sofia, Болгария» / «Sofia, Bulgaria»."""
    def name(match):
        sep, code = match.group(1), match.group(2)
        if code.isupper() and code.lower() in US_STATES:
            return match.group(0)
        country = CODE_NAMES.get(code.lower())
        if not country:
            return match.group(0)
        return f"{sep}{'' if sep == '(' else ' '}{_terms.country_name(country, lang)}"
    return PRETTY_RE.sub(name, location or "")


def _codes(location: str):
    """Коды из локации: (нижний регистр, был ли записан заглавными)."""
    return [(m.group(1).lower(), m.group(1).isupper())
            for m in ISO_RE.finditer(location or "")]


def _country_codes(location: str) -> set:
    """Только те коды, которые читаем как страну, а не как штат США."""
    return {code for code, upper in _codes(location)
            if not (upper and code in US_STATES)}


def _state_codes(location: str) -> set:
    return {code for code, upper in _codes(location)
            if code in US_STATES and (upper or code not in AMBIGUOUS)}


def _low(job) -> str:
    return f"{job.location or ''} {job.title or ''}".lower()


def is_us(job) -> bool:
    """США — по локации, заголовку и (когда страна нигде не названа) по
    признакам оффера вроде 401(k)."""
    location = job.location or ""
    text = _low(job)
    if any(word in text for word in US_WORDS):
        return True
    # «Sales Representative (USA)» — страна бывает названа только в заголовке
    if US_PREFIX_RE.search(text) or US_WORD_RE.search(location) \
            or US_TITLE_RE.search(job.title or ""):
        return True
    if any(word in text for word in EUROPE_WORDS + CIS_WORDS + OTHER_WORDS):
        return False
    if _country_codes(location) & (EU_CODES | CIS_CODES | OTHER_CODES):
        return False
    if _state_codes(location):
        return True
    # страна нигде не названа («Remote», пустая локация) — ищем признаки
    # американского оффера во всём тексте: 401(k) бывает глубоко в подвале
    body = (job.description or "").lower()
    return any(hint in body for hint in US_HINTS)


def region(job) -> str:
    """'us' | 'europe' | 'cis' | 'other' | 'remote' | 'unknown'.

    Слово-страна весомее ISO-кода: в «Gurugram, HR, IN» HR — это индийский
    штат Харьяна, а не Хорватия. Ответ держим на самом объекте: подборка
    спрашивает регион по нескольку раз, а разбор лезет во всё описание.
    """
    cached = getattr(job, "_tg_region", None)
    if cached:
        return cached
    zone = _region(job)
    try:
        job._tg_region = zone
    except Exception:                                           # noqa: BLE001
        pass
    return zone


def _region(job) -> str:
    if is_us(job):
        return "us"
    text = _low(job)
    codes = _country_codes(job.location or "")
    if any(w in text for w in EUROPE_WORDS) or EUROPE_TOKEN_RE.search(text):
        return "europe"
    if any(w in text for w in CIS_WORDS):
        return "cis"
    if any(w in text for w in OTHER_WORDS):
        return "other"
    if codes & EU_CODES:
        return "europe"
    if codes & CIS_CODES:
        return "cis"
    if codes & OTHER_CODES:
        return "other"
    if any(w in text for w in REMOTE_WORDS):
        return "remote"
    return "unknown"


# Порядок = приоритет в подборке: сначала Европа, потом СНГ, потом удалёнка.
RANK = {"europe": 0, "cis": 1, "remote": 2, "unknown": 3, "other": 9, "us": 9}
ALLOWED = tuple(x.strip() for x in os.environ.get(
    "SPINHIRE_TG_REGIONS", "europe,cis,remote").split(",") if x.strip())


def allowed(job, strict: bool = False) -> bool:
    """Пускаем ли вакансию в канал. strict — для одиночного поста «вакансия
    дня»: там непонятная гео недопустима, слишком заметное место."""
    zone = region(job)
    if zone in ALLOWED:
        return True
    return zone == "unknown" and not strict


def geo_rank(job) -> int:
    return RANK.get(region(job), 9)


# ---------- английский канал: ни одного русского слова ----------

def en_clean(text: str) -> str:
    """Русские куски строки вырезаем вместе с осиротевшими разделителями."""
    if not has_cyrillic(text):
        return text
    parts = [p.strip() for p in re.split(r"\s*[·|]\s*|,\s+", text or "")]
    keep = [p for p in parts if p and not has_cyrillic(p)]
    return " · ".join(keep)


def en_ready(job, salary: str = "", location: str = "") -> bool:
    """Вакансия годится для английского канала: латиница во всём, что увидит
    подписчик, — заголовок, компания, гео, вилка."""
    fields = (job.title or "", job.company_name or "",
              location if location is not None else (job.location or ""),
              salary or job.salary or "")
    return not any(has_cyrillic(f) for f in fields)
