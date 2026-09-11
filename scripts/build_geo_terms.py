#!/usr/bin/env python3
"""Собрать server/i18n/terms.auto.json — страны и языки на всех языках сайта.

Имена берём из CLDR через babel, поэтому они настоящие, а не машинный перевод:
«Кюрасао» на греческом это Κουρασάο, а не Kyurasao. babel нужен только здесь,
на сервере его нет — в репозиторий уезжает готовый JSON.

    pip install babel && python3 scripts/build_geo_terms.py

Английские имена уже существующих стран не трогаем: из них собран слаг
кластерных страниц (/jobs/usa), и смена имени сломала бы адреса и sitemap.
"""
import json
import os
import sys

from babel import Locale

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ["en", "de", "pl", "fr", "es", "pt", "it", "el", "ro", "bg", "uk"]

# Канонические русские имена — те, что пишет краулер и возвращает country_of().
ISO = {
    "Мальта": "MT", "Кипр": "CY", "Польша": "PL", "Украина": "UA", "Великобритания": "GB",
    "Гибралтар": "GI", "Румыния": "RO", "Болгария": "BG", "Греция": "GR", "Испания": "ES",
    "Португалия": "PT", "Германия": "DE", "Бразилия": "BR", "США": "US", "Канада": "CA",
    "Грузия": "GE", "Армения": "AM", "Сербия": "RS", "Филиппины": "PH", "Индия": "IN",
    "ЮАР": "ZA", "ОАЭ": "AE", "Швеция": "SE", "Латвия": "LV", "Эстония": "EE", "Литва": "LT",
    "Нидерланды": "NL", "Ирландия": "IE", "Италия": "IT", "Мексика": "MX", "Колумбия": "CO",
    "Перу": "PE", "Чили": "CL", "Аргентина": "AR", "Турция": "TR", "Австралия": "AU",
    "Китай": "CN", "Япония": "JP", "Казахстан": "KZ",
    # были только у краулера — на сайте оставались русскими
    "Австрия": "AT", "Бельгия": "BE", "Босния": "BA", "Венгрия": "HU", "Вьетнам": "VN",
    "Гана": "GH", "Гонконг": "HK", "Дания": "DK", "Египет": "EG", "Израиль": "IL",
    "Индонезия": "ID", "Кения": "KE", "Коста-Рика": "CR", "Кюрасао": "CW", "Малайзия": "MY",
    "Марокко": "MA", "Молдова": "MD", "Нигерия": "NG", "Норвегия": "NO", "Остров Мэн": "IM",
    "Панама": "PA", "Северная Македония": "MK", "Сингапур": "SG", "Словакия": "SK",
    "Словения": "SI", "Таиланд": "TH", "Танзания": "TZ", "Уганда": "UG", "Узбекистан": "UZ",
    "Финляндия": "FI", "Франция": "FR", "Хорватия": "HR", "Черногория": "ME", "Чехия": "CZ",
    "Швейцария": "CH", "Шри-Ланка": "LK",
    # встречаются в вакансиях из телеграм-каналов
    "Россия": "RU", "Беларусь": "BY", "Азербайджан": "AZ", "Киргизия": "KG", "Таджикистан": "TJ",
    "Новая Зеландия": "NZ", "Люксембург": "LU", "Исландия": "IS", "Албания": "AL",
    "Кюрасао и Синт-Мартен": "CW", "Пуэрто-Рико": "PR", "Парагвай": "PY", "Уругвай": "UY",
    "Эквадор": "EC", "Боливия": "BO", "Венесуэла": "VE", "Гватемала": "GT", "Доминикана": "DO",
    "Тунис": "TN", "Кот-д'Ивуар": "CI", "Замбия": "ZM", "Зимбабве": "ZW", "Эфиопия": "ET",
    "Пакистан": "PK", "Бангладеш": "BD", "Непал": "NP", "Шри Ланка": "LK", "Мьянма": "MM",
    "Камбоджа": "KH", "Южная Корея": "KR", "Тайвань": "TW", "Макао": "MO", "Монголия": "MN",
    "Саудовская Аравия": "SA", "Катар": "QA", "Кувейт": "KW", "Бахрейн": "BH", "Оман": "OM",
    "Иордания": "JO", "Ливан": "LB", "Кипр Северный": "CY", "Мальдивы": "MV", "Маврикий": "MU",
    "Сейшелы": "SC", "Багамы": "BS", "Барбадос": "BB", "Ямайка": "JM", "Коста Рика": "CR",
    "Джерси": "JE", "Гернси": "GG", "Андорра": "AD", "Монако": "MC", "Сан-Марино": "SM",
    "Лихтенштейн": "LI", "Гренландия": "GL", "Фарерские острова": "FO",
}

