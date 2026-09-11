# -*- coding: utf-8 -*-
"""Бот подбора вакансий: человек не уходит из Telegram, пока не откликнулся.

Зачем он есть. Реклама Telegram нас в свою вертикаль не пускает, а весь наш
трафик в мессенджере (закупки в каналах, свои @spinhire_ru / @spinhire,
рефералка) упирался в переход на сайт с регистрацией. Бот снимает этот шаг:
поиск, резюме и отклик происходят прямо в чате, а на сайт человек идёт уже
осознанно — за кабинетом и полным описанием.

Что умеет:
  • поиск по 7 тысячам вакансий словом на любом языке («биздев», «affiliate»);
  • резюме файлом или текстом → черновик профиля (та же эвристика, что на сайте,
    ежечасная задача потом причёсывает текст) → процент совпадения к вакансиям;
  • отклик в один тап — заводит аккаунт, дальше работает обычный конвейер:
    CRM, карточка Алине из leadbot, ссылка /claim работодателю;
  • подписка «присылать новые» — единственный бесплатный канал возврата
    человека, которого у борда нет: сайт даёт визит, бот даёт chat_id.

Аккаунт заводится на Telegram, а не на почту: у нас платят за контакт, а в
iGaming контакт — это @username, не e-mail. Ящик у таких аккаунтов служебный
(@telegram.spinhire.io), письма на него не уходят (resend_send его отсекает),
вместо писем человеку пишет бот.

Переменные окружения:
  SPINHIRE_JOBBOT_TOKEN    токен @spinhire_jobs_bot (НЕ тот, что постит в каналы)
  SPINHIRE_JOBBOT_SECRET   секрет в пути вебхука; по умолчанию — хэш токена
  SPINHIRE_JOBBOT_PUSH_HOURS   окно рассылки новых вакансий, по умолчанию 10-21
  SPINHIRE_JOBBOT_PUSH_REGIONS 1 — в подписку не уходят США (правило каналов)

Подключить вебхук после деплоя: POST /admin/jobbot/setup (нужен админ).
"""
import hashlib
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from functools import lru_cache
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import Session

from server.app import (APPLY_DAILY_LIMIT, APPLY_EXTRA_COST, APPLY_MIN_INTERVAL,
                        Application, ApplicationEvent, BASE_URL, Base, CV_UPLOAD_DIR,
                        Job, Resume, SIGNUP_COIN_BONUS, SessionLocal, User,
                        add_notification, anonymize_resume_text, db_session,
                        hash_pw, heuristic_cv_fields, match_score, need_admin,
                        CATEGORIES, TG_ACCOUNT_DOMAIN, country_of, resume_is_ready,
                        salary_usd, set_session, track)
from server.terms import REMOTE_COUNTRY, TERMS, UNKNOWN_COUNTRY
from server import postfilter

router = APIRouter()

TOKEN = os.environ.get("SPINHIRE_JOBBOT_TOKEN", "")
SECRET = (os.environ.get("SPINHIRE_JOBBOT_SECRET", "")
          or (hashlib.sha256(TOKEN.encode()).hexdigest()[:32] if TOKEN else ""))
SITE = (BASE_URL or "https://spinhire.io").rstrip("/")
CARDS = 3                       # вакансий в одном сообщении
START_CARDS = 5                 # на первом экране показываем пятёрку сразу
BANNER = f"{(BASE_URL or 'https://spinhire.io').rstrip('/')}/img/bot-welcome.jpg"
MAX_CARDS = 30                  # дальше «Ещё» не листаем — человеку пора на сайт
INDEX_TTL = 300                 # кэш поискового индекса, секунд
CV_LIMIT = 5 * 1024 * 1024
TZ_OFFSET = int(os.environ.get("SPINHIRE_TG_TZ_OFFSET", "3"))
_push_hours = os.environ.get("SPINHIRE_JOBBOT_PUSH_HOURS", "10-21").split("-")
PUSH_FROM, PUSH_TO = int(_push_hours[0]), int(_push_hours[-1])
# Правило каналов «США не постим» действует и здесь: аудитория у нас Европа,
# СНГ и удалёнка, американский оффер такому кандидату недоступен, а с топовой
# вилкой он ещё и вытесняет из выдачи то, на что реально можно откликнуться.
# Исключение — когда человек сам спросил про Штаты (см. US_QUERY_RE).
GEO_FILTER = os.environ.get("SPINHIRE_JOBBOT_REGIONS", "1") not in ("", "0")


# ---------- хранилище ----------

class BotChat(Base):
    """Диалог с кандидатом: что ищет, на что подписан, каким аккаунтом стал."""
    __tablename__ = "bot_chats"
    id = Column(Integer, primary_key=True)
    chat_id = Column(String, unique=True, nullable=False)
    username = Column(String, default="")
    first_name = Column(String, default="")
    lang = Column(String, default="ru")          # ru | en
    user_id = Column(Integer, default=None)      # аккаунт на сайте, когда завёлся
    state = Column(String, default="")           # "" | cv | title
    pending_job = Column(Integer, default=None)  # отклик ждёт резюме/должность
    query = Column(String, default="")           # последний поисковый запрос
    offset = Column(Integer, default=0)          # сколько карточек уже показано
    sub = Column(Integer, default=0)             # подписка на новые вакансии
    sub_query = Column(String, default="")
    sub_last = Column(String, default="")        # ISO последней рассылки
    source = Column(String, default="")          # payload из /start?start=…
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)


