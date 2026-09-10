# -*- coding: utf-8 -*-
"""Картинки к постам в Telegram: фирменная карточка вместо голого текста.

Каждый пост канала уходит как фото с подписью, поэтому картинка должна нести
смысл, а не быть обоями: в дайджесте — три верхние вакансии с вилками, в
«вакансии дня» — сама вакансия крупно. Фон, акцентный цвет и подпись-чип
меняются по дню, чтобы лента не выглядела одинаковой.

Рендер — Pillow, шрифты берём системные (Lato на сервере, Arial на маке);
если Pillow или шрифтов нет, функции возвращают None и пост уходит текстом.
"""
import os
import re
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, "img")

W, H = 1280, 720
BG = (9, 13, 11)
GOLD = (240, 197, 106)
GREEN = (122, 232, 140)
PINK = (255, 77, 157)
CYAN = (63, 216, 232)
WHITE = (240, 246, 242)
MUTE = (176, 188, 183)
SHADOW = (0, 0, 0)

# hero-neon.png в ротацию не берём: это коллаж со швом по вертикали,
# под затемнением он виден полосой.
BACKGROUNDS = ("asset-chips.jpg", "asset-roulette.jpg", "asset-cards.jpg",
               "asset-dice.jpg", "asset-slot-cabinet.jpg")
ACCENTS = (GREEN, GOLD, CYAN, PINK)

# Шрифт нужен с кириллицей: Lato есть на дроплете, Arial — на маке разработчика.
FONT_DIRS = [os.environ.get("SPINHIRE_FONT_DIR", ""),
             "/usr/share/fonts/truetype/lato",
             "/usr/share/fonts/truetype/dejavu",
             "/System/Library/Fonts/Supplemental"]
FONT_FILES = {
    "black": ("Lato-Black.ttf", "DejaVuSans-Bold.ttf", "Arial Black.ttf"),
    "bold": ("Lato-Bold.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"),
    "regular": ("Lato-Regular.ttf", "DejaVuSans.ttf", "Arial.ttf"),
}
_font_cache = {}

TEXT = {
    "ru": {"digest": "ТОП ВАКАНСИЙ ДНЯ", "hot": "ВАКАНСИЯ ДНЯ",
           "tagline": "Работа в iGaming", "open": "на борде",
           "more": "и ещё {n} в подборке"},
    "en": {"digest": "TOP PAYING TODAY", "hot": "HOT JOB",
           "tagline": "iGaming Jobs", "open": "jobs on the board",
           "more": "and {n} more in the digest"},
}


def _font(size: int, weight: str = "black"):
    key = (size, weight)
    if key in _font_cache:
        return _font_cache[key]
    from PIL import ImageFont
    for folder in FONT_DIRS:
        if not folder:
            continue
        for name in FONT_FILES[weight]:
            path = os.path.join(folder, name)
            if os.path.exists(path):
                _font_cache[key] = ImageFont.truetype(path, size)
                return _font_cache[key]
    raise RuntimeError("нет шрифта с кириллицей для карточек")


def _clean(text: str) -> str:
    """Из поста в картинку: без HTML-разметки и служебных хвостов."""
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s{2,}", " ", text.replace("&amp;", "&")).strip()


def _canvas(accent, seed: int):
    from PIL import Image, ImageChops, ImageDraw, ImageOps
    name = BACKGROUNDS[seed % len(BACKGROUNDS)]
    path = os.path.join(IMG, name)
    if os.path.exists(path):
        base = ImageOps.fit(Image.open(path).convert("RGB"), (W, H), Image.LANCZOS)
    else:
        base = Image.new("RGB", (W, H), BG)
    # Затемняем маской, а не рисованием по RGBA: ImageDraw в режиме RGBA
    # заменяет пиксель вместо смешивания и оставляет шов на стыке градиентов.
    columns, rows = Image.new("L", (W, H)), Image.new("L", (W, H))
    paint = ImageDraw.Draw(columns)
    for x in range(W):                      # слева плотнее — там текст
        share = max(0.0, 1 - x / (W * 0.72))
        paint.line([(x, 0), (x, H)], fill=int(215 * share ** 1.2))
    paint = ImageDraw.Draw(rows)
    for y in range(H):                      # книзу темнее — там подвал
        paint.line([(0, y), (W, y)], fill=int(70 + 80 * (y / H) ** 1.6))
    mask = ImageChops.lighter(columns, rows)
    ImageDraw.Draw(mask).rectangle([0, 0, W, 104], fill=228)
    img = Image.composite(Image.new("RGB", (W, H), (5, 8, 7)), base, mask)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 8], fill=accent)
    return img, draw


def _shadowed(draw, xy, text, font, fill):
    x, y = xy
    draw.text((x + 2, y + 3), text, font=font, fill=SHADOW)
    draw.text((x, y), text, font=font, fill=fill)


def _fit(draw, text: str, x: int, y: int, width: int, size: int, fill,
         weight: str = "black", floor: int = 20) -> int:
    """Одна строка, ужимаем кегль пока не влезет; совсем длинное — режем."""
    font = _font(size, weight)
    while draw.textlength(text, font=font) > width and size > floor:
        size -= 2
        font = _font(size, weight)
    while text and draw.textlength(text, font=font) > width:
        text = text[:-2] + "…"
    _shadowed(draw, (x, y), text, font, fill)
    return size


