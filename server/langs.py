"""Коды языков и сегменты адреса.

Код языка (ISO 639-1) и сегмент в адресе — не одно и то же. Украинская версия живёт под
/ua/: так адрес читает украинец (ua — код страны), а /uk/ смотрится как Британия — владелец
15.09.2026 потребовал /ua. Внутри код языка остаётся «uk»: словари server/i18n/uk.*,
hreflang, og:locale и мета sh-lang по стандарту принимают только его. Старые адреса /uk/…
отдают 301 на /ua/… (server/app.py, language_layer). Модуль без зависимостей, чтобы его
брали и app.py, и краулер, и claim — без круговых импортов.
"""

LANG_SLUGS = {"uk": "ua"}
SLUG_LANGS = {slug: code for code, slug in LANG_SLUGS.items()}


def lang_slug(code: str) -> str:
    """Код языка → сегмент адреса: uk → ua, остальные совпадают."""
    return LANG_SLUGS.get(code, code)


def slug_lang(slug: str) -> str:
    """Сегмент адреса → код языка: ua → uk, остальные совпадают."""
    return SLUG_LANGS.get(slug, slug)
