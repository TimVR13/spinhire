"""Языковые версии не должны показывать русский текст.

Проверяем закрытый список: всё, что площадка сама подставляет в карточку —
страна, формат, направление, тег, язык работы, период вилки, служебная фраза, —
обязано иметь перевод на каждый язык сайта. Свободный текст работодателя сюда
не входит: его мы не переводим и не обещаем перевести.

Живой сайт проверяет scripts/i18n_audit.py — эти тесты ловят разрыв раньше,
на словарях.
"""
import re
import unittest

from server import terms
from server.app import CATEGORIES, COUNTRY_EN, FORMATS, country_of


CYRILLIC = re.compile(r"[А-Яа-яЁё]")


class TermCoverageTests(unittest.TestCase):
    def test_every_language_has_every_term(self):
        reference = set(terms.TERMS["en"])
        for lang in terms.LANGS:
            missing = reference - set(terms.TERMS[lang])
            self.assertFalse(missing, f"в словаре {lang} нет: {sorted(missing)[:10]}")

    def test_latin_languages_never_keep_russian(self):
        """На en/de/pl… перевод обязан быть без кириллицы — иначе это не перевод."""
        for lang in terms.LATIN_LANGS:
            for source, translated in terms.TERMS[lang].items():
                self.assertFalse(CYRILLIC.search(translated),
                                 f"{lang}: {source!r} → {translated!r}")

    def test_cyrillic_languages_actually_translate(self):
        """У bg/uk кириллица законна, но перевод не должен совпадать с русским."""
        same = {lang: [s for s, t in terms.TERMS[lang].items()
                       if s != t and s.lower() == t.lower()] for lang in ("bg", "uk")}
        for lang, values in same.items():
            self.assertFalse(values, f"{lang}: не переведено {values[:10]}")

    def test_categories_and_formats_are_covered(self):
        for value in CATEGORIES + FORMATS:
            for lang in terms.LANGS:
                self.assertIn(value, terms.TERMS[lang], f"{value!r} нет в {lang}")

    def test_countries_are_covered(self):
        for ru_name in COUNTRY_EN:
            for lang in terms.LANGS:
                self.assertIn(ru_name, terms.TERMS[lang], f"{ru_name!r} нет в {lang}")


class SubstitutionTests(unittest.TestCase):
    def test_word_boundaries_protect_russian_endings(self):
        """«вакансиям» не должно превращаться в «jobм» — это была живая ошибка."""
        self.assertEqual(terms.translate_terms("← Назад к вакансиям", "en"),
                         "← Назад к вакансиям")

    def test_country_suffix_in_location(self):
        self.assertEqual(terms.translate_terms("Nairobi, Кения", "en"), "Nairobi, Kenya")
        self.assertEqual(terms.translate_terms("Dubai, ОАЭ", "de"),
                         "Dubai, Vereinigte Arabische Emirate")

    def test_salary_period(self):
        self.assertEqual(terms.translate_terms("$350 000 в год", "en"), "$350 000/year")

    def test_service_words_do_not_touch_free_text(self):
        """Однословные ключи статей («в», «и», «из») в подстрочный словарь не попадают."""
        for lang in terms.LANGS:
            for word in ("в", "и", "из", "как", "или"):
                self.assertNotIn(word, terms.TERMS[lang])
        # предлоги и падежи подстрочник не трогает: «на Мальте» переводится
        # целиком словарём интерфейса, а не по словам
        self.assertEqual(terms.translate_terms("Работа в iGaming на Мальте", "en"),
                         "Работа в iGaming на Мальте")


class LocationTests(unittest.TestCase):
    def test_duplicate_country_is_collapsed(self):
        self.assertEqual(terms.location_label("Canada, Remote, Канада"), "Canada, Remote")
        self.assertEqual(terms.location_label("United Arab Emirates, Remote, ОАЭ"),
                         "United Arab Emirates, Remote")

    def test_city_and_its_country_are_both_kept(self):
        self.assertEqual(terms.location_label("Toronto, Canada"), "Toronto, Canada")

    def test_country_of_ignores_garbage(self):
        """«в USDT» и «Проект под NDA» — не страны, в фильтрах им места нет."""
        for junk in ("в USDT", "Проект под NDA", "в зависимости от грейда", "2 Locations"):
            self.assertEqual(country_of(junk), terms.UNKNOWN_COUNTRY, junk)

    def test_country_of_prefers_the_tail(self):
        """«Atlanta, Georgia, US» — это США, а не Грузия."""
        self.assertEqual(country_of("Atlanta, Georgia, US"), "США")
        self.assertEqual(country_of("Tbilisi, Georgia"), "Грузия")


class FallbackTests(unittest.TestCase):
    def test_unknown_country_falls_back_to_english_not_russian(self):
        self.assertEqual(terms.country_name("Небывалия", "de"), "Небывалия")
        self.assertEqual(terms.country_name("Кения", "el"), "Κένυα")

    def test_crawler_and_site_share_one_table(self):
        from server import crawler
        self.assertIs(crawler._COUNTRY_RU, terms.COUNTRY_NAMES)


if __name__ == "__main__":
    unittest.main()