# Английские имена, которые уже участвуют в адресах кластеров — не переименовывать.
EN_FROZEN = {
    "США": "USA", "ЮАР": "South Africa", "ОАЭ": "UAE", "Чехия": "Czechia",
    "Великобритания": "United Kingdom",
    # CLDR отдаёт Türkiye и Curaçao — слаг из них выходит «t-rkiye» и «cura-ao»
    "Турция": "Turkey", "Кюрасао": "Curacao", "Кюрасао и Синт-Мартен": "Curacao",
    "Кот-д'Ивуар": "Cote d'Ivoire",
}


# Языки работы: в базе лежит эндоним («Русский», «Deutsch»), а на английской
# витрине человек ждёт «Russian». Имя берём из CLDR по коду языка.
JOB_LANGUAGE_CODES = {
    "English": "en", "Українська": "uk", "Русский": "ru", "Deutsch": "de",
    "Español": "es", "Français": "fr", "Português": "pt", "Polski": "pl",
    "Italiano": "it", "Ελληνικά": "el", "Română": "ro", "Български": "bg",
    "Türkçe": "tr", "Nederlands": "nl", "Svenska": "sv", "Suomi": "fi",
    "Norsk": "no", "Dansk": "da", "Čeština": "cs", "Magyar": "hu",
    "Hrvatski": "hr", "Srpski": "sr", "日本語": "ja", "한국어": "ko",
    "中文": "zh", "العربية": "ar", "עברית": "he", "हिन्दी": "hi",
}

# Теги-языки («немецкий», «шведский») ставит краулер по тексту вакансии.
TAG_LANGUAGE_CODES = {
    "английский": "en", "украинский": "uk", "русский": "ru", "немецкий": "de",
    "испанский": "es", "французский": "fr", "португальский": "pt", "польский": "pl",
    "итальянский": "it", "греческий": "el", "румынский": "ro", "болгарский": "bg",
    "турецкий": "tr", "нидерландский": "nl", "шведский": "sv", "финский": "fi",
    "норвежский": "no", "датский": "da", "чешский": "cs", "венгерский": "hu",
    "хорватский": "hr", "сербский": "sr", "японский": "ja", "корейский": "ko",
    "китайский": "zh", "арабский": "ar", "иврит": "he", "хинди": "hi",
}


def main() -> int:
    locales = {code: Locale.parse(code) for code in LANGS}
    countries, missing = {}, []
    for ru_name, iso in sorted(ISO.items()):
        row = {"iso": iso}
        for code in LANGS:
            name = locales[code].territories.get(iso, "")
            if not name:
                missing.append((ru_name, code))
                name = locales["en"].territories.get(iso, ru_name)
            row[code] = name
        if ru_name in EN_FROZEN:
            # имя из CLDR остаётся алиасом: источники пишут «United Arab Emirates»
            row["en_cldr"] = row["en"]
            row["en"] = EN_FROZEN[ru_name]
        countries[ru_name] = row

    languages = {}
    for table, capitalize in ((JOB_LANGUAGE_CODES, True), (TAG_LANGUAGE_CODES, False)):
        for label, code in sorted(table.items()):
            row = {}
            for lang in LANGS:
                name = locales[lang].languages.get(code, "")
                if not name:
                    missing.append((label, lang))
                    name = locales["en"].languages.get(code, label)
                # эндоним в шапке карточки идёт с большой буквы, тег — с маленькой
                row[lang] = name[:1].upper() + name[1:] if capitalize else name.lower()
            languages[label] = row

    if missing:
        print("нет имени в CLDR:", missing, file=sys.stderr)
    out = os.path.join(ROOT, "server", "i18n", "terms.auto.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"countries": countries, "languages": languages},
                  fh, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"{out}: {len(countries)} стран и {len(languages)} языков × {len(LANGS)} языков сайта")
    return 0


if __name__ == "__main__":
    sys.exit(main())
