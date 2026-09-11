"""Служебная лексика площадки на всех языках сайта — единственный источник правды.

Здесь лежит закрытый список того, что придумали мы, а не работодатель: страны,
форматы работы, направления, теги, языки, периоды зарплаты и служебные фразы
(«по запросу», «Компания не указана»). Из этого модуля собираются

* подстрочный словарь серверного перевода HTML (server/app.py),
* клиентский словарь /js/i18n-terms.js (js/app.js),
* нормализация локаций краулером (server/crawler.py),
* подписи карточек в скриптах соцсетей (scripts/*.py).

Правило простое: если краулер умеет записать значение в базу, оно обязано быть
здесь со всеми языками. tests/test_i18n_terms.py это проверяет, а
scripts/i18n_audit.py ловит то, что всё-таки просочилось на живой сайт.

Страны и названия языков не пишутся руками: server/i18n/terms.auto.json собран
из CLDR скриптом scripts/build_geo_terms.py.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_LANG = "ru"
# языки сайта, кроме русского
LANGS = ["en", "de", "pl", "fr", "es", "pt", "it", "el", "ro", "bg", "uk"]
# на этих версиях кириллица в тексте — всегда ошибка
LATIN_LANGS = ["en", "de", "pl", "fr", "es", "pt", "it", "el", "ro"]

_AUTO = json.load(open(os.path.join(ROOT, "server", "i18n", "terms.auto.json"), encoding="utf-8"))
COUNTRIES = _AUTO["countries"]        # русское имя → {iso, en, de, …}
LANGUAGE_NAMES = _AUTO["languages"]   # «Русский» / «шведский» → имя языка по локали

COUNTRY_ISO = {ru: row["iso"] for ru, row in COUNTRIES.items()}


def _rows(pairs):
    """[(рус, en, de, pl, fr, es, pt, it, el, ro, bg, uk)] → {рус: {lang: перевод}}."""
    out = {}
    for row in pairs:
        assert len(row) == len(LANGS) + 1, row
        out[row[0]] = dict(zip(LANGS, row[1:]))
    return out


CATEGORIES = _rows([
    ("Операции казино", "Casino operations", "Casino-Betrieb", "Operacje kasyna",
     "Opérations casino", "Operaciones de casino", "Operações de casino",
     "Operazioni casinò", "Λειτουργία καζίνο", "Operațiuni cazino",
     "Казино операции", "Операції казино"),
    ("Беттинг и трейдинг", "Betting & trading", "Betting & Trading", "Bukmacherka i trading",
     "Paris et trading", "Apuestas y trading", "Apostas e trading", "Betting e trading",
     "Στοιχηματισμός & trading", "Pariuri și trading", "Бетинг и трейдинг", "Беттінг і трейдинг"),
    ("Разработка игр", "Game development", "Spieleentwicklung", "Tworzenie gier",
     "Développement de jeux", "Desarrollo de juegos", "Desenvolvimento de jogos",
     "Sviluppo giochi", "Ανάπτυξη παιχνιδιών", "Dezvoltare de jocuri",
     "Разработка на игри", "Розробка ігор"),
    ("Аффилейты и медиабаинг", "Affiliates & media buying", "Affiliates & Media-Buying",
     "Afiliacja i media buying", "Affiliation et media buying", "Afiliados y compra de medios",
     "Afiliados e media buying", "Affiliazione e media buying", "Affiliates & media buying",
     "Afiliere și media buying", "Афилиейти и медия байинг", "Афілейти та медіабаїнг"),
    ("Комплаенс и AML", "Compliance & AML", "Compliance & AML", "Compliance i AML",
     "Conformité et AML", "Cumplimiento y AML", "Compliance e AML", "Compliance e AML",
     "Συμμόρφωση & AML", "Conformitate și AML", "Комплайънс и AML", "Комплаєнс і AML"),
    ("Платежи и антифрод", "Payments & antifraud", "Zahlungen & Betrugsprävention",
     "Płatności i antyfraud", "Paiements et antifraude", "Pagos y antifraude",
     "Pagamentos e antifraude", "Pagamenti e antifrode", "Πληρωμές & antifraud",
     "Plăți și antifraudă", "Плащания и антифрод", "Платежі та антифрод"),
    ("Поддержка игроков", "Player support", "Spieler-Support", "Wsparcie graczy",
     "Support joueurs", "Soporte al jugador", "Suporte ao jogador", "Supporto giocatori",
     "Υποστήριξη παικτών", "Suport jucători", "Поддръжка на играчи", "Підтримка гравців"),
    ("Маркетинг и CRM", "Marketing & CRM", "Marketing & CRM", "Marketing i CRM",
     "Marketing et CRM", "Marketing y CRM", "Marketing e CRM", "Marketing e CRM",
     "Μάρκετινγκ & CRM", "Marketing și CRM", "Маркетинг и CRM", "Маркетинг і CRM"),
    ("Данные и BI", "Data & BI", "Daten & BI", "Dane i BI", "Données et BI", "Datos y BI",
     "Dados e BI", "Dati e BI", "Δεδομένα & BI", "Date și BI", "Данни и BI", "Дані та BI"),
    ("Финансы, право и HR", "Finance, legal & HR", "Finanzen, Recht & HR",
     "Finanse, prawo i HR", "Finance, juridique et RH", "Finanzas, legal y RRHH",
     "Finanças, jurídico e RH", "Finanza, legale e HR", "Οικονομικά, νομικά & HR",
     "Finanțe, juridic și HR", "Финанси, право и HR", "Фінанси, право і HR"),
    ("Топ-менеджмент", "Executive", "Top-Management", "Kadra zarządzająca",
     "Direction générale", "Alta dirección", "Alta direção", "Top management",
     "Ανώτατα στελέχη", "Management executiv", "Топ мениджмънт", "Топменеджмент"),
])

FORMATS = _rows([
    ("офис", "office", "Büro", "biuro", "bureau", "oficina", "escritório", "ufficio",
     "γραφείο", "birou", "офис", "офіс"),
    ("Офис", "Office", "Büro", "Biuro", "Bureau", "Oficina", "Escritório", "Ufficio",
     "Γραφείο", "Birou", "Офис", "Офіс"),
    ("гибрид", "hybrid", "hybrid", "hybrydowo", "hybride", "híbrido", "híbrido", "ibrido",
     "υβριδικό", "hibrid", "хибрид", "гібрид"),
    ("Гибрид", "Hybrid", "Hybrid", "Hybrydowo", "Hybride", "Híbrido", "Híbrido", "Ibrido",
     "Υβριδικό", "Hibrid", "Хибрид", "Гібрид"),
    ("удалёнка", "remote", "remote", "zdalnie", "télétravail", "remoto", "remoto",
     "da remoto", "εξ αποστάσεως", "remote", "дистанционно", "віддалено"),
    ("Удалёнка", "Remote", "Remote", "Zdalnie", "Télétravail", "Remoto", "Remoto",
     "Da remoto", "Εξ αποστάσεως", "Remote", "Дистанционно", "Віддалено"),
    ("удалённо", "remote", "remote", "zdalnie", "télétravail", "remoto", "remoto",
     "da remoto", "εξ αποστάσεως", "remote", "дистанционно", "віддалено"),
    ("Удалённо", "Remote", "Remote", "Zdalnie", "Télétravail", "Remoto", "Remoto",
     "Da remoto", "Εξ αποστάσεως", "Remote", "Дистанционно", "Віддалено"),
    ("удалёнка ЕС", "remote in EU", "remote in der EU", "zdalnie w UE", "télétravail UE",
     "remoto en la UE", "remoto na UE", "da remoto in UE", "εξ αποστάσεως στην ΕΕ",
     "remote în UE", "дистанционно в ЕС", "віддалено в ЄС"),
])

TAGS = _rows([
    ("аффилейты", "affiliates", "Affiliates", "afiliacja", "affiliation", "afiliados",
     "afiliados", "affiliazione", "affiliates", "afiliere", "афилиейти", "афілейти"),
    ("спортсбук", "sportsbook", "Sportsbook", "sportsbook", "sportsbook", "sportsbook",
     "sportsbook", "sportsbook", "sportsbook", "sportsbook", "спортсбук", "спортсбук"),
    ("беттинг", "betting", "Betting", "betting", "paris sportifs", "apuestas", "apostas",
     "betting", "στοίχημα", "pariuri", "бетинг", "беттінг"),
    ("платежи", "payments", "Zahlungen", "płatności", "paiements", "pagos", "pagamentos",
     "pagamenti", "πληρωμές", "plăți", "плащания", "платежі"),
    ("медиабаинг", "media buying", "Media-Buying", "media buying", "media buying",
     "compra de medios", "media buying", "media buying", "media buying", "media buying",
     "медия байинг", "медіабаїнг"),
    ("крипто", "crypto", "Krypto", "krypto", "crypto", "cripto", "cripto", "cripto",
     "crypto", "cripto", "крипто", "крипто"),
    ("слоты", "slots", "Slots", "sloty", "machines à sous", "slots", "slots", "slot",
     "slots", "sloturi", "слотове", "слоти"),
    ("антифрод", "antifraud", "Betrugsprävention", "antyfraud", "antifraude", "antifraude",
     "antifraude", "antifrode", "antifraud", "antifraudă", "антифрод", "антифрод"),
    ("релокация", "relocation", "Relocation", "relokacja", "relocation", "reubicación",
     "relocação", "relocation", "μετεγκατάσταση", "relocare", "релокация", "релокація"),
    ("геймдев-движки", "game engines", "Game-Engines", "silniki gier", "moteurs de jeu",
     "motores de juego", "motores de jogo", "motori di gioco", "μηχανές παιχνιδιών",
     "motoare de joc", "гейм енджини", "геймдев-рушії"),
    ("BI-инструменты", "BI tools", "BI-Tools", "narzędzia BI", "outils BI",
     "herramientas BI", "ferramentas BI", "strumenti BI", "εργαλεία BI", "instrumente BI",
     "BI инструменти", "BI-інструменти"),
    ("удержание", "retention", "Retention", "retencja", "rétention", "retención",
     "retenção", "retention", "retention", "retenție", "задържане", "утримання"),
])

# Города, которые краулер и работодатели пишут по-русски.
CITIES = _rows([
    ("Москва", "Moscow", "Moskau", "Moskwa", "Moscou", "Moscú", "Moscovo", "Mosca",
     "Μόσχα", "Moscova", "Москва", "Москва"),
    ("Санкт-Петербург", "Saint Petersburg", "Sankt Petersburg", "Petersburg",
     "Saint-Pétersbourg", "San Petersburgo", "São Petersburgo", "San Pietroburgo",
     "Αγία Πετρούπολη", "Sankt-Petersburg", "Санкт Петербург", "Санкт-Петербург"),
    ("Санкт-Петербурге", "Saint Petersburg", "Sankt Petersburg", "Petersburg",
     "Saint-Pétersbourg", "San Petersburgo", "São Petersburgo", "San Pietroburgo",
     "Αγία Πετρούπολη", "Sankt-Petersburg", "Санкт Петербург", "Санкт-Петербург"),
    ("Киев", "Kyiv", "Kyjiw", "Kijów", "Kyiv", "Kiev", "Kiev", "Kiev", "Κίεβο", "Kiev",
     "Киев", "Київ"),
    ("Київ", "Kyiv", "Kyjiw", "Kijów", "Kyiv", "Kiev", "Kiev", "Kiev", "Κίεβο", "Kiev",
     "Киев", "Київ"),
    ("Львов", "Lviv", "Lwiw", "Lwów", "Lviv", "Leópolis", "Lviv", "Leopoli", "Λβιβ",
     "Liov", "Лвив", "Львів"),
    ("Варшава", "Warsaw", "Warschau", "Warszawa", "Varsovie", "Varsovia", "Varsóvia",
     "Varsavia", "Βαρσοβία", "Varșovia", "Варшава", "Варшава"),
    ("Братислава", "Bratislava", "Bratislava", "Bratysława", "Bratislava", "Bratislava",
     "Bratislava", "Bratislava", "Μπρατισλάβα", "Bratislava", "Братислава", "Братислава"),
    ("Лимассол", "Limassol", "Limassol", "Limassol", "Limassol", "Limasol", "Limassol",
     "Limassol", "Λεμεσός", "Limassol", "Лимасол", "Лімасол"),
    ("Лимасол", "Limassol", "Limassol", "Limassol", "Limassol", "Limasol", "Limassol",
     "Limassol", "Λεμεσός", "Limassol", "Лимасол", "Лімасол"),
    ("Другие страны", "Other countries", "Andere Länder", "Inne kraje", "Autres pays",
     "Otros países", "Outros países", "Altri paesi", "Άλλες χώρες", "Alte țări",
     "Други държави", "Інші країни"),
])

# Служебные фразы, которые площадка подставляет вместо пустых полей.
SERVICE = _rows([
    ("по запросу", "on request", "auf Anfrage", "do uzgodnienia", "sur demande",
     "a convenir", "a combinar", "su richiesta", "κατόπιν αιτήματος", "la cerere",
     "по договаряне", "за запитом"),
    ("Не указана", "Not specified", "Nicht angegeben", "Nie podano", "Non précisé",
     "No especificado", "Não especificado", "Non specificato", "Δεν προσδιορίζεται",
     "Nespecificat", "Не е посочена", "Не вказано"),
    ("Не указан", "Not specified", "Nicht angegeben", "Nie podano", "Non précisé",
     "No especificado", "Não especificado", "Non specificato", "Δεν προσδιορίζεται",
     "Nespecificat", "Не е посочен", "Не вказано"),
    ("не указана", "not specified", "nicht angegeben", "nie podano", "non précisé",
     "no especificado", "não especificado", "non specificato", "δεν προσδιορίζεται",
     "nespecificat", "не е посочена", "не вказано"),
    ("не указан", "not specified", "nicht angegeben", "nie podano", "non précisé",
     "no especificado", "não especificado", "non specificato", "δεν προσδιορίζεται",
     "nespecificat", "не е посочен", "не вказано"),
    ("Компания не указана", "Company not specified", "Unternehmen nicht angegeben",
     "Firma nieokreślona", "Entreprise non précisée", "Empresa no especificada",
     "Empresa não especificada", "Azienda non specificata", "Εταιρεία χωρίς όνομα",
     "Companie nespecificată", "Компанията не е посочена", "Компанію не вказано"),
    ("Другое", "Other", "Sonstiges", "Inne", "Autre", "Otro", "Outro", "Altro", "Άλλο",
     "Altele", "Друго", "Інше"),
    ("мес", "month", "Monat", "mies.", "mois", "mes", "mês", "mese", "μήνα", "lună",
     "месец", "міс."),
    ("локация скрыта", "location hidden", "Standort verborgen", "lokalizacja ukryta",
     "localisation masquée", "ubicación oculta", "localização oculta", "località nascosta",
     "κρυφή τοποθεσία", "locație ascunsă", "локацията е скрита", "локацію приховано"),
    ("активно ищет", "actively looking", "sucht aktiv", "aktywnie szuka",
     "en recherche active", "busca activamente", "procura ativamente", "cerca attivamente",
     "ψάχνει ενεργά", "caută activ", "активно търси", "активно шукає"),
    ("активность сегодня", "active today", "heute aktiv", "aktywny dzisiaj",
     "actif aujourd’hui", "activo hoy", "ativo hoje", "attivo oggi", "ενεργός σήμερα",
     "activ astăzi", "активен днес", "активність сьогодні"),
    ("активность вчера", "active yesterday", "gestern aktiv", "aktywny wczoraj",
     "actif hier", "activo ayer", "ativo ontem", "attivo ieri", "ενεργός χθες",
     "activ ieri", "активен вчера", "активність вчора"),
    ("активность на этой неделе", "active this week", "diese Woche aktiv",
     "aktywny w tym tygodniu", "actif cette semaine", "activo esta semana",
     "ativo esta semana", "attivo questa settimana", "ενεργός αυτήν την εβδομάδα",
     "activ săptămâna aceasta", "активен тази седмица", "активність цього тижня"),
    ("лет опыта", "years of experience", "Jahre Erfahrung", "lat doświadczenia",
     "ans d’expérience", "años de experiencia", "anos de experiência", "anni di esperienza",
     "χρόνια εμπειρίας", "ani de experiență", "години опит", "років досвіду"),
    ("Обновлено", "Updated", "Aktualisiert", "Zaktualizowano", "Mis à jour", "Actualizado",
     "Atualizado", "Aggiornato", "Ενημερώθηκε", "Actualizat", "Обновено", "Оновлено"),
    ("хочет", "expects", "erwartet", "oczekuje", "attend", "espera", "espera", "si aspetta",
     "προσδοκά", "așteaptă", "очаква", "хоче"),
])

# Фразы, которые собираются в коде вместе с числом. В подстрочный словарь они
# не идут — там от них толку нет; они попадают во второй индекс сервера, где
# число заменено на «#» (см. _I18N_NUM в server/app.py).
NUMBERED = _rows([
    ("обновлено # дн. назад", "updated # days ago", "vor # Tagen aktualisiert",
     "zaktualizowano # dni temu", "mis à jour il y a # jours",
     "actualizado hace # días", "atualizado há # dias", "aggiornato # giorni fa",
     "ενημερώθηκε πριν # ημέρες", "actualizat acum # zile", "обновено преди # дни",
     "оновлено # дн. тому"),
    ("# лет опыта", "# years of experience", "# Jahre Erfahrung",
     "# lat doświadczenia", "# ans d’expérience", "# años de experiencia",
     "# anos de experiência", "# anni di esperienza", "# χρόνια εμπειρίας",
     "# ani de experiență", "# години опит", "# років досвіду"),
])

# Периоды в вилке приходят слитно с суммой («$350 000 в год») — словарь целых
# строк их не ловит, поэтому это отдельные подстроки с ведущим пробелом.
PERIODS = _rows([
    (" в год", "/year", "/Jahr", "/rok", "/an", "/año", "/ano", "/anno", "/έτος", "/an",
     "/година", "/рік"),
    (" в месяц", "/month", "/Monat", "/mies.", "/mois", "/mes", "/mês", "/mese", "/μήνα",
     "/lună", "/месец", "/міс."),
    (" в час", "/hour", "/Std.", "/godz.", "/heure", "/hora", "/hora", "/ora", "/ώρα",
     "/oră", "/час", "/год."),
])


# «от», «до» — служебные слова вилки. В общий подстрочный словарь они не идут:
# короткие предлоги, заменённые по всему тексту, и превращали русские фразы в
# кашу вроде «Работа to iGaming». Здесь они применяются только к полю зарплаты.
SALARY_WORDS = _rows([
    ("от", "from", "ab", "od", "à partir de", "desde", "a partir de", "da", "από",
     "de la", "от", "від"),
    ("до", "up to", "bis", "do", "jusqu’à", "hasta", "até", "fino a", "έως", "până la",
     "до", "до"),
    ("в год", "/year", "/Jahr", "/rok", "/an", "/año", "/ano", "/anno", "/έτος", "/an",
     "/година", "/рік"),
    ("в месяц", "/month", "/Monat", "/mies.", "/mois", "/mes", "/mês", "/mese", "/μήνα",
     "/lună", "/месец", "/міс."),
    ("мес", "month", "Monat", "mies.", "mois", "mes", "mês", "mese", "μήνα", "lună",
     "месец", "міс."),
    ("в час", "/hour", "/Std.", "/godz.", "/heure", "/hora", "/hora", "/ora", "/ώρα",
     "/oră", "/час", "/год."),
    ("час", "hour", "Std.", "godz.", "heure", "hora", "hora", "ora", "ώρα", "oră",
     "час", "год."),
    ("год", "year", "Jahr", "rok", "an", "año", "ano", "anno", "έτος", "an",
     "година", "рік"),
])

_SALARY_RE = {}
for _lang in LANGS:
    _keys = sorted(SALARY_WORDS, key=len, reverse=True)
    _SALARY_RE[_lang] = re.compile(
        r"(?<![А-Яа-яЁёІіЇїЄєҐґ])(?:" + "|".join(re.escape(k) for k in _keys)
        + r")(?![А-Яа-яЁёІіЇїЄєҐґ])")


def salary_label(value: str, lang: str = BASE_LANG) -> str:
    """«от £13 в час» → «from £13/hour». Только для поля зарплаты."""
    if lang not in _SALARY_RE or not value or not CYRILLIC_RE.search(value):
        return value
    value = translate_terms(value, lang)          # «по запросу» и прочие целые фразы
    # «$1 800 / мес» и «$350 000 в год» приводим к одной форме до подстановки
    value = re.sub(r"\s*/\s*(мес|час|год)\b", r"/\1", value)
    out = _SALARY_RE[lang].sub(lambda m: SALARY_WORDS[m.group(0)][lang], value)
    return re.sub(r"\s+/", "/", out)


# Вертикали работодателей из data/vendor-seeds.json собраны из небольшого
# набора слов («Слоты / Live Casino», «Агрегатор + платформа»). Переводим их
# по словам, но только в этом поле: «казино» и «платформа» — слишком частые
# слова, чтобы менять их по всей странице.
INDUSTRY_WORDS = _rows([
    ("Слоты", "Slots", "Slots", "Sloty", "Machines à sous", "Slots", "Slots", "Slot",
     "Slots", "Sloturi", "Слотове", "Слоти"),
    ("Агрегатор", "Aggregator", "Aggregator", "Agregator", "Agrégateur", "Agregador",
     "Agregador", "Aggregatore", "Aggregator", "Agregator", "Агрегатор", "Агрегатор"),
    ("платформа", "platform", "Plattform", "platforma", "plateforme", "plataforma",
     "plataforma", "piattaforma", "πλατφόρμα", "platformă", "платформа", "платформа"),
    ("Платформа", "Platform", "Plattform", "Platforma", "Plateforme", "Plataforma",
     "Plataforma", "Piattaforma", "Πλατφόρμα", "Platformă", "Платформа", "Платформа"),
    ("Спортбет", "Sportsbook", "Sportsbook", "Sportsbook", "Paris sportifs",
     "Apuestas deportivas", "Apostas desportivas", "Sportsbook", "Sportsbook",
     "Pariuri sportive", "Спортбет", "Спортбет"),
    ("Казино", "Casino", "Casino", "Kasyno", "Casino", "Casino", "Casino", "Casinò",
     "Καζίνο", "Cazino", "Казино", "Казино"),
    ("казино", "casino", "Casino", "kasyno", "casino", "casino", "casino", "casinò",
     "καζίνο", "cazino", "казино", "казино"),
    ("провайдер", "provider", "Anbieter", "dostawca", "fournisseur", "proveedor",
     "fornecedor", "fornitore", "πάροχος", "furnizor", "доставчик", "провайдер"),
    ("Контент", "Content", "Content", "Content", "Contenu", "Contenido", "Conteúdo",
     "Contenuti", "Περιεχόμενο", "Conținut", "Съдържание", "Контент"),
    ("Разработка", "Development", "Entwicklung", "Development", "Développement",
     "Desarrollo", "Desenvolvimento", "Sviluppo", "Ανάπτυξη", "Dezvoltare",
     "Разработка", "Розробка"),
    ("Наземные", "Land-based", "Stationär", "Naziemne", "En dur", "Presenciales",
     "Presenciais", "Terrestri", "Επίγεια", "Terestre", "Наземни", "Наземні"),
    ("Онлайн", "Online", "Online", "Online", "En ligne", "Online", "Online", "Online",
     "Online", "Online", "Онлайн", "Онлайн"),
    ("Аффилиат", "Affiliate", "Affiliate", "Afiliacyjna", "Affiliation", "Afiliados",
     "Afiliados", "Affiliazione", "Affiliate", "Afiliere", "Афилиейт", "Афілейт"),
    ("Скретч-карты", "Scratch cards", "Rubbellose", "Zdrapki", "Cartes à gratter",
     "Rascas", "Raspadinhas", "Gratta e vinci", "Ξυστά", "Răzuibile", "Изтривалки",
     "Скретч-картки"),
    ("Виртуал спорт", "Virtual sports", "Virtuelle Sportarten", "Sporty wirtualne",
     "Sports virtuels", "Deportes virtuales", "Desportos virtuais", "Sport virtuali",
     "Εικονικά σπορ", "Sporturi virtuale", "Виртуален спорт", "Віртуальний спорт"),
    ("Лотереи", "Lotteries", "Lotterien", "Loterie", "Loteries", "Loterías",
     "Lotarias", "Lotterie", "Λοταρίες", "Loterii", "Лотарии", "Лотереї"),
    ("ПО", "software", "Software", "oprogramowanie", "logiciel", "software",
     "software", "software", "λογισμικό", "software", "софтуер", "ПЗ"),
    ("Блокчейн", "Blockchain", "Blockchain", "Blockchain", "Blockchain", "Blockchain",
     "Blockchain", "Blockchain", "Blockchain", "Blockchain", "Блокчейн", "Блокчейн"),
])

_INDUSTRY_RE = {}
for _lang in LANGS:
    _keys = sorted(INDUSTRY_WORDS, key=len, reverse=True)
    _INDUSTRY_RE[_lang] = re.compile(
        r"(?<![А-Яа-яЁёІіЇїЄєҐґ])(?:" + "|".join(re.escape(k) for k in _keys)
        + r")(?![А-Яа-яЁёІіЇїЄєҐґ])")


def industry_label(value: str, lang: str = BASE_LANG) -> str:
    """«Агрегатор + платформа» → «Aggregator + platform». Только поле вертикали."""
    if lang not in _INDUSTRY_RE or not value or not CYRILLIC_RE.search(value):
        return value
    return _INDUSTRY_RE[lang].sub(lambda m: INDUSTRY_WORDS[m.group(0)][lang], value)


# Телеграм-парсер иногда берёт за название компании кусок фразы из объявления:
# «ищем в FinTech-компанию» → «FinTech-компанию», «крупное digital-издательство
# спортивных медиа». Это не имя работодателя, а описание в косвенном падеже:
# перевести его нельзя, а на английской витрине оно выглядит как брак.
# Показываем такие вакансии как «компания не указана» — что и есть правда.
# Регистр здесь значим: с большой буквы начинаются настоящие имена
# («Париматч», «ПростоМедіа, ТОВ»), с маленькой — обрывки фраз.
_ANON_COMPANY_RE = re.compile(
    r"^[а-яё]"                                     # строчная буква в начале
    r"|(?<![А-Яа-яЁё-])(?:для|из)(?![А-Яа-яЁё])"   # предлог внутри названия
    r"|[-\s](?:компанию|компания|компанией|компаний|проект|проекта|проекту)$")


def looks_anonymous(name: str) -> bool:
    """Название — обрывок фразы, а не имя работодателя."""
    value = (name or "").strip()
    return bool(value) and bool(CYRILLIC_RE.search(value)) and bool(_ANON_COMPANY_RE.search(value))


def company_label(name: str, lang: str = BASE_LANG) -> str:
    """Имя работодателя как показывать. Настоящие имена не трогаем никогда."""
    if looks_anonymous(name):
        return TERMS.get(lang, {}).get("Компания не указана", "Компания не указана")
    return name


def _country_terms() -> dict:
    return {ru: {lang: row[lang] for lang in LANGS} for ru, row in COUNTRIES.items()}


def _language_terms() -> dict:
    return {label: {lang: row[lang] for lang in LANGS} for label, row in LANGUAGE_NAMES.items()}


# Порядок важен: последний словарь переопределяет предыдущие. Страны идут раньше
# служебных фраз, чтобы «Не указана» осталась фразой, а не превратилась в страну.
_SOURCES = (_country_terms(), _language_terms(), CATEGORIES, FORMATS, TAGS, CITIES,
            SERVICE, PERIODS)

TERMS = {lang: {} for lang in LANGS}
for _table in _SOURCES:
    for _ru, _row in _table.items():
        for _lang in LANGS:
            if _row.get(_lang):
                TERMS[_lang][_ru] = _row[_lang]

# Границы по кириллице: без них «вакансиям» превращалось в «jobм», а «Дизайн» —
# в «Дvonайн». Первым идёт самый длинный ключ, иначе «Не указана» съест «Не указан».
_BOUNDARY = r"(?<![А-Яа-яЁёІіЇїЄєҐґ])(?:%s)(?![А-Яа-яЁёІіЇїЄєҐґ])"
TERM_RE = {}
for _lang, _table in TERMS.items():
    _keys = sorted(_table, key=len, reverse=True)
    TERM_RE[_lang] = re.compile(_BOUNDARY % "|".join(re.escape(k) for k in _keys))

CYRILLIC_RE = re.compile(r"[А-Яа-яЁёІіЇїЄєҐґ]")


def translate_terms(text: str, lang: str) -> str:
    """Заменить служебную лексику в свободной строке («Nairobi, Кения» → «Nairobi, Kenya»)."""
    table, pattern = TERMS.get(lang), TERM_RE.get(lang)
    if not table or not pattern or not CYRILLIC_RE.search(text):
        return text
    return pattern.sub(lambda m: table[m.group(0)], text)


def country_name(ru_name: str, lang: str = BASE_LANG) -> str:
    """Имя страны на языке страницы. На латинской версии русского не отдаём никогда."""
    if lang == BASE_LANG:
        return ru_name
    row = COUNTRIES.get(ru_name)
    if row:
        return row.get(lang) or row["en"]
    value = TERMS.get(lang, {}).get(ru_name)
    if value:
        return value
    # неизвестное значение: на латинской версии лучше английское, чем русское
    return TERMS.get("en", {}).get(ru_name, ru_name) if lang in LATIN_LANGS else ru_name


# ---------- нормализация свободного текста локации в страну ----------
# Всё, что источники пишут вместо страны: английское имя, ISO, город, локальное
# написание. Собирается из таблицы стран, чтобы новая страна появлялась сразу.
# COUNTRY_NAMES — только имена стран (на всех языках сайта, плюс ISO и имя из
# CLDR, если витринное заморожено). По ним же схлопываются повторы в локации.
COUNTRY_NAMES = {}
for _ru, _row in COUNTRIES.items():
    COUNTRY_NAMES[_ru.lower()] = _ru
    COUNTRY_NAMES[_row["iso"].lower()] = _ru
    for _key, _value in _row.items():
        if _key != "iso" and _value:
            COUNTRY_NAMES[_value.lower()] = _ru

COUNTRY_ALIASES = dict(COUNTRY_NAMES)

# Города и исторические написания, которых нет в CLDR.
CITY_COUNTRY = {
    "sliema": "Мальта", "st julian": "Мальта", "st julian's": "Мальта", "valletta": "Мальта",
    "gzira": "Мальта", "gżira": "Мальта", "ta' xbiex": "Мальта", "birkirkara": "Мальта",
    "limassol": "Кипр", "nicosia": "Кипр", "larnaca": "Кипр", "paphos": "Кипр",
    "warsaw": "Польша", "warszawa": "Польша", "варшава": "Польша", "krakow": "Польша",
    "kraków": "Польша", "poznan": "Польша", "wroclaw": "Польша", "wrocław": "Польша",
    "gdansk": "Польша", "katowice": "Польша",
    "kyiv": "Украина", "kiev": "Украина", "київ": "Украина", "киев": "Украина",
    "lviv": "Украина", "львов": "Украина", "львів": "Украина", "odesa": "Украина",
    "london": "Великобритания", "manchester": "Великобритания", "leeds": "Великобритания",
    "england": "Великобритания", "scotland": "Великобритания", "uk": "Великобритания",
    "great britain": "Великобритания", "britain": "Великобритания",
    "bucharest": "Румыния", "cluj": "Румыния", "sofia": "Болгария", "plovdiv": "Болгария",
    "athens": "Греция", "thessaloniki": "Греция", "madrid": "Испания",
    "barcelona": "Испания", "malaga": "Испания", "lisbon": "Португалия",
    "lisboa": "Португалия", "porto": "Португалия", "berlin": "Германия",
    "munich": "Германия", "hamburg": "Германия", "sao paulo": "Бразилия",
    "são paulo": "Бразилия", "rio de janeiro": "Бразилия",
    "new jersey": "США", "las vegas": "США", "new york": "США", "usa": "США",
    "u.s.": "США", "united states of america": "США", "california": "США",
    "toronto": "Канада", "montreal": "Канада", "vancouver": "Канада", "calgary": "Канада",
    "ontario": "Канада", "tbilisi": "Грузия", "batumi": "Грузия", "yerevan": "Армения",
    "belgrade": "Сербия", "novi sad": "Сербия", "manila": "Филиппины",
    "capetown": "ЮАР", "cape town": "ЮАР", "johannesburg": "ЮАР",
    "dubai": "ОАЭ", "abu dhabi": "ОАЭ", "uae": "ОАЭ", "u.a.e.": "ОАЭ",
    "stockholm": "Швеция", "riga": "Латвия", "tallinn": "Эстония", "vilnius": "Литва",
    "amsterdam": "Нидерланды", "dublin": "Ирландия", "dublin city": "Ирландия",
    "milan": "Италия", "rome": "Италия", "nairobi": "Кения", "colombo": "Шри-Ланка",
    "kuala lumpur": "Малайзия", "medellin": "Колумбия", "bogota": "Колумбия",
    "san josé": "Коста-Рика", "san jose": "Коста-Рика", "bratislava": "Словакия",
    "братислава": "Словакия", "москва": "Россия", "moscow": "Россия",
    "санкт-петербург": "Россия", "санкт-петербурге": "Россия", "saint petersburg": "Россия",
    "isle of man": "Остров Мэн", "gibraltar": "Гибралтар", "curacao": "Кюрасао",
    "curaçao": "Кюрасао", "ho chi minh": "Вьетнам", "hanoi": "Вьетнам",
    "jakarta": "Индонезия", "bangkok": "Таиланд", "singapore": "Сингапур",
    "hong kong": "Гонконг", "tokyo": "Япония", "seoul": "Южная Корея",
    "buenos aires": "Аргентина", "lima": "Перу", "santiago": "Чили",
    "mexico city": "Мексика", "ciudad de méxico": "Мексика", "almaty": "Казахстан",
    "astana": "Казахстан", "tashkent": "Узбекистан", "baku": "Азербайджан",
    "tel aviv": "Израиль", "istanbul": "Турция", "ankara": "Турция",
    "czech republic": "Чехия", "prague": "Чехия", "praha": "Чехия",
    "bosnia and herzegovina": "Босния", "north macedonia": "Северная Македония",
}
COUNTRY_ALIASES.update(CITY_COUNTRY)

def location_label(raw: str, lang: str = BASE_LANG) -> str:
    """«Canada, Remote, Канада» → «Canada, Remote»: убрать повтор страны.

    Краулер дописывает страну к строке источника, а источник её часто уже назвал —
    просто на своём языке. Схлопываем только повторы стран: город из той же страны
    («Toronto, Canada») — это не дубль, а нормальная пара.

    На латинской версии части, оставшиеся русскими после перевода, выбрасываем.
    Телеграм-парсер иногда кладёт в локацию что попало («в USDT», «ТОЛЬКО ОФИС»),
    и такой мусор лучше не показывать вовсе, чем показывать по-русски.
    """
    parts = [p.strip() for p in (raw or "").split(",")]
    seen, out = set(), []
    for part in parts:
        if not part:
            continue
        key = COUNTRY_NAMES.get(part.lower(), part.lower())
        if key in seen:
            continue
        if lang in LATIN_LANGS and CYRILLIC_RE.search(translate_terms(part, lang)):
            continue
        seen.add(key)
        out.append(part)
    return ", ".join(out)


# Псевдострана «Удалёнка» и заглушка «Не указана» стран не имеют, но живут в тех
# же фильтрах и счётчиках.
REMOTE_COUNTRY = "Удалёнка"
UNKNOWN_COUNTRY = "Не указана"
