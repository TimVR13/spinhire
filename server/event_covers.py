# -*- coding: utf-8 -*-
"""Обложки событий: фото города + крупный текст (как афиши у TheGamblest).

На странице обложка собирается из HTML/CSS (фото города под градиентом, поверх — даты,
название, город), а для соцсетей и мессенджеров нужна готовая картинка: og:image
1200×630 печём здесь через Pillow в img/events/og/<slug>.jpg. Шрифты сайта лежат в
server/assets/fonts (вариативные Bricolage Grotesque и Golos Text).

Фото городов: img/events/city/<город>.jpg — фирменные генерирует
scripts/event_city_photos.py (Vertex), запасные докачивает краулер из Википедии.
"""
from __future__ import annotations

import os
import re
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(ROOT, "server", "assets", "fonts")
OG_DIR = os.path.join(ROOT, "img", "events", "og")
W, H = 1200, 630
ACID = (60, 240, 194)
PINK = (255, 95, 193)
INK = (244, 244, 246)
INK_DIM = (200, 204, 210)

MONTHS_RU = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
MONTHS_RU_FULL = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август",
                  "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS_EN_FULL = ["January", "February", "March", "April", "May", "June", "July", "August",
                  "September", "October", "November", "December"]


def _d(value: str) -> date | None:
    try:
        return date.fromisoformat((value or "")[:10])
    except ValueError:
        return None


def format_dates(date_from: str, date_to: str = "", lang: str = "ru", with_year: bool = True) -> str:
    """«29 сен – 1 окт 2026», «24–25 сен 2026», «15 окт 2026»; en: «29 Sep – 1 Oct 2026»."""
    a, b = _d(date_from), _d(date_to) or _d(date_from)
    if not a:
        return date_from or ""
    months = MONTHS_EN if lang == "en" else MONTHS_RU
    year = f" {a.year}" if with_year else ""
    if not b or b <= a:
        return f"{a.day} {months[a.month - 1]}{year}"
    if a.month == b.month and a.year == b.year:
        return f"{a.day}–{b.day} {months[a.month - 1]}{year}"
    if a.year == b.year:
        return f"{a.day} {months[a.month - 1]} – {b.day} {months[b.month - 1]}{year}"
    return f"{a.day} {months[a.month - 1]} {a.year} – {b.day} {months[b.month - 1]} {b.year}"


def month_title(ym: str, lang: str = "ru") -> str:
    """'2026-09' → 'Сентябрь' / 'September'."""
    try:
        m = int(ym[5:7])
    except ValueError:
        return ym
    return (MONTHS_EN_FULL if lang == "en" else MONTHS_RU_FULL)[m - 1]


def day_title(value: str, lang: str = "ru") -> str:
    """'2026-09-28' → '28 сентября' / '28 September' — заголовок дня в расписании."""
    d = _d(value)
    if not d:
        return value or ""
    if lang == "en":
        return f"{d.day} {MONTHS_EN_FULL[d.month - 1]}"
    genitive = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
                "сентября", "октября", "ноября", "декабря"]
    return f"{d.day} {genitive[d.month - 1]}"


# ---------- рисование ----------

def _font(name: str, size: int, weight: int):
    from PIL import ImageFont
    font = ImageFont.truetype(os.path.join(FONT_DIR, name), size)
    try:
        axes = font.get_variation_axes()
        values = []
        for axis in axes:
            label = axis["name"].decode() if isinstance(axis["name"], bytes) else str(axis["name"])
            if "weight" in label.lower():
                values.append(max(axis["minimum"], min(axis["maximum"], weight)))
            elif "optical" in label.lower():
                values.append(min(axis["maximum"], max(axis["minimum"], size)))
            else:
                values.append(axis["default"])
        font.set_variation_by_axes(values)
    except Exception:  # noqa: BLE001 — статический шрифт или FreeType без вариаций
        pass
    return font


