"""Извлечение зарплатной вилки из текста вакансии.

Точность важнее охвата. В описаниях полно сумм, которые зарплатой не являются
(«€300 yearly wellness allowance», бюджет на обучение, реферальная премия), и
одна такая ошибка хуже, чем сто вакансий без вилки: кандидат видит €300 в
карточке, а Google получает заведомо ложную разметку JobPosting.

Поэтому сумма принимается, только если рядом стоит слово про оплату труда и
поблизости нет слова про льготу или бонус.
"""
import re

CURRENCIES = {
    "€": "EUR", "eur": "EUR", "euro": "EUR",
    "$": "USD", "usd": "USD",
    "£": "GBP", "gbp": "GBP",
    "zł": "PLN", "pln": "PLN",
    "gel": "GEL", "₾": "GEL",
    "usdt": "USDT",
    "грн": "UAH", "uah": "UAH",
}

# Слово про оплату труда — обязано быть рядом
PAY_WORDS = re.compile(
    r"salary|salaries|remuneration|base pay|pay range|compensation range|"
    r"annualized range|total cash|зарплат|оклад|вилка|ставка|доход",
    re.I)

# Слово про льготу — если оно ближе к сумме, чем слово про оплату, сумму не берём
PERK_WORDS = re.compile(
    r"allowance|perk|benefit|referral|bonus scheme|budget|stipend|voucher|"
    r"discount|insurance|wellness|training|education|learning|relocation package|"
    r"sign[- ]on|gift|equipment|компенсац\w* (?:обучен|спорт|питан)|бюджет|"
    r"страхов|абонемент|подарок",
    re.I)

# сумма с валютой: «€1 200», «85,000 USD», «PLN 12000»
_NUM = r"\d[\d   ,.]{2,}\d|\d{3,}|\d{1,3}[.,]\d{2}"
_CUR = r"€|\$|£|zł|₾|EUR|USD|GBP|PLN|GEL|USDT|UAH|грн"
AMOUNT = re.compile(rf"(?:(?P<cur1>{_CUR})\s?(?P<num1>{_NUM}))|"
                    rf"(?:(?P<num2>{_NUM})\s?(?P<cur2>{_CUR}))", re.I)

RANGE_SEP = re.compile(r"^\s*(?:-|–|—|to|до|and|…|\.\.)\s*$", re.I)

YEARLY = re.compile(r"annual|annualiz|per year|/\s?year|yearly|p\.a\.|в год|годов", re.I)
MONTHLY = re.compile(r"per month|/\s?month|monthly|в месяц|ежемесяч|мес\.", re.I)
HOURLY = re.compile(r"per hour|/\s?h(?:our|r)\b|hourly|в час|/\s?час", re.I)


def _to_number(raw):
    """«85,000» → 85000, «18.25» → 18.25, «1 200» → 1200.

    Точка или запятая с двумя знаками после неё — десятичная дробь (так пишут
    почасовые ставки); во всех остальных случаях они разделяют тысячи.
    """
    text = raw.strip()
    decimal = re.search(r"[.,](\d{2})$", text)
    if decimal and len(re.sub(r"[^\d]", "", text[:decimal.start()])) <= 3:
        whole = re.sub(r"[^\d]", "", text[:decimal.start()])
        return float(f"{whole or 0}.{decimal.group(1)}")
    digits = re.sub(r"[^\d]", "", text)
    return float(digits) if digits else 0.0


def _plausible_any(value, period):
    """Проверка до того, как период определён: годится любое толкование."""
    if period:
        return _plausible(value, period)
    return any(_plausible(value, p) for p in ("HOUR", "MONTH", "YEAR"))


def _plausible(value, period):
    """Отсекаем номера телефонов, годы и суммы льгот."""
    if period == "YEAR":
        return 8_000 <= value <= 2_000_000
    if period == "HOUR":
        return 3 <= value <= 500
    return 400 <= value <= 100_000