class BotLogin(Base):
    """Одноразовая ссылка входа на сайт — уходит только в личный чат владельца."""
    __tablename__ = "bot_logins"
    id = Column(Integer, primary_key=True)
    token = Column(String, unique=True, nullable=False)
    user_id = Column(Integer, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------- тексты ----------

T = {
 "start": {
  "ru": ("<b>SpinHire</b> — работа в казино, беттинге и партнёрских программах.\n\n"
         "В базе <b>{n}</b> вакансий. Ниже — пять самых денежных по СНГ прямо сейчас, "
         "дальше смотри кнопками.\n\n"
         "Резюме можно прислать файлом или просто ссылкой на LinkedIn — соберём сами."),
  "en": ("<b>SpinHire</b> — jobs in casino, betting and affiliate programmes.\n\n"
         "<b>{n}</b> openings in the base. Below are the five best paying right now, "
         "the rest is behind the buttons.\n\n"
         "Send your CV as a file or just drop a LinkedIn link — we'll build the profile."),
 },
 "menu": {
  "ru": "Что показать?",
  "en": "What should I show?",
 },
 "pick_cat": {
  "ru": "Направления — в скобках сколько открыто:",
  "en": "Areas — open roles in brackets:",
 },
 "pick_geo": {
  "ru": "Страны — в скобках сколько открыто:",
  "en": "Countries — open roles in brackets:",
 },
 "slice_top": {
  "ru": "Самые денежные вакансии в базе:",
  "en": "Top paying openings we have:",
 },
 "slice_fresh": {
  "ru": "Свежее за последние дни:",
  "en": "Added in the last few days:",
 },
 "slice_cat": {
  "ru": "{q} — <b>{n}</b> вакансий:",
  "en": "{q} — <b>{n}</b> openings:",
 },
 "found": {
  "ru": "По запросу «{q}» нашёл <b>{n}</b>. Самые денежные:",
  "en": "Found <b>{n}</b> for \"{q}\". Top paying:",
 },
 "found_all": {
  "ru": "По запросу «{q}» нашёл <b>{n}</b>:",
  "en": "Found <b>{n}</b> for \"{q}\":",
 },
 "more": {
  "ru": "Ещё по «{q}»:",
  "en": "More for \"{q}\":",
 },
 "approx": {
  "ru": "Точного совпадения по «{q}» нет. Вот ближайшее:",
  "en": "No exact match for \"{q}\". Closest:",
 },
 "empty": {
  "ru": ("По «{q}» сейчас ничего. Могу прислать, как только появится, — "
         "или попробуй другое слово: «саппорт», «аффилейт», «head of»."),
  "en": ("Nothing for \"{q}\" right now. I can ping you when it shows up — "
         "or try another word: \"support\", \"affiliate\", \"head of\"."),
 },
 "li_ok": {
  "ru": "Профиль забрал с LinkedIn: <b>{title}</b>{years}.",
  "en": "Pulled from LinkedIn: <b>{title}</b>{years}.",
 },
 "li_fail": {
  "ru": ("По этой ссылке профиль закрыт — LinkedIn отдаёт его только своим. "
         "Пришли резюме файлом (PDF или DOCX) или текстом, так надёжнее."),
  "en": ("That profile is not public — LinkedIn only shows it to logged-in users. "
         "Send the CV as a file (PDF or DOCX) or as text instead."),
 },
 "li_wait": {
  "ru": "Секунду, читаю профиль…",
  "en": "One moment, reading the profile…",
 },
 "cis_top": {
  "ru": "💰 Топ-5 по деньгам, СНГ:",
  "en": "💰 Top 5 by money, CIS:",
 },
 "need_cv": {
  "ru": ("Чтобы откликнуться, нужно резюме. Три способа, любой:\n"
         "• файл PDF или DOCX;\n"
         "• ссылка на профиль LinkedIn — соберём по ней сами;\n"
         "• просто текст резюме одним сообщением.\n\n"
         "Работодатель получает анонимную карточку; имя и контакт он открывает "
         "за деньги — поэтому твои данные не расходятся по базам."),
  "en": ("An application needs a CV. Any of the three:\n"
         "• a PDF or DOCX file;\n"
         "• a LinkedIn profile link — we'll build the profile from it;\n"
         "• the CV text pasted as one message.\n\n"
         "The employer sees an anonymous card; your name and contact are unlocked "
         "for money — so your data doesn't leak into random databases."),
 },
 "cv_bad": {
  "ru": "Не смог прочитать файл. Пришли PDF или DOCX до 5 МБ — или вставь текст резюме сообщением.",
  "en": "Couldn't read the file. Send a PDF or DOCX under 5 MB — or paste the CV as text.",
 },
 "cv_ok": {
  "ru": "Резюме принял: <b>{title}</b>{years}.",
  "en": "CV saved: <b>{title}</b>{years}.",
 },
 "ask_title": {
  "ru": "Как называется твоя должность? Одной строкой — например «VIP Account Manager».",
  "en": "What's your job title? One line — e.g. \"VIP Account Manager\".",
 },
 "applied": {
  "ru": ("Отклик отправлен: <b>{title}</b> — {company}.\n\n"
         "Мы передаём его работодателю напрямую. Ответ придёт сюда, в чат."),
  "en": ("Application sent: <b>{title}</b> — {company}.\n\n"
         "We pass it to the employer directly. Their answer lands here, in this chat."),
 },
 "applied_already": {
  "ru": "На эту вакансию ты уже откликался.",
  "en": "You've already applied to this one.",
 },
 "limit": {
  "ru": "На сегодня лимит откликов ({n}) исчерпан — так борд защищает работодателей от веерной рассылки. Завтра снова.",
  "en": "Daily application limit ({n}) reached — that's how the board keeps employers from mass-blasting. Try tomorrow.",
 },
 "too_fast": {
  "ru": "Секунду — отклики можно отправлять не чаще раза в {n} секунд.",
  "en": "Hold on — one application per {n} seconds.",
 },
 "gone": {
  "ru": "Эта вакансия уже снята.",
  "en": "This opening is gone.",
 },
 "subbed": {
  "ru": "Подписал на «{q}» — пришлю, как появятся новые. Отключить: /stop",
  "en": "Subscribed to \"{q}\" — I'll ping you on new ones. Turn off: /stop",
 },
 "unsubbed": {
  "ru": "Рассылку выключил. Поиск работает как раньше.",
  "en": "Alerts off. Search still works.",
 },
 "fresh": {
  "ru": "Новое по «{q}»:",
  "en": "New for \"{q}\":",
 },
 "help": {
  "ru": ("Напиши должность — покажу вакансии. Пришли резюме файлом — посчитаю совпадение.\n\n"
         "/jobs — свежие вакансии\n/cv — обновить резюме\n/stop — выключить рассылку\n"
         "/lang — русский / English"),
  "en": ("Type a role — I'll show openings. Send a CV file — I'll score the match.\n\n"
         "/jobs — latest openings\n/cv — update CV\n/stop — turn alerts off\n"
         "/lang — Russian / English"),
 },
 "cabinet": {
  "ru": "Кабинет на сайте",
  "en": "Open web account",
 },
 "btn_apply": {"ru": "Откликнуться {i}", "en": "Apply {i}"},
 "btn_more": {"ru": "Ещё {n}", "en": "More {n}"},
 "btn_sub": {"ru": "Присылать новые", "en": "Alert me"},
 "btn_open": {"ru": "Открыть {i}", "en": "Open {i}"},
 "btn_all": {"ru": "Все вакансии на сайте", "en": "All openings on the site"},
}

MENU = {
    "cats": {"ru": "🔎 По направлениям", "en": "🔎 By area"},
    "geos": {"ru": "🌍 По странам", "en": "🌍 By country"},
    "top": {"ru": "💰 Топ зарплат", "en": "💰 Top paying"},
    "fresh": {"ru": "🆕 Свежие", "en": "🆕 Newest"},
    "cv": {"ru": "📄 Загрузить резюме", "en": "📄 Upload CV"},
    "sub_on": {"ru": "🔔 Присылать новые", "en": "🔔 Alert me"},
    "sub_off": {"ru": "🔕 Отключить рассылку", "en": "🔕 Stop alerts"},
    "site": {"ru": "🌐 Открыть сайт", "en": "🌐 Open the site"},
    "back": {"ru": "← Меню", "en": "← Menu"},
    "menu_btn": {"ru": "☰ Всё меню", "en": "☰ Full menu"},
}


def t(key: str, lang: str, **kw) -> str:
    return T[key].get(lang, T[key]["en"]).format(**kw)


# ---------- телеграм ----------

def api(method: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/{method}", data=body,
        headers={"Content-Type": "application/json",
                 "User-Agent": "SpinHire/1.0 (+https://spinhire.io)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read())
        except Exception:                                      # noqa: BLE001
            return {"ok": False, "error": f"HTTP {exc.code}"}
    except Exception as exc:                                   # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def send(chat_id, text: str, keyboard: list = None) -> dict:
    payload = {"chat_id": str(chat_id), "text": text[:4000], "parse_mode": "HTML",
               "disable_web_page_preview": True}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    resp = api("sendMessage", payload)
    if not resp.get("ok") and resp.get("error_code") == 429:
        wait = int((resp.get("parameters") or {}).get("retry_after") or 3)
        time.sleep(min(wait + 1, 30))
        resp = api("sendMessage", payload)
    return resp


def send_photo(chat_id, photo: str, caption: str, keyboard: list = None) -> dict:
    """Фото с подписью. Telegram показывает его крупно — пустой текстовый экран
    на первом касании выглядит как служебный скрипт, а не как продукт."""
    payload = {"chat_id": str(chat_id), "photo": photo, "caption": caption[:1024],
               "parse_mode": "HTML"}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    return api("sendPhoto", payload)


def esc(value: str) -> str:
    return (value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def notify_user(db: Session, user_id: int, text: str, keyboard: list = None) -> bool:
    """Написать в бот владельцу аккаунта. Ради этого мы и держим chat_id."""
    if not TOKEN or not user_id:
        return False
    chat = db.query(BotChat).filter_by(user_id=user_id).first()
    if not chat:
        return False
    return bool(send(chat.chat_id, text, keyboard).get("ok"))


# ---------- поиск ----------

STOP = {"работа", "вакансия", "вакансии", "ищу", "хочу", "job", "jobs", "work",
        "looking", "for", "the", "and", "manager"}

# Сленг и сокращения, которыми люди пишут свою роль в чат. Слева — как пишут,
# справа — как это называется в вакансиях.
SYNONYMS = {
    "биздев": ("business development", "bizdev", "sales", "partnership"),
    "bd": ("business development", "bizdev"),
    "саппорт": ("support", "customer support", "customer service"),
    "поддержка": ("support", "customer support"),
    "суппорт": ("support", "customer support"),
    "вип": ("vip", "vip account", "vip manager"),
    "ретеншн": ("retention", "crm"),
    "ретеншен": ("retention", "crm"),
    "аффилейт": ("affiliate",),
    "аффилиат": ("affiliate",),
    "партнёрка": ("affiliate", "partnership"),
    "партнерка": ("affiliate", "partnership"),
    "медиабаер": ("media buyer", "media buying", "user acquisition"),
    "медиабайер": ("media buyer", "media buying", "user acquisition"),
    "баер": ("media buyer", "media buying"),
    "трафик": ("media buying", "user acquisition", "traffic"),
    "маркетолог": ("marketing", "marketer"),
    "разработчик": ("developer", "engineer"),
    "программист": ("developer", "engineer"),
    "тестировщик": ("qa", "test engineer"),
    "аналитик": ("analyst", "analytics"),
    "дизайнер": ("designer", "design"),
    "рекрутер": ("recruiter", "talent acquisition"),
    "бухгалтер": ("accountant", "finance"),
    "юрист": ("legal", "lawyer", "counsel"),
    "комплаенс": ("compliance", "aml", "kyc"),
    "антифрод": ("fraud", "risk", "payments"),
    "платежи": ("payments", "psp"),
    "трейдер": ("trader", "trading", "sportsbook"),
    "беттинг": ("betting", "sportsbook", "odds"),
    "дилер": ("live dealer", "dealer", "presenter"),
    "ведущий": ("presenter", "live dealer"),
    "руководитель": ("head of", "lead", "director", "manager"),
    "директор": ("director", "head of", "chief"),
    "продажи": ("sales", "business development"),
    "менеджер": ("manager",),
    "продакт": ("product manager", "product owner"),
    "проджект": ("project manager", "delivery"),
    "контент": ("content", "copywriter"),
    "сео": ("seo",),
    "смм": ("social media", "smm"),
    "хр": ("hr", "people", "recruiter"),
    "эйчар": ("hr", "people", "recruiter"),
}

# «ищу работу в США», «usa remote» — человек спросил прямо, гео-правило снимаем
US_QUERY_RE = re.compile(r"(?i)(\busa\b|u\.s\.|united states|америк|сша|штат)")

def _geo_map() -> dict:
    """«польша» → («poland», «польша»). Локации в базе есть и по-русски, и по-английски,
    а человек в чате пишет страну в любом падеже — сравниваем по основе слова."""
    out = {}
    from server import terms as _terms
    for ru, row in _terms.COUNTRIES.items():
        low, en = ru.lower(), row["en"].lower()
        stem = low[:-2] if len(low) > 6 else (low[:-1] if len(low) > 4 else low)
        out[stem] = out[en] = (en, low)      # «польша», «в Польше» и «Poland»
    for extra, pair in (("usa", ("usa", "united states", "сша")),
                        ("сша", ("usa", "united states", "сша")),
                        ("лимассол", ("limassol", "лимассол")),
                        ("варшав", ("warsaw", "варшава")),
                        ("тбилис", ("tbilisi", "тбилиси")),
                        ("ерева", ("yerevan", "ереван")),
                        ("белград", ("belgrade", "белград")),
                        ("удал", ("remote", "удалён", "удален")),
                        ("remote", ("remote", "удалён", "удален")),
                        ("релокейт", ("relocation", "релокация"))):
        out[extra] = pair
    return out


GEO = _geo_map()
# Компилируем на импорте: иначе каждое сообщение в чате прогоняло бы по запросу
# три сотни регулярок стран и полсотни синонимов — это 0,4 с на ровном месте.
GEO_RE = {stem: re.compile(rf"(?<![а-яёa-z])({re.escape(stem)}[а-яё]{{0,3}})(?![а-яёa-z])")
          for stem in GEO}
SYNONYM_RE = {key: re.compile(rf"(?<![а-яёa-z]){re.escape(key)}[а-яё]{{0,3}}(?![а-яёa-z])")
              for key in SYNONYMS}

# «в год», «per annum», «/yr» — там, где источник период назвал
YEARLY_WORDS = ("в год", "год", "year", "annual", "p.a", "per annum", "/yr", "рік", "річн")
PLAUSIBLE_MONTH = 40000      # выше — ошибка парсинга источника, а не зарплата


def month_usd(salary: str) -> int:
    """Вилка → доллары в месяц. Ноль, если числу нельзя верить.

    Британские и мальтийские объявления пишут «£85,000 to £100,000» без слова
    «в год», и общий salary_usd() читает это как месяц. В сортировке «топ
    зарплат» такая вакансия навсегда встаёт выше честных $6 000/мес, поэтому
    неразмеченные большие числа считаем годовыми, а совсем невероятные —
    мусором источника («Game Presenter, €1 815 293 в год»).
    """
    if not any(c.isdigit() for c in (salary or "")):
        return 0
    usd = salary_usd(salary)
    low = salary.lower()
    if usd >= 20000 and not any(word in low for word in YEARLY_WORDS):
        usd //= 12
    return 0 if usd > PLAUSIBLE_MONTH else usd


_index_cache = {"at": 0.0, "rows": []}


# Страны, ради которых бот и живёт: аудитория русскоязычная. Имена — как их
# отдаёт country_of(), то есть канонические русские.
CIS_COUNTRIES = {"Украина", "Беларусь", "Казахстан", "Грузия", "Армения", "Азербайджан",
                 "Узбекистан", "Киргизия", "Кыргызстан", "Молдова", "Россия",
                 "Таджикистан", "Туркменистан"}


@lru_cache(maxsize=4096)
def _region_place(location: str) -> str:
    return postfilter.region(SimpleNamespace(title="", location=location, description=""))


@lru_cache(maxsize=4096)
def country_cached(location: str) -> str:
    return country_of(location)


def region_of(location: str, title: str) -> str:
    """Регион вакансии. Кэш держим по месту, а не по паре с заголовком.

    Разбор региона лезет во все словари стран и на 5 тысячах строк стоил
    11 секунд — собеседник в чате столько не ждёт. Разных локаций семь сотен
    на пять тысяч вакансий, поэтому считаем по локации, а заголовок
    переспрашиваем только у невнятных («Remote», пусто): «Sales Rep (USA)»
    страну называет именно там.
    """
    zone = _region_place(location)
    if zone in ("remote", "unknown") and title:
        zone = postfilter.region(SimpleNamespace(title=title, location=location,
                                                 description=""))
    return zone


def job_index(db: Session) -> list:
    """Лёгкий индекс одобренных вакансий: в чате нельзя ждать секунду на запрос."""
    now = time.time()
    if _index_cache["rows"] and now - _index_cache["at"] < INDEX_TTL:
        return _index_cache["rows"]
    rows = (db.query(Job.id, Job.title, Job.company_name, Job.category, Job.location,
                     Job.fmt, Job.salary, Job.tags, Job.created_at)
            .filter(Job.status == "approved").all())
    out = []
    for r in rows:
        title, company = r.title or "", r.company_name or ""
        tags, category = r.tags or "", r.category or ""
        location, salary = r.location or "", r.salary or ""
        out.append({
            "id": r.id, "title": title, "company": company, "location": location,
            "fmt": r.fmt or "", "salary": salary, "category": category,
            "created": r.created_at or datetime(2020, 1, 1),
            "usd": month_usd(salary),
            "title_low": title.lower(),
            "meta_low": f"{tags} {category}".lower(),
            "where_low": f"{company} {location} {r.fmt or ''}".lower(),
            # регион и страна разбираются по всему тексту и спрашиваются на каждый
            # запрос — держим ответ в индексе, а не считаем на 7 тысячах строк заново
            "region": region_of(location, title),
            "country": country_cached(location) if location else (
                REMOTE_COUNTRY if (r.fmt or "") == "удалёнка" else UNKNOWN_COUNTRY),
        })
    _index_cache.update(at=now, rows=out)
    return out


def concepts(query: str) -> list:
    """Запрос → список смысловых кусков: [(вес, {варианты написания})].

    Кусок — это одно понятие во всех известных нам написаниях: «саппорт» и
    «customer support» — один кусок, «саппорт» и «Польша» — два разных.
    """
    low = " ".join((query or "").lower().split())
    groups, covered = [], set()
    for key, values in SYNONYMS.items():
        # «продажам», «саппорта», «аффилейтом» — падеж не должен ломать распознавание
        if SYNONYM_RE[key].search(low):
            groups.append(("role", {key, *values}))
            covered.add(key)
    for stem, names in GEO.items():
        found = GEO_RE[stem].search(low)
        if found:
            groups.append(("geo", set(names)))
            covered.add(found.group(1))
    for word in re.findall(r"[a-zа-яё0-9+#.]{3,}", low):
        if word in STOP or word in covered or any(word in key for key in covered):
            continue
        covered.add(word)
        groups.append(("role", {word}))
    return [(kind, _matcher(kind, terms)) for kind, terms in groups]


def _matcher(kind: str, terms: set):
    """Роль ищем по границам слова, место — подстрокой.

    «unity» внутри «opportunity» — это не Unity, и такой мусор выдавал 226
    вакансий вместо честного нуля. У стран наоборот: «Кипр» должен находиться
    в «Кипре», а «удал» — в «удалёнке».
    """
    if kind == "geo":
        return lambda text: any(term in text for term in terms)
    rx = re.compile(r"(?<![a-zа-яё0-9])(?:%s)(?![a-zа-яё0-9])"
                    % "|".join(_stemmed(term) for term in sorted(terms, key=len, reverse=True)))
    return lambda text: bool(rx.search(text))


def _stemmed(term: str) -> str:
    """Русское слово ищем с любым окончанием: в вакансиях «продажи», в запросе «продажам»."""
    body = re.escape(term)
    return body + r"[а-яё]{0,3}" if re.search(r"[а-яё]", term) else body


def hit(row: dict, kind: str, match) -> int:
    """Насколько кусок запроса попал в вакансию. Синонимы не складываем —
    берём лучшее написание, иначе «Customer Support» обгонял бы «Support Agent»
    только потому, что мы знаем для роли два слова."""
    if kind == "geo":
        return (8 if match(row["where_low"]) else 4 if match(row["title_low"]) else 0)
    return (10 if match(row["title_low"]) else
            5 if match(row["meta_low"]) else
            2 if match(row["where_low"]) else 0)


def geo_ok(row: dict) -> bool:
    """Пускаем ли вакансию в чат: те же регионы, что и в каналы."""
    zone = row.get("region") or "unknown"
    return zone in postfilter.ALLOWED or zone == "unknown"


def search(db: Session, query: str) -> tuple:
    """(вакансии, точное ли совпадение). Сначала по смыслу, внутри уровня — по деньгам.

    Деньги вперёд ставим осознанно: человек пришёл из мессенджера, ему нужен
    повод остаться, а не хронология. Но денежная вакансия не перепрыгивает
    более точную по роли — иначе «биздев» отдаёт CTO за $12k, и человек уходит.
    """
    rows = job_index(db)
    if GEO_FILTER and not US_QUERY_RE.search(query or ""):
        rows = [r for r in rows if geo_ok(r)]
    if not (query or "").strip():
        fresh = sorted(rows, key=lambda r: -r["created"].timestamp())[:200]
        return sorted(fresh, key=lambda r: (-r["usd"], -r["created"].timestamp())), True
    parts = concepts(query)
    if not parts:
        return [], True
    low = " ".join(query.lower().split())
    strict, loose = [], []
    for row in rows:
        hits = [hit(row, kind, match) for kind, match in parts]
        total = sum(hits)
        if not total:
            continue
        if low in row["title_low"]:
            total += 6                       # точное название роли из запроса
        (strict if all(hits) else loose).append((total, row))
    # Все слова запроса найдены — показываем только такие. «unity разработчик»
    # не должен выдавать 1300 любых инженеров: обещание «нашёл N» держит нас.
    scored, exact = (strict, True) if strict else (loose, False)
    if not scored:
        return [], True
    best = max(score for score, _row in scored)

    def tier(score: int) -> int:
        ratio = score / best
        return 0 if ratio >= 0.9 else 1 if ratio >= 0.6 else 2

    scored.sort(key=lambda pair: (tier(pair[0]), -pair[1]["usd"],
                                  -pair[1]["created"].timestamp()))
    return [row for _s, row in scored], exact


# ---------- карточки ----------

def card(row: dict, index: int, lang: str, fit: dict = None) -> str:
    head = f"{index}. <b>{esc(row['title'])}</b>"
    where = " · ".join(x for x in (esc(row["company"]), esc(row["location"]),
                                   esc(row["fmt"])) if x)
    money = row["salary"] if any(c.isdigit() for c in row["salary"]) else ""
    lines = [head, where]
    if money:
        lines.append(f"💰 {esc(money)}")
    if fit and fit.get("percent"):
        word = "совпадение" if lang == "ru" else "match"
        lines.append(f"🎯 {word} {fit['percent']}%")
    return "\n".join(x for x in lines if x)


def jobs_message(db: Session, chat: BotChat, rows: list, offset: int,
                 header: str, limit: int = CARDS) -> tuple:
    """Текст + клавиатура для пачки вакансий."""
    lang = chat.lang
    page = rows[offset:offset + limit]
    cv = None
    if chat.user_id:
        candidate = db.query(Resume).filter_by(user_id=chat.user_id).first()
        cv = candidate if resume_is_ready(candidate) else None
    blocks, keyboard = [header], []
    for i, row in enumerate(page, start=offset + 1):
        fit = {}
        if cv:
            fit = match_score(cv, SimpleNamespace(
                title=row["title"], tags=row["meta_low"], description="",
                fmt=row["fmt"], language_list=[]), light=True)
        blocks.append(card(row, i, lang, fit))
        keyboard.append([
            {"text": t("btn_apply", lang, i=i), "callback_data": f"a:{row['id']}"},
            {"text": t("btn_open", lang, i=i), "url": f"{SITE}/job/{row['id']}"},
        ])
    tail = []
    if offset + limit < min(len(rows), MAX_CARDS):
        tail.append({"text": t("btn_more", lang, n=CARDS),
                     "callback_data": f"m:{offset + limit}"})
    if not chat.sub:
        tail.append({"text": t("btn_sub", lang), "callback_data": "s:1"})
    if tail:
        keyboard.append(tail)
    keyboard.append([{"text": MENU["menu_btn"][lang], "callback_data": "menu"},
                     {"text": t("btn_all", lang), "url": site_link(chat.query)}])
    return "\n\n".join(blocks), keyboard


def site_link(spec: str) -> str:
    """Тот же срез, но на сайте: человек не должен искать заново."""
    kind, _, value = (spec or "").partition(":")
    if kind == "cat":
        return f"{SITE}/jobs?cat=" + urllib.parse.quote(value)
    if kind in ("geo", "top", "fresh") or not spec:
        return f"{SITE}/jobs"
    return f"{SITE}/jobs?q=" + urllib.parse.quote(spec)


def label_of(name: str, lang: str) -> str:
    """Русское имя направления или страны на языке собеседника."""
    return TERMS.get(lang, {}).get(name, name) if lang != "ru" else name


def by_money(rows: list) -> list:
    return sorted(rows, key=lambda r: (-r["usd"], -r["created"].timestamp()))


def slice_rows(db: Session, spec: str) -> tuple:
    """Срез базы по кнопке или по слову: (вакансии, точное ли совпадение, заголовок).

    Одна точка входа на все способы посмотреть базу — иначе кнопка «Ещё»
    не знает, что именно листает.
    """
    kind, _, value = spec.partition(":")
    if kind in ("cat", "geo", "top", "fresh", "cis"):
        rows = [r for r in job_index(db) if geo_ok(r)]
        if kind == "cis":
            # Аудитория у бота русскоязычная: на первом экране показываем то, куда
            # её реально возьмут. Берём по стране, а не по region(): Украину
            # postfilter числит Европой, и «СНГ» без неё — это полсотни вакансий.
            near = [r for r in rows if r["country"] in CIS_COUNTRIES]
            paid = by_money([r for r in near if r["usd"]])
            return (paid or by_money(near) or by_money([r for r in rows if r["usd"]]),
                    True, spec)
        if kind == "cat":
            return by_money([r for r in rows if r["category"] == value]), True, spec
        if kind == "geo":
            return by_money([r for r in rows if r["country"] == value]), True, spec
        if kind == "top":
            return by_money([r for r in rows if r["usd"]]), True, spec
        newest = sorted(rows, key=lambda r: -r["created"].timestamp())[:60]
        return newest, True, spec
    rows, exact = search(db, spec)
    return rows, exact, spec


def slice_header(spec: str, rows: list, offset: int, exact: bool, lang: str) -> str:
    kind, _, value = spec.partition(":")
    if offset:
        name = label_of(value, lang) if kind in ("cat", "geo") else esc(spec)
        return t("more", lang, q=esc(name if kind in ("cat", "geo") else spec))
    if kind == "cat" or kind == "geo":
        return t("slice_cat", lang, q=esc(label_of(value, lang)), n=len(rows))
    if kind == "top":
        return t("slice_top", lang)
    if kind == "cis":
        return t("cis_top", lang)
    if kind == "fresh":
        return t("slice_fresh", lang)
    if not exact:
        return t("approx", lang, q=esc(spec))
    # «Самые денежные» обещаем, только если деньги в карточках действительно
    # есть: у половины агрегированных вакансий вилки нет, и заголовок-обманка
    # стоит дороже, чем скромный «нашёл N».
    with_salary = sum(1 for row in rows[:CARDS] if row["usd"])
    if len(rows) > CARDS and with_salary >= 2:
        return t("found", lang, q=esc(spec), n=len(rows))
    return t("found_all", lang, q=esc(spec), n=len(rows))


def show_jobs(db: Session, chat: BotChat, spec: str, offset: int = 0,
              limit: int = CARDS) -> None:
    rows, exact, spec = slice_rows(db, spec)
    lang = chat.lang
    chat.query, chat.offset = spec, offset
    if not rows:
        keyboard = [[{"text": t("btn_sub", lang), "callback_data": "s:1"}],
                    [{"text": MENU["back"][lang], "callback_data": "menu"}]]
        send(chat.chat_id, t("empty", lang, q=esc(spec)), keyboard)
        track(db, "bot_search_empty", chat.user_id, "bot", None, q=spec[:80])
        return
    header = slice_header(spec, rows, offset, exact, lang)
    text, keyboard = jobs_message(db, chat, rows, offset, header, limit)
    send(chat.chat_id, text, keyboard)
    track(db, "bot_slice", chat.user_id, "bot", None, spec=spec[:80], found=len(rows))


# ---------- аккаунт, резюме, отклик ----------

def ensure_account(db: Session, chat: BotChat) -> User:
    """Аккаунт заводится молча и на Telegram: лишний вопрос про почту стоит нам отклика."""
    from sqlalchemy import func
    if chat.user_id:
        existing = db.get(User, chat.user_id)
        if existing:
            return existing
    email = f"tg{chat.chat_id}@{TG_ACCOUNT_DOMAIN}"
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if not user:
        source = "telegram-bot" + (f":{chat.source}" if chat.source else "")
        user = User(email=email, password_hash=hash_pw(secrets.token_urlsafe(24)),
                    name=(chat.first_name or "")[:80], role="talent", verified=1,
                    coins=SIGNUP_COIN_BONUS, lang=chat.lang, signup_source=source[:200])
        db.add(user)
        db.flush()
        track(db, "signup", user.id, "user", user.id, source="tgbot")
    chat.user_id = user.id
    return user


def login_link(db: Session, user: User) -> str:
    """Одноразовая ссылка входа: у аккаунта из бота пароля нет и почты тоже."""
    token = secrets.token_urlsafe(24)
    db.add(BotLogin(token=token, user_id=user.id))
    return f"{SITE}/tg/login/{token}"


LINKEDIN_RE = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/[^\s?#]+", re.I)
# Публичный профиль отдаётся обычному браузеру и без логина — этого хватает на
# заголовок, «о себе», место и опыт. Ходим строго по ссылке, которую человек дал
# сам, один раз на кандидата: аккаунта в этом запросе нет, банить нечего.
LI_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/127.0 Safari/537.36")


def _og(html: str, prop: str) -> str:
    found = re.search(rf'property="{prop}"\s+content="([^"]*)"', html)
    if not found:
        found = re.search(rf'content="([^"]*)"\s+property="{prop}"', html)
    value = found.group(1) if found else ""
    for entity, char in (("&amp;", "&"), ("&quot;", '"'), ("&#39;", "'"),
                         ("&lt;", "<"), ("&gt;", ">"), ("&middot;", "·")):
        value = value.replace(entity, char)
    return value.strip()


def linkedin_fields(url: str) -> dict:
    """Публичный профиль LinkedIn → черновик резюме. Пусто — профиль закрыт."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": LI_UA, "Accept-Language": "en-US,en;q=0.9"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            html = resp.read(900_000).decode("utf8", "ignore")
    except Exception:                                          # noqa: BLE001
        return {}
    title_raw, desc = _og(html, "og:title"), _og(html, "og:description")
    if not title_raw or not desc:
        return {}
    # «Имя Фамилия - Head of CRM at Acme | LinkedIn»
    name, _, headline = title_raw.split(" | LinkedIn")[0].partition(" - ")
    parts = [p.strip() for p in desc.split("·") if p.strip()]
    location, experience, education, summary = "", "", "", []
    for part in parts:
        low = part.lower()
        if low.startswith("location:"):
            location = part.split(":", 1)[1].strip()
        elif low.startswith("experience:"):
            experience = part.split(":", 1)[1].strip()
        elif low.startswith("education:"):
            education = part.split(":", 1)[1].strip()
        elif "connections on linkedin" in low or "followers" in low:
            continue
        else:
            summary.append(part)
    about_parts = summary + ([f"Experience: {experience}"] if experience else [])
    about = anonymize_resume_text(" ".join(about_parts))
    for token in (name or "").split():
        if len(token) > 2:
            about = re.sub(r"(?i)(?<!\w)" + re.escape(token) + r"(?!\w)", "", about)
    about = re.sub(r"\s{2,}", " ", about).strip()
    from server.app import CV_SKILL_WORDS
    low_all = f"{headline} {desc}".lower()
    skills = [w for w in CV_SKILL_WORDS
              if re.search(r"(?<![a-zа-я])" + re.escape(w.lower()) + r"(?![a-zа-я])", low_all)]
    langs = [w for w in skills if w in ("English", "German", "Spanish", "French",
                                        "Portuguese", "Italian", "Polish", "Turkish",
                                        "Ukrainian", "Russian")]
    out = {"title": (headline or "").strip()[:120], "about": about[:900],
           "skills": ", ".join(w for w in skills if w not in langs)[:400],
           "languages": ", ".join(langs), "location": location[:120],
           "education": education[:200]}
    return out if out["title"] else {}


def _text_cv_fields(text: str, person_name: str = "") -> dict:
    """Поля профиля из резюме, вставленного текстом (файл разбирает эвристика сайта)."""
    from server.app import CV_SKILL_WORDS, CV_TITLE_HINTS, clean_role_title
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Половина людей вставляет резюме одним абзацем без переносов, поэтому в
    # кандидаты на должность идут и куски первой строки до точки или тире.
    chunks = list(lines[:25])
    for line in lines[:3]:
        chunks.extend(part.strip() for part in re.split(r"[.•|—–\u2022]", line))
    title = ""
    for chunk in chunks:
        low = chunk.lower()
        if 6 <= len(chunk) <= 90 and any(h in low for h in CV_TITLE_HINTS) and "@" not in chunk:
            title = clean_role_title(chunk, person_name)
            if title:
                break
    low_text = text.lower()
    skills = [w for w in CV_SKILL_WORDS
              if re.search(r"(?<![a-zа-я])" + re.escape(w.lower()) + r"(?![a-zа-я])", low_text)]
    years = 0
    m = re.search(r"(\d{1,2})\+?\s*(?:years?|yrs|лет|года)", low_text)
    if m:
        years = min(int(m.group(1)), 40)
    langs = [w for w in skills if w in ("English", "German", "Spanish", "French", "Portuguese",
                                        "Italian", "Polish", "Turkish", "Ukrainian", "Russian")]
    return {"title": title, "experience_years": years,
            "skills": ", ".join(w for w in skills if w not in langs)[:400],
            "languages": ", ".join(langs),
            "about": anonymize_resume_text(" ".join(text.split()))[:900]}


def save_cv(db: Session, chat: BotChat, *, payload: bytes = b"", filename: str = "",
            text: str = "", fields: dict = None, linkedin: str = "") -> Resume:
    """Резюме из файла или текста → тот же черновик, что даёт быстрая загрузка на сайте.

    Дальше его подхватывает ежечасная задача модерации и переписывает начисто —
    поэтому статусы и moderation_note держим ровно как в /profile.
    """
    user = ensure_account(db, chat)
    row = db.query(Resume).filter_by(user_id=user.id).first()
    if not row:
        row = Resume(user_id=user.id, desired_format="удалёнка", status="draft")
        db.add(row)
        db.flush()
    if fields is not None:
        pass                                   # поля уже разобраны (LinkedIn)
    elif payload:
        os.makedirs(CV_UPLOAD_DIR, exist_ok=True)
        ext = os.path.splitext(filename or "")[1].lower()
        ext = ext if ext in (".pdf", ".docx") else ".pdf"
        stored = os.path.join(CV_UPLOAD_DIR, f"{user.id}-{secrets.token_hex(12)}{ext}")
        with open(stored, "wb") as handle:
            handle.write(payload)
        row.cv_file_name = os.path.basename(filename or f"cv{ext}")[:240]
        row.cv_file_path = stored
        fields = heuristic_cv_fields(stored, user.name or "")
    else:
        fields = _text_cv_fields(text, user.name or "")
    if linkedin:
        row.linkedin_url = linkedin[:500]
    for key, value in (fields or {}).items():
        # заголовок и «о себе» всегда берём из свежего файла, остальное — только
        # в пустые поля: человек мог поправить их руками в кабинете
        if value and (key in ("title", "about") or not (getattr(row, key, None) or "")):
            setattr(row, key, value)
    if chat.username:
        row.contact_telegram = f"@{chat.username}"
    row.consent_at = row.consent_at or datetime.utcnow().isoformat() + "Z"
    row.submitted_at = datetime.utcnow().isoformat() + "Z"
    complete = resume_is_ready(row) and len(row.about or "") >= 80
    row.status = "approved" if complete else "pending"
    row.published = complete
    row.moderation_note = "auto:linkedin" if linkedin else "auto:jobbot"
    track(db, "bot_cv", user.id, "resume", row.id, complete=complete)
    return row


def do_apply(db: Session, chat: BotChat, job_id: int) -> None:
    """Отклик из чата. Дальше включается обычный конвейер: CRM, лид Алине, /claim."""
    lang = chat.lang
    job = db.get(Job, job_id)
    if not job or job.status != "approved":
        send(chat.chat_id, t("gone", lang))
        return
    user = ensure_account(db, chat)
    cv = db.query(Resume).filter_by(user_id=user.id).first()
    if not resume_is_ready(cv):
        chat.state, chat.pending_job = "cv", job_id
        send(chat.chat_id, t("need_cv", lang))
        return
    if db.query(Application).filter_by(job_id=job_id, user_id=user.id).first():
        send(chat.chat_id, t("applied_already", lang))
        return
    day_ago = datetime.utcnow() - timedelta(hours=24)
    recent = (db.query(Application)
              .filter(Application.user_id == user.id, Application.created_at >= day_ago)
              .order_by(Application.created_at.desc()).all())
    if recent and (datetime.utcnow() - recent[0].created_at).total_seconds() < APPLY_MIN_INTERVAL:
        send(chat.chat_id, t("too_fast", lang, n=APPLY_MIN_INTERVAL))
        return
    if len(recent) >= APPLY_DAILY_LIMIT:
        if (user.coins or 0) >= APPLY_EXTRA_COST:
            user.coins = (user.coins or 0) - APPLY_EXTRA_COST
        else:
            send(chat.chat_id, t("limit", lang, n=APPLY_DAILY_LIMIT))
            return
    application = Application(job_id=job_id, user_id=user.id, cover="")
    db.add(application)
    db.flush()
    db.add(ApplicationEvent(application_id=application.id, actor_id=user.id,
                            kind="created", body="Отклик из Telegram-бота"))
    track(db, "application_created", user.id, "job", job_id, via="tgbot")
    from server import crm
    crm.note_application(db, job, user, application)
    chat.state, chat.pending_job = "", None
    keyboard = [[{"text": t("cabinet", lang), "url": login_link(db, user)}]]
    send(chat.chat_id, t("applied", lang, title=esc(job.title), company=esc(job.company_name)),
         keyboard)


# ---------- разбор апдейтов ----------

RU_LANGS = ("ru", "uk", "be", "kk", "hy", "ka", "az", "uz", "ky", "tg", "mo")


def get_chat(db: Session, raw_chat: dict, sender: dict) -> BotChat:
    chat_id = str(raw_chat.get("id"))
    row = db.query(BotChat).filter_by(chat_id=chat_id).first()
    if not row:
        code = (sender.get("language_code") or "").lower()[:2]
        row = BotChat(chat_id=chat_id, lang="ru" if code in RU_LANGS else "en")
        db.add(row)
        db.flush()
    row.username = sender.get("username") or row.username
    row.first_name = sender.get("first_name") or row.first_name
    row.last_seen = datetime.utcnow()
    return row


def menu_keyboard(chat: BotChat) -> list:
    lang = chat.lang
    sub = ("sub_off", "s:0") if chat.sub else ("sub_on", "s:1")
    return [
        [{"text": MENU["cats"][lang], "callback_data": "cats"},
         {"text": MENU["geos"][lang], "callback_data": "geos"}],
        [{"text": MENU["top"][lang], "callback_data": "top"},
         {"text": MENU["fresh"][lang], "callback_data": "fresh"}],
        [{"text": MENU["cv"][lang], "callback_data": "cv"}],
        [{"text": MENU[sub[0]][lang], "callback_data": sub[1]}],
        [{"text": MENU["site"][lang], "url": f"{SITE}/jobs"}],
    ]


def _pairs(buttons: list, lang: str) -> list:
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([{"text": MENU["back"][lang], "callback_data": "menu"}])
    return rows


def cats_keyboard(db: Session, lang: str) -> list:
    """Направления с числом открытых вакансий — пустых кнопок не показываем."""
    rows = [r for r in job_index(db) if geo_ok(r)]
    counts = {}
    for row in rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    buttons = [{"text": f"{label_of(name, lang)} ({counts[name]})",
                "callback_data": f"c:{CATEGORIES.index(name)}"}
               for name in CATEGORIES if counts.get(name)]
    return _pairs(buttons, lang)


def geo_counts(db: Session) -> list:
    counts = {}
    for row in (r for r in job_index(db) if geo_ok(r)):
        country = row["country"]
        if country and country != UNKNOWN_COUNTRY:
            counts[country] = counts.get(country, 0) + 1
    return sorted(counts.items(), key=lambda pair: -pair[1])[:10]


def geos_keyboard(db: Session, lang: str) -> list:
    buttons = [{"text": f"{label_of(name, lang)} ({count})",
                "callback_data": f"g:{name[:40]}"} for name, count in geo_counts(db)]
    return _pairs(buttons, lang)


def show_menu(db: Session, chat: BotChat) -> None:
    send(chat.chat_id, t("menu", chat.lang), menu_keyboard(chat))


def show_welcome(db: Session, chat: BotChat) -> None:
    """Первое касание: баннер, сразу пятёрка вакансий по СНГ и кнопки.

    Меню отдельным сообщением не шлём — человек, пришедший из канала, должен
    увидеть вакансию в первые три секунды, а не список разделов.
    """
    total = len([r for r in job_index(db) if geo_ok(r)])
    caption = t("start", chat.lang, n=f"{total:,}".replace(",", " "))
    if not send_photo(chat.chat_id, BANNER, caption).get("ok"):
        send(chat.chat_id, caption)          # картинка не отдалась — не молчим
    show_jobs(db, chat, "cis", 0, START_CARDS)


def fetch_file(file_id: str) -> bytes:
    info = api("getFile", {"file_id": file_id})
    path = ((info.get("result") or {}).get("file_path") or "")
    if not path:
        return b""
    url = f"https://api.telegram.org/file/bot{TOKEN}/{path}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SpinHire/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read(CV_LIMIT + 1)
    except Exception:                                          # noqa: BLE001
        return b""


def handle_document(db: Session, chat: BotChat, doc: dict) -> None:
    lang = chat.lang
    name = (doc.get("file_name") or "").lower()
    if (doc.get("file_size") or 0) > CV_LIMIT or not name.endswith((".pdf", ".docx", ".doc")):
        send(chat.chat_id, t("cv_bad", lang))
        return
    payload = fetch_file(doc.get("file_id") or "")
    if not payload or len(payload) > CV_LIMIT:
        send(chat.chat_id, t("cv_bad", lang))
        return
    row = save_cv(db, chat, payload=payload, filename=doc.get("file_name") or "cv.pdf")
    after_cv(db, chat, row)


def after_cv(db: Session, chat: BotChat, row: Resume) -> None:
    """Резюме принято: подтверждаем, доводим отклик или показываем совпадения."""
    lang = chat.lang
    if not (row.title or "").strip():
        chat.state = "title"
        send(chat.chat_id, t("ask_title", lang))
        return
    years = ""
    if row.experience_years:
        years = (f", {row.experience_years} лет опыта" if lang == "ru"
                 else f", {row.experience_years} yrs")
    send(chat.chat_id, t("cv_ok", lang, title=esc(row.title), years=years))
    chat.state = ""
    if chat.pending_job:
        job_id, chat.pending_job = chat.pending_job, None
        do_apply(db, chat, job_id)
        return
    show_jobs(db, chat, chat.query or row.title or "fresh", 0)


def handle_linkedin(db: Session, chat: BotChat, url: str) -> None:
    """Ссылка на профиль вместо файла: самый короткий путь к отклику."""
    lang = chat.lang
    send(chat.chat_id, t("li_wait", lang))
    fields = linkedin_fields(url)
    if not fields:
        send(chat.chat_id, t("li_fail", lang))
        track(db, "bot_linkedin_fail", chat.user_id, "bot", None)
        return
    row = save_cv(db, chat, fields=fields, linkedin=url)
    years = ""
    if row.experience_years:
        years = (f", {row.experience_years} лет опыта" if lang == "ru"
                 else f", {row.experience_years} yrs")
    send(chat.chat_id, t("li_ok", lang, title=esc(row.title), years=years))
    track(db, "bot_linkedin", chat.user_id, "resume", row.id)
    chat.state = ""
    if chat.pending_job:
        job_id, chat.pending_job = chat.pending_job, None
        do_apply(db, chat, job_id)
        return
    show_jobs(db, chat, chat.query or row.title or "fresh", 0)


def handle_text(db: Session, chat: BotChat, text: str) -> None:
    lang = chat.lang
    body = text.strip()
    low = body.lower()
    if low.startswith("/"):
        command = low.split()[0].split("@")[0]
        payload = body[len(command):].strip()
        if command == "/start":
            chat.source = (payload or chat.source)[:80]
            show_welcome(db, chat)
            track(db, "bot_start", chat.user_id, "bot", None, source=chat.source)
        elif command in ("/menu", "/help"):
            show_menu(db, chat)
        elif command == "/jobs":
            show_jobs(db, chat, "fresh", 0)
        elif command == "/cv":
            chat.state = "cv"
            send(chat.chat_id, t("need_cv", lang))
        elif command == "/stop":
            chat.sub = 0
            send(chat.chat_id, t("unsubbed", lang), menu_keyboard(chat))
        elif command == "/lang":
            chat.lang = "en" if chat.lang == "ru" else "ru"
            show_menu(db, chat)
        else:
            send(chat.chat_id, t("help", lang), menu_keyboard(chat))
        return
    link = LINKEDIN_RE.search(body)
    if link:
        handle_linkedin(db, chat, link.group(0))
        return
    if chat.state == "title":
        row = db.query(Resume).filter_by(user_id=chat.user_id).first() if chat.user_id else None
        if row:
            row.title = body[:120]
            after_cv(db, chat, row)
            return
    # Длинный текст — это вставленное резюме, а не поисковый запрос: столько
    # в строку поиска не пишут, а к нам так приходит половина кандидатов.
    if chat.state == "cv" or len(body) >= 400:
        row = save_cv(db, chat, text=body)
        after_cv(db, chat, row)
        return
    show_jobs(db, chat, body[:120], 0)


def handle_callback(db: Session, chat: BotChat, data: str) -> None:
    kind, _, value = data.partition(":")
    lang = chat.lang
    if kind == "a" and value.isdigit():
        do_apply(db, chat, int(value))
    elif kind == "m" and value.isdigit():
        show_jobs(db, chat, chat.query, int(value))
    elif data == "menu":
        show_menu(db, chat)
    elif data == "cats":
        send(chat.chat_id, t("pick_cat", lang), cats_keyboard(db, lang))
    elif data == "geos":
        send(chat.chat_id, t("pick_geo", lang), geos_keyboard(db, lang))
    elif kind == "c" and value.isdigit() and int(value) < len(CATEGORIES):
        show_jobs(db, chat, f"cat:{CATEGORIES[int(value)]}", 0)
    elif kind == "g" and value:
        show_jobs(db, chat, f"geo:{value}", 0)
    elif data in ("top", "fresh"):
        show_jobs(db, chat, data, 0)
    elif data == "cv":
        chat.state = "cv"
        send(chat.chat_id, t("need_cv", lang))
    elif data == "s:0":
        chat.sub = 0
        send(chat.chat_id, t("unsubbed", lang), menu_keyboard(chat))
    elif kind == "s":
        chat.sub, chat.sub_query = 1, chat.query or ""
        chat.sub_last = datetime.utcnow().isoformat()
        name = chat.sub_query.partition(":")[2] or chat.sub_query or "все вакансии"
        send(chat.chat_id, t("subbed", lang, q=esc(label_of(name, lang))),
             menu_keyboard(chat))
        track(db, "bot_subscribe", chat.user_id, "bot", None, q=chat.sub_query[:80])


_seen_updates: set = set()


def handle_update(db: Session, update: dict) -> None:
    uid = update.get("update_id")
    if uid in _seen_updates:
        return
    if len(_seen_updates) > 5000:
        _seen_updates.clear()
    _seen_updates.add(uid)
    callback = update.get("callback_query")
    message = update.get("message") or update.get("edited_message")
    if callback:
        raw_chat = (callback.get("message") or {}).get("chat") or {}
        chat = get_chat(db, raw_chat, callback.get("from") or {})
        api("answerCallbackQuery", {"callback_query_id": callback.get("id")})
        handle_callback(db, chat, callback.get("data") or "")
        db.commit()
        return
    if not message:
        return
    chat = get_chat(db, message.get("chat") or {}, message.get("from") or {})
    if message.get("document"):
        handle_document(db, chat, message["document"])
    elif message.get("text"):
        handle_text(db, chat, message["text"])
    else:
        send(chat.chat_id, t("help", chat.lang))
    db.commit()


# ---------- рассылка новых вакансий подписчикам ----------

def push_pending(db: Session, dry: bool = False) -> dict:
    """Новые вакансии по подписке: не чаще раза в сутки и не больше трёх штук.

    Раз в сутки — не жадность, а страховка: за частые рассылки Telegram режет
    боту доставку по жалобам, и мы теряем единственный бесплатный канал возврата.
    """
    now = datetime.utcnow()
    stats = {"chats": 0, "sent": 0, "jobs": 0}
    chats = db.query(BotChat).filter(BotChat.sub == 1).all()
    for chat in chats:
        stats["chats"] += 1
        try:
            since = datetime.fromisoformat(chat.sub_last) if chat.sub_last else chat.created_at
        except ValueError:
            since = chat.created_at or now
        if since and (now - since) < timedelta(hours=20):
            continue
        found, exact = search(db, chat.sub_query)
        # в рассылку уходит только точное совпадение: «похожее» в ленте,
        # которую человек не открывал, читается как спам и стоит отписки
        rows = [r for r in found if r["created"] > since] if exact else []
        if not rows:
            continue
        text, keyboard = jobs_message(db, chat, rows[:CARDS], 0,
                                      t("fresh", chat.lang, q=esc(chat.sub_query or "новое")))
        if dry:
            stats["sent"] += 1
            stats["jobs"] += len(rows[:CARDS])
            continue
        if send(chat.chat_id, text, keyboard).get("ok"):
            chat.sub_last = now.isoformat()
            stats["sent"] += 1
            stats["jobs"] += len(rows[:CARDS])
            track(db, "bot_push", chat.user_id, "bot", None, n=len(rows[:CARDS]))
        else:
            # заблокировал бота — молча снимаем с рассылки, иначе долбимся вечно
            chat.sub = 0
    if not dry:
        db.commit()
    return stats


def _scheduler() -> None:
    started = time.time()
    while True:
        try:
            db = SessionLocal()
            try:
                # индекс пересобираем здесь, а не на первом сообщении после
                # протухшего кэша: собеседник не должен ждать сборку
                _index_cache["at"] = 0.0
                job_index(db)
            finally:
                db.close()
        except Exception as exc:                               # noqa: BLE001
            print(f"[jobbot] индекс не пересобрался: {type(exc).__name__}: {exc}")
        try:
            local = datetime.utcnow() + timedelta(hours=TZ_OFFSET)
            # первый круг пропускаем: таблицы бота создаются на старте приложения
            if time.time() - started > 60 and PUSH_FROM <= local.hour < PUSH_TO:
                db = SessionLocal()
                try:
                    res = push_pending(db)
                    if res.get("sent"):
                        print(f"[jobbot] подписка: чатов {res['sent']}, вакансий {res['jobs']}")
                finally:
                    db.close()
        except Exception as exc:                               # noqa: BLE001
            print(f"[jobbot] ошибка планировщика: {type(exc).__name__}: {exc}")
        time.sleep(INDEX_TTL)


def start_scheduler() -> None:
    if not TOKEN:
        print("[jobbot] молчит: нет SPINHIRE_JOBBOT_TOKEN")
        return
    threading.Thread(target=_scheduler, daemon=True).start()
    print(f"[jobbot] бот подбора включён, рассылка {PUSH_FROM}:00–{PUSH_TO}:00 +{TZ_OFFSET}")


# ---------- маршруты ----------

@router.post("/tg/jobbot/{secret}")
async def webhook(secret: str, request: Request, db: Session = Depends(db_session)):
    """Вебхук Telegram. Всегда отвечаем 200: иначе он будет слать апдейт по кругу."""
    header = request.headers.get("x-telegram-bot-api-secret-token", "")
    if not TOKEN or not secrets.compare_digest(secret, SECRET) \
            or (header and not secrets.compare_digest(header, SECRET)):
        raise HTTPException(404)
    try:
        update = await request.json()
    except Exception:                                          # noqa: BLE001
        return JSONResponse({"ok": True})
    try:
        handle_update(db, update)
    except Exception as exc:                                   # noqa: BLE001
        db.rollback()
        print(f"[jobbot] ошибка обработки: {type(exc).__name__}: {exc}")
    return JSONResponse({"ok": True})


@router.get("/tg/login/{token}")
def tg_login(token: str, request: Request, db: Session = Depends(db_session)):
    """Вход по одноразовой ссылке: у аккаунта из бота нет ни пароля, ни почты."""
    row = db.query(BotLogin).filter_by(token=token).first()
    fresh = row and not row.used and row.created_at \
        and (datetime.utcnow() - row.created_at) < timedelta(hours=24)
    if not fresh:
        return RedirectResponse("/login?e=expired", status_code=303)
    user = db.get(User, row.user_id)
    if not user:
        return RedirectResponse("/login?e=expired", status_code=303)
    row.used = True
    db.commit()
    return set_session(RedirectResponse("/profile", status_code=303), user)


@router.post("/admin/jobbot/setup")
def admin_setup(request: Request, db: Session = Depends(db_session)):
    """Прописать вебхук в Telegram. Дёргать после каждого переезда домена."""
    need_admin(request, db)
    if not TOKEN:
        return JSONResponse({"error": "нет SPINHIRE_JOBBOT_TOKEN"})
    url = f"{SITE}/tg/jobbot/{SECRET}"
    resp = api("setWebhook", {"url": url, "secret_token": SECRET,
                              "allowed_updates": ["message", "callback_query"],
                              "drop_pending_updates": True})
    me = api("getMe", {})
    return JSONResponse({"webhook": resp, "bot": me.get("result", me), "url": url})


@router.get("/admin/jobbot/stats")
def admin_stats(request: Request, db: Session = Depends(db_session)):
    need_admin(request, db)
    chats = db.query(BotChat).count()
    return JSONResponse({
        "chats": chats,
        "subscribed": db.query(BotChat).filter(BotChat.sub == 1).count(),
        "accounts": db.query(BotChat).filter(BotChat.user_id.isnot(None)).count(),
        "jobs_indexed": len(job_index(db)),
        "webhook": (api("getWebhookInfo", {}).get("result") if TOKEN else None),
    })


@router.get("/admin/jobbot/preview")
def admin_preview(request: Request, q: str = "", db: Session = Depends(db_session)):
    """Что бот ответит на запрос — без отправки в Telegram."""
    need_admin(request, db)
    rows, exact = search(db, q)
    return JSONResponse({"query": q, "found": len(rows), "exact": exact,
                         "top": [{"id": r["id"], "title": r["title"], "company": r["company"],
                                  "salary": r["salary"], "usd": r["usd"]} for r in rows[:CARDS]]})


@router.post("/admin/jobbot/push")
def admin_push(request: Request, dry: int = 0, db: Session = Depends(db_session)):
    need_admin(request, db)
    return JSONResponse(push_pending(db, dry=bool(dry)))
