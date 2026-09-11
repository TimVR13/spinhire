"""Разнообразие роликов серии: тема оформления, голос диктора и формулировки — по направлению и slug.

Серия «профессии» — это 35 роликов одной структуры. Без вариаций зритель видит один и тот же
ролик 35 раз, а YouTube — шаблонный канал. Поэтому каждому ролику детерминированно (от slug,
чтобы пересборка давала тот же результат) достаётся своя тема, свой диктор и свои формулировки.
"""

# Палитра сайта (css/style.css, oklch → hex): изумруд, магента, фиолет, циан, золото.
ACCENT = {
    "emerald": ("#12e08e", "рост, деньги"),
    "pink":    ("#ff3fa4", "громкий акцент"),
    "violet":  ("#b27dff", "продукт, разработка"),
    "cyan":    ("#00dff2", "аналитика, данные"),
    "gold":    ("#d4a94a", "статус, топ-менеджмент"),
}

# Тема направления: акцент + подсветка фона + рисунок подложки + фотофон первого кадра.
# Так все ролики одного направления узнаются как подсерия, а соседние в ленте не сливаются.
# Фирменные фишки (chip-1 зелёная, chip-2 розовая, chip-3 голубая) подобраны в цвет акцента.
THEMES = {
    "Операции казино":          {"accent": "emerald", "second": "gold",    "pattern": "rays",  "hero": "chip-1.png"},
    "Беттинг и трейдинг":       {"accent": "cyan",    "second": "emerald", "pattern": "grid",  "hero": "chip-3.png"},
    "Разработка игр":           {"accent": "violet",  "second": "cyan",    "pattern": "orbs",  "hero": "hero-v2.jpg"},
    "Аффилейты и медиабаинг":   {"accent": "pink",    "second": "violet",  "pattern": "rays",  "hero": "chip-2.png"},
    "Комплаенс и AML":          {"accent": "cyan",    "second": "gold",    "pattern": "grid",  "hero": "hero-v.jpg"},
    "Платежи и антифрод":       {"accent": "emerald", "second": "cyan",    "pattern": "orbs",  "hero": "hero-v2.jpg"},
    "Саппорт (языки)":          {"accent": "pink",    "second": "emerald", "pattern": "orbs",  "hero": "chip-2.png"},
    "Маркетинг и CRM":          {"accent": "pink",    "second": "gold",    "pattern": "grid",  "hero": "hero-v.jpg"},
    "Данные и BI":              {"accent": "cyan",    "second": "violet",  "pattern": "rays",  "hero": "chip-3.png"},
    "Топ-менеджмент":           {"accent": "gold",    "second": "emerald", "pattern": "orbs",  "hero": "hero-v.jpg"},
}
DEFAULT_THEME = {"accent": "emerald", "second": "gold", "pattern": "rays", "hero": "hero-v2.jpg"}

# Chirp3-HD, доступные и для ru-RU, и для en-US (латиницу читает тот же голос, иначе диктор «меняется»
# посреди фразы). Charon — голос канала, остальные для разнообразия серии.
VOICES = ["Chirp3-HD-Charon", "Chirp3-HD-Orus", "Chirp3-HD-Kore", "Chirp3-HD-Aoede", "Chirp3-HD-Puck", "Chirp3-HD-Leda"]

# Формулировки: один и тот же смысл разными словами, чтобы серия не читалась как шаблон.
HOOK_KICKERS = ["Профессия за минуту", "Разбор профессии", "Кто это вообще", "Работа в iGaming"]
HOOK_LINES = [
    "{t} в iGaming за минуту: что делает, сколько получает и как войти.",
    "Разбираем профессию: {t} в iGaming. Задачи, деньги и точка входа.",
    "{t}: чем занимается в гемблинге, сколько платят и с чего начать.",
    "Кто такой {t} в iGaming и почему на эту роль сейчас ищут людей.",
]
DO_TITLES = ["Что делает", "Чем занимается", "Задачи роли", "Что в работе"]
DO_SAYS = ["Что делает. ", "Чем занимается. ", "Задачи роли. ", "В работе. "]
SKILL_TITLES = ["Что нужно уметь", "Навыки", "Что требуют", "Без чего не возьмут"]
SKILL_SAYS = ["Что нужно уметь. ", "Навыки. ", "Что требуют. ", "Без чего не возьмут. "]
ENTRY_KICKERS = ["Как войти", "С чего начать", "Точка входа", "Путь в профессию"]
CTA_LINES = ["Полный разбор профессии", "Разбор роли и вакансии", "Вакансии по этой роли", "Полный гайд по профессии"]
TITLE_TEMPLATES = [
    "Кто такой {t} в iGaming: обязанности, зарплата, как стать | профессии гемблинга",
    "{T} в iGaming: чем занимается, сколько зарабатывает и как войти в профессию",
    "Профессия {t} в гемблинге: задачи, зарплаты по грейдам и старт карьеры",
]


def seed(slug: str) -> int:
    """Стабильное число от slug: пересборка ролика не меняет его оформление."""
    return sum((i + 1) * ord(c) for i, c in enumerate(slug))


def pick(options: list, slug: str, shift: int = 0):
    return options[(seed(slug) + shift) % len(options)]


def theme_for(role: dict) -> dict:
    """Тема ролика: цвета в hex (Remotion не умеет наши CSS-переменные), рисунок фона, фотофон."""
    t = THEMES.get(role.get("family"), DEFAULT_THEME)
    return {"accent": ACCENT[t["accent"]][0], "second": ACCENT[t["second"]][0],
            "pattern": t["pattern"], "hero": t["hero"], "name": t["accent"]}


def voice_for(slug: str) -> str:
    return pick(VOICES, slug)