def _result(low, high, currency, stated):
    """Собираем вилку и доопределяем период, если в тексте его не назвали.

    «€3 000» в объявлении почти всегда месяц, «$120,000» — год. Между 10 000 и
    20 000 однозначного ответа нет, и мы предпочитаем отдать вакансию без вилки,
    чем показать кандидату годовой оклад как месячный.
    """
    period = stated
    if period is None:
        if high < 10_000:
            period = "MONTH"
        elif low >= 20_000:
            period = "YEAR"
        else:
            return None
    if not (_plausible(low, period) and _plausible(high, period)):
        return None
    return {"min": low, "max": high, "currency": currency, "period": period}


def parse_salary(text, window=140):
    """Вилка из текста вакансии либо None.

    Возвращает {'min', 'max', 'currency', 'period'} — period это 'MONTH' или 'YEAR'.
    """
    if not text:
        return None
    text = " ".join(text.split())
    matches = list(AMOUNT.finditer(text))
    for i, m in enumerate(matches):
        cur_raw = (m.group("cur1") or m.group("cur2") or "").lower()
        currency = CURRENCIES.get(cur_raw)
        if not currency:
            continue
        left = text[max(0, m.start() - window):m.start()]
        right = text[m.end():m.end() + 60]
        pay = PAY_WORDS.search(left) or PAY_WORDS.search(right)
        if not pay:
            continue
        # льгота ближе к сумме, чем слово про оплату → это не зарплата
        perk = PERK_WORDS.search(left)
        if perk and perk.start() > (PAY_WORDS.search(left).start() if PAY_WORDS.search(left) else -1):
            continue
        if PERK_WORDS.search(right):
            continue

        context = left + " " + text[m.start():m.end() + 60]
        stated = ("HOUR" if HOURLY.search(context) else
                  "YEAR" if YEARLY.search(context) else
                  "MONTH" if MONTHLY.search(context) else None)
        # Пока период неизвестен, сумму проверяем мягко: годится любая, которая
        # правдоподобна хоть как часовая, хоть как месячная, хоть как годовая.
        # Окончательное решение принимает _result, когда известна вся вилка.
        period = stated
        low = _to_number(m.group("num1") or m.group("num2"))
        if not _plausible_any(low, period):
            continue

        high = low
        # «от 1200 до 1800 EUR»: валюта стоит только у верхней границы,
        # тогда нижняя лежит слева от найденной суммы
        head = re.search(r"(\d[\d   ,.]*\d)\s*(?:-|–|—|to|до)\s*$", left)
        if head:
            candidate = _to_number(head.group(1))
            if _plausible_any(candidate, period) and candidate <= low:
                return _result(candidate, low, currency, stated)

        # вторая сумма вилки: идёт следом и отделена только тире или «to»
        if i + 1 < len(matches):
            nxt = matches[i + 1]
            between = text[m.end():nxt.start()]
            if RANGE_SEP.match(between):
                nxt_cur = CURRENCIES.get((nxt.group("cur1") or nxt.group("cur2") or "").lower())
                candidate = _to_number(nxt.group("num1") or nxt.group("num2"))
                if (nxt_cur in (None, currency)) and _plausible_any(candidate, period) and candidate >= low:
                    high = candidate
        # «от 1200 до 1800» без валюты у второго числа
        if high == low:
            tail = re.match(r"\s*(?:-|–|—|to|до)\s*(\d[\d   ,.]*\d)",
                            text[m.end():m.end() + 24])
            if tail:
                candidate = _to_number(tail.group(1))
                if _plausible_any(candidate, period) and candidate >= low:
                    high = candidate
        result = _result(low, high, currency, stated)
        if result:
            return result
    return None


SYMBOL = {"EUR": "€", "USD": "$", "GBP": "£", "PLN": "zł", "GEL": "₾",
          "USDT": "USDT ", "UAH": "₴"}


def format_salary(parsed):
    """Вилка строкой в том же виде, в каком её хранит поле Job.salary."""
    if not parsed:
        return ""
    sign = SYMBOL.get(parsed["currency"], parsed["currency"] + " ")

    def money(value):
        if value == int(value):
            return f"{int(value):,}".replace(",", " ")
        return f"{value:.2f}".replace(".", ",")

    body = money(parsed["min"])
    if parsed["max"] > parsed["min"]:
        body += "–" + money(parsed["max"])
    suffix = {"YEAR": " в год", "HOUR": " в час"}.get(parsed["period"], "")
    return f"{sign}{body}{suffix}"