def _wrap_lines(draw, text: str, width: int, size: int, weight: str = "black",
                lines: int = 2) -> list:
    font = _font(size, weight)
    row, out = "", []
    for word in text.split():
        probe = f"{row} {word}".strip()
        if draw.textlength(probe, font=font) > width and row:
            out.append(row)
            row = word
            if len(out) == lines:
                break
        else:
            row = probe
    if len(out) < lines and row:
        out.append(row)
    if len(out) == lines and row and row not in out:
        out[-1] += "…"
    return out[:lines]


def _wrap(draw, rows, x: int, y: int, size: int, fill, weight: str = "black",
          gap: float = 1.16) -> int:
    font = _font(size, weight)
    for i, row in enumerate(rows):
        _shadowed(draw, (x, y + int(i * size * gap)), row, font, fill)
    return y + int(len(rows) * size * gap)


def _header(img, draw, lang: str, accent, chip: str):
    from PIL import Image, ImageDraw, ImageOps
    t = TEXT.get(lang, TEXT["en"])
    draw.ellipse([56, 40, 78, 62], fill=accent)
    _shadowed(draw, (92, 28), "SpinHire", _font(44), WHITE)
    tagline = _font(24, "regular")
    draw.text((W - 56 - draw.textlength(t["tagline"], font=tagline), 42),
              t["tagline"], font=tagline, fill=MUTE)
    draw.line([(56, 104), (W - 56, 104)], fill=(70, 84, 78), width=2)
    chip_font = _font(24, "black")
    width = draw.textlength(chip, font=chip_font) + 40
    draw.rounded_rectangle([56, 128, 56 + width, 174], 12, fill=accent)
    draw.text((76, 138), chip, font=chip_font, fill=BG)
    logo = os.path.join(IMG, "logo-final.png")
    if os.path.exists(logo):
        size = 92
        mark = ImageOps.fit(Image.open(logo).convert("RGB"), (size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
        img.paste(mark, (W - size - 56, H - size - 56), mask)


def _footer(draw, lang: str, accent, note: str = ""):
    _shadowed(draw, (56, H - 74), "spinhire.io", _font(30, "black"), accent)
    if note:
        font = _font(24, "regular")
        draw.text((56, H - 112), note, font=font, fill=MUTE)


def _png(img) -> bytes:
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _jobs_count(total: int, lang: str) -> str:
    """«6 064 вакансии на борде» — с правильным окончанием."""
    number = f"{total:,}".replace(",", "\u2009")
    if lang != "ru":
        return f"{number} {TEXT['en']['open']}"
    tail, hundred = total % 10, total % 100
    word = "вакансий"
    if tail == 1 and hundred != 11:
        word = "вакансия"
    elif tail in (2, 3, 4) and hundred not in (12, 13, 14):
        word = "вакансии"
    return f"{number} {word} на борде"


def _seed(lang: str) -> int:
    """Фон меняется каждый день и различается у двух каналов."""
    return date.today().toordinal() + (0 if lang == "ru" else 3)


def digest_card(lang: str, rows, total_open: int = 0, extra: int = 0):
    """rows — [(заголовок, вилка, «Компания · Гео»)], первые три попадут на картинку."""
    try:
        t = TEXT.get(lang, TEXT["en"])
        seed = _seed(lang)
        accent = ACCENTS[seed % len(ACCENTS)]
        img, draw = _canvas(accent, seed)
        _header(img, draw, lang, accent, t["digest"])
        y = 198
        for i, (title, salary, place) in enumerate(rows[:3]):
            colour = (GOLD, GREEN, CYAN)[i % 3]
            draw.rounded_rectangle([56, y + 4, 62, y + 112], 3, fill=colour)
            _fit(draw, _clean(title), 84, y, 800, 36, WHITE, floor=30)
            _fit(draw, _clean(salary), 84, y + 46, 600, 40, colour)
            _fit(draw, _clean(place), 84, y + 94, 800, 22, MUTE, "regular")
            y += 136
        note = t["more"].format(n=extra) if extra > 0 else ""
        if total_open:
            note = f"{note} · {_jobs_count(total_open, lang)}" if note else \
                _jobs_count(total_open, lang)
        _footer(draw, lang, accent, note)
        return _png(img)
    except Exception as exc:                                    # noqa: BLE001
        print(f"[tgcards] дайджест без картинки: {type(exc).__name__}: {exc}")
        return None


def hot_card(lang: str, title: str, salary: str, place: str, company: str = ""):
    try:
        t = TEXT.get(lang, TEXT["en"])
        seed = _seed(lang) + 1
        accent = PINK if seed % 2 else GOLD
        img, draw = _canvas(accent, seed)
        _header(img, draw, lang, accent, t["hot"])
        rows = _wrap_lines(draw, _clean(title), 900, 54, lines=2)
        # короткий заголовок не должен висеть в верхней трети — центрируем блок
        block = len(rows) * int(54 * 1.16) + 166
        top = 200 + max(0, (370 - block) // 2)
        bottom = _wrap(draw, rows, 56, top, 54, WHITE)
        line = " · ".join(x for x in (_clean(company), _clean(place)) if x)
        if line:
            _fit(draw, line, 56, bottom + 22, 900, 28, GREEN, "regular")
        _fit(draw, _clean(salary), 56, bottom + 76, 820, 62, accent)
        _footer(draw, lang, accent)
        return _png(img)
    except Exception as exc:                                    # noqa: BLE001
        print(f"[tgcards] горячая вакансия без картинки: {type(exc).__name__}: {exc}")
        return None