def _wrap(draw, text: str, font, max_width: int, max_lines: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        probe = f"{cur} {word}".strip()
        if draw.textlength(probe, font=font) <= max_width or not cur:
            cur = probe
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while draw.textlength(last + "…", font=font) > max_width and " " in last:
            last = last.rsplit(" ", 1)[0]
        lines[-1] = last + "…"
    return lines


def _background(photo_path: str):
    from PIL import Image, ImageFilter
    if photo_path and os.path.exists(photo_path):
        im = Image.open(photo_path).convert("RGB")
        scale = max(W / im.width, H / im.height)
        im = im.resize((max(W, round(im.width * scale)), max(H, round(im.height * scale))), Image.LANCZOS)
        left = (im.width - W) // 2
        top = (im.height - H) // 2
        im = im.crop((left, top, left + W, top + H))
        return im
    # без фото — фирменный тёмный градиент с неоновыми пятнами
    im = Image.new("RGB", (W, H), (14, 20, 18))
    glow = Image.new("RGB", (W, H), (14, 20, 18))
    from PIL import ImageDraw
    g = ImageDraw.Draw(glow)
    g.ellipse((W - 520, -260, W + 160, 300), fill=(26, 70, 58))
    g.ellipse((-260, H - 240, 320, H + 260), fill=(70, 28, 56))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    return Image.blend(im, glow, 0.9)


def make_og(out_path: str, *, title: str, dates: str, place: str, venue: str = "",
            photo_path: str = "", kicker: str = "iGaming · событие") -> str:
    """Собрать og-картинку и вернуть путь. Тихо возвращает '' без Pillow."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return ""
    im = _background(photo_path)
    # затемнение: снизу плотнее, чтобы текст читался на любом фото
    shade = Image.new("L", (1, H))
    for y in range(H):
        t = y / (H - 1)
        shade.putpixel((0, y), int(55 + 180 * (t ** 1.35)))
    shade = shade.resize((W, H))
    dark = Image.new("RGB", (W, H), (8, 12, 11))
    im = Image.composite(dark, im, shade)
    draw = ImageDraw.Draw(im)
    # неоновая кромка сверху
    for x in range(W):
        t = x / (W - 1)
        col = tuple(round(ACID[i] * (1 - t) + PINK[i] * t) for i in range(3))
        draw.line([(x, 0), (x, 9)], fill=col)
    # бренд
    brand = _font("BricolageGrotesque.ttf", 40, 800)
    draw.text((64, 44), "spin", font=brand, fill=INK)
    draw.text((64 + draw.textlength("spin", font=brand), 44), "hire", font=brand, fill=ACID)
    kick_font = _font("GolosText.ttf", 22, 700)
    kick = kicker.upper()
    draw.text((W - 64 - draw.textlength(kick, font=kick_font), 52), kick, font=kick_font, fill=INK_DIM)
    # текст снизу
    y = H - 64
    if venue:
        venue_font = _font("GolosText.ttf", 24, 600)
        line = _wrap(draw, venue, venue_font, W - 128, 1)[0]
        y -= 30
        draw.text((64, y), line, font=venue_font, fill=INK_DIM)
        y -= 12
    place_font = _font("GolosText.ttf", 28, 700)
    y -= 34
    draw.text((64, y), place.upper(), font=place_font, fill=INK)
    y -= 18
    size = 74
    title_font = _font("BricolageGrotesque.ttf", size, 800)
    lines = _wrap(draw, title, title_font, W - 128, 2)
    while len(lines) > 1 and size > 52 and any(draw.textlength(l, font=title_font) > W - 128 for l in lines):
        size -= 4
        title_font = _font("BricolageGrotesque.ttf", size, 800)
        lines = _wrap(draw, title, title_font, W - 128, 2)
    line_h = round(size * 1.02)
    y -= line_h * len(lines)
    for i, line in enumerate(lines):
        draw.text((64, y + i * line_h), line, font=title_font, fill=INK)
    dates_font = _font("GolosText.ttf", 30, 700)
    y -= 46
    draw.text((64, y), dates.upper(), font=dates_font, fill=ACID)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    im.save(out_path, "JPEG", quality=86, optimize=True, progressive=True)
    return out_path


def og_path(slug: str) -> str:
    return os.path.join(OG_DIR, f"{slug}.jpg")


def og_url(slug: str) -> str:
    return f"/img/events/og/{slug}.jpg" if slug and os.path.exists(og_path(slug)) else ""


def make_og_for_event(ev) -> str:
    """OG-карточка для строки events. Возвращает URL картинки или ''."""
    if not getattr(ev, "slug", ""):
        return ""
    photo = ""
    if (ev.image or "").startswith("/img/"):
        photo = os.path.join(ROOT, ev.image.lstrip("/"))
    place = re.sub(r"^[^\w]+", "", ev.city or "").strip()  # без флага-эмодзи: в Pillow он не отрисуется
    result = make_og(og_path(ev.slug), title=ev.title, dates=format_dates(ev.date_from, ev.date_to, "ru"),
                     place=place, venue=ev.venue or "", photo_path=photo,
                     kicker=(ev.category or "событие") + " · iGaming")
    return f"/img/events/og/{ev.slug}.jpg" if result else ""
