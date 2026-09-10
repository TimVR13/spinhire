# SpinHire: запуск на Product Hunt и похожих площадках

Собрано 9 сентября 2026. Тексты — готовые к вставке, английские блоки не переводить.
В квадратных скобках то, что нужно заполнить руками. Дополняет `tasks/ai-outreach-kit.md`
(Wikidata, Crunchbase, LinkedIn, письма редакторам) — здесь только запуск на каталогах.

---

## 0. Что уже сделано в коде под запуск

| Изменение | Где | Зачем для запуска |
|---|---|---|
| Пресс-кит | `/press.html`, EN — `/en/press.html` | Каталоги и журналисты спрашивают логотип, описание и цифры. Одна ссылка вместо переписки. Цифры живые: подставляются из базы при каждом запросе |
| Чистка английского словаря | `js/i18n-en.js`, `server/i18n/en.json` | Было «WITH FORKS BY GRADE», «The plug is where the employer opened it», «Robot seller's office», «Tariffs», «Twist −10 SC». Исправлено ~900 строк: главная, тарифы, рынок, профессии, шапка, подвал, страница работодателя |
| Английские значения в открытом API | `/api/jobs?lang=en`, `/en/api/jobs`, `/en/api/market-stats` | В ответе были «офис», «Операции казино», «от £13 в час» и русская строка лицензии. Первое, что открывают на Hacker News и в каталогах API, — сам ответ |
| Карточка ссылки на языковых версиях | `og:locale`, `og:url`, EN og:title и og:description | С `ru_RU` и русским `og:url` ссылка в ленте Product Hunt, X и LinkedIn выглядела чужой и уводила на русскую версию. Заодно убрана неверная строчка «Salaries are open» |
| `/en/press` больше не роняет язык | `clean_static_pages` | Чистые адреса служебных страниц под языковым префиксом вели на русскую версию |
| Пресс-кит в подвале всех страниц, в `sitemap.xml` и в `llms.txt` | 63 файла, `server/app.py` | Каталоги и ИИ-ассистенты находят пресс-кит сами |
| Скрипты запуска | `scripts/launch_facts.py`, `scripts/launch_shots.py` | Свежие цифры для текстов и скриншоты галереи одной командой |
| Починен прогон тестов | `_mcp_start`, `tests/*` | Второй запуск lifespan ронял приложение («session manager can only be called once»), а три теста проверяли давно изменённые цены, константу краулера и порядок валидации. Теперь `python3 -m pytest tests` — 51 из 51 |

**Перед запуском обязательно:** задеплоить эти изменения (пуш в `main` → автодеплой) и
только потом снимать скриншоты для галереи — иначе на них попадут старые машинные переводы.

Что осталось на стороне владельца в самом продукте (не блокирует запуск, но заметно):

- Русский `meta description` главной обещает «Зарплаты открыты» — по индексу это 9%.
  В английской версии формулировка исправлена, русскую стоит привести к тому же виду.
- В выпадающем списке локаций видны сырые строки работодателей вроде
  «Kuala Lumpur, Малайзия»: это данные источников, а не интерфейс. Часть таких стран
  теперь переводится словарём, остальное лечится нормализацией в краулере.

---

## 1. Цифры: единственный источник правды

Никогда не берите числа из старых текстов. Перед каждой подачей:

```bash
python3 scripts/launch_facts.py          # человекочитаемый факт-лист
python3 scripts/launch_facts.py --json   # то же в JSON
```

Скрипт ходит на живой сайт (`/api/market-stats`) и печатает готовые формулировки.

Состояние на 9 сентября 2026:

| Факт | Значение |
|---|---|
| Живых вакансий | 6 103 |
| Компаний нанимают | 536 |
| Новых за неделю | 1 235 |
| Обновление индекса | каждые 6 часов |
| Профессий с вилками | 35 |
| Языков интерфейса | 12 (русский + 11) |
| Цена размещения | от €49, безлимит €599/мес |
| Открытие контакта из базы резюме | от €4 |
| Лицензия данных | CC BY 4.0 |
| Запуск проекта | 2026 |
| Контакт | hello@spinhire.io |

**Важно про формулировки.** В outreach-ките от 3 сентября значилось «1 036 компаний» —
сейчас в индексе 536: часть источников отвалилась, вакансии переехали. Не копируйте старую цифру.

**Чего писать нельзя.** Зарплата раскрыта примерно у 9% вакансий индекса (у собственных
вакансий работодателей — у всех, это правило площадки). Поэтому формулировка «salaries are
open» про весь индекс — неправда. Правильно: «salary ranges wherever the employer discloses
them; employer-posted jobs are published only with a range» и «35 profession cards with salary
bands». Это же исправлено и в английской версии сайта.

---

## 2. Product Hunt

### 2.1 Подготовка аккаунта (за 2–3 недели до запуска)

1. Завести аккаунт мейкера, заполнить профиль: фото, био, ссылки на X и LinkedIn.
   Пустые аккаунты PH понижает в ранжировании.
2. Две-три недели заходить и голосовать/комментировать чужие продукты — 5–10 действий в день.
3. Подписаться на 20–30 активных мейкеров в нише hiring/data.
4. Заранее решить, кто ещё числится мейкером (у каждого мейкера свой аккаунт с историей).
5. Хантера искать не обязательно: с 2023 года самостоятельный запуск не хуже.

### 2.2 Риск, который надо снять заранее

Product Hunt не принимает гемблинг-продукты. SpinHire — не гемблинг, а джоб-борд, но
модерация смотрит на казино-эстетику и на страницу с мини-играми. Что делает риск управляемым:

- В тексте страницы первым же предложением: *«a job board for the iGaming industry — an
  employment platform for a licensed industry, not a gambling service»*.
- `/games` закрыт в `robots.txt` и не попадает в галерею и ссылки. В подаче про мини-игры
  не упоминать вообще.
- Раздел «Worth keeping in mind» в пресс-ките формулирует то же самое: ставок и денежных
  выигрышей нет, баллы виртуальные.
- Если модерация всё же попросит пояснение — ответ готов в разделе 2.7.

### 2.3 Карточка продукта

**Name:** SpinHire

**Tagline (≤60 символов), в порядке предпочтения:**

1. `Open-data job board for the iGaming industry` (44)
2. `6,000 iGaming jobs with an open API, no paywall` (46)
3. `iGaming jobs, open API, public salary data` (42)

**Description (≤260 символов):**

```
A job board for online casino, betting, game studios, affiliates and payments. 6,000+ live jobs
from 500+ companies, refreshed every 6 hours. The whole index is an open API — no key, CC BY 4.0.
```

**Topics (выбрать 3, PH больше не даёт):** Hiring, Career, API. Запасные: Remote Work, Data & Analytics.

**Links:** сайт `https://spinhire.io/en/`, API `https://spinhire.io/en/api/jobs`,
рынок `https://spinhire.io/en/market`, пресс-кит `https://spinhire.io/en/press.html`.

**Pricing:** Free (candidates) / Paid (employers).

### 2.4 Галерея

Первый кадр решает больше, чем текст: в ленте видно только его. Формат 1270×760, PNG.
Сгенерировать после деплоя:

```bash
python3 scripts/launch_shots.py           # 6 кадров в img/press/launch/
python3 scripts/launch_shots.py --list    # что именно снимается
```

Порядок кадров и подписи (подпись впечатывается в кадр скриптом):

| # | Экран | Подпись (EN) |
|---|---|---|
| 1 | `/en/` герой + счётчики | 6,000+ live iGaming jobs, refreshed every 6 hours |
| 2 | `/en/jobs` с открытыми фильтрами | Filters the industry actually needs: vertical, licence, languages, relocation, crypto pay |
| 3 | `/en/market` | Public labour-market data with methodology and a monthly archive |
| 4 | `/en/professions` | 35 profession cards with salary bands by seniority and region |
| 5 | ответ `/api/jobs` в браузере | The whole index as an open API — no key, CC BY 4.0 |
| 6 | `/en/post-job` | For employers: structured posting, salary range required, mini-ATS |

Видео не обязательно. Если делаете — 30–45 секунд, без звука, показать поиск → карточку
вакансии → фильтр по релокации → страницу рынка.

**Thumbnail:** `img/logo-mark-sq.png` (200×200) или `img/favicons/apple-touch-icon.png`.

### 2.5 Первый комментарий мейкера

Публикуется сразу после того, как продукт появился в ленте.

```
Hi Product Hunt 👋 I'm [FOUNDER NAME], maker of SpinHire.

iGaming — online casinos, sportsbooks, game studios, affiliates, payments — hires constantly and
pays well, but its job market is strangely closed. The existing boards keep their index behind a
login or a paid employer account, and nobody publishes what is actually being hired, where, and
for how much.

We built SpinHire the other way round:

• The whole index is open. https://spinhire.io/en/api/jobs returns every live job, no key, CC BY 4.0,
  and every record links back to the original posting on the employer's site. Right now that's
  6,100+ jobs from 530+ companies, refreshed every 6 hours.
• Public labour-market data at /market — methodology, daily snapshots, permanent monthly URLs, CSV.
• 35 profession cards with salary bands by seniority and region.
• Industry fields as real filters: vertical, licence, languages, relocation, crypto pay.
• Machine-readable everywhere: markdown mirrors of every page, llms.txt, and an MCP server at
  /mcp so agents can query jobs without scraping.
• 12 languages, because a large part of this workforce is Russian- and Ukrainian-speaking, and the
  relocation hubs are Malta, Cyprus, Warsaw and Tbilisi.

To be clear about the category: this is an employment platform for a licensed industry, not a
gambling service. No betting, no money games.

I'll be here all day. What would you build on top of the API?
```

### 2.6 План дня запуска

Дата: вторник–четверг. Старт: 00:01 PT (это 10:01 по Кипру / 09:01 UTC зимой,
проверьте текущий сдвиг). Раньше 00:01 PT публиковать нет смысла — сутки считаются с полуночи PT.

| Время (PT) | Что делаем |
|---|---|
| −7 дней | Финальные тексты, галерея, черновик поставлен в расписание PH |
| −2 дня | Прогрев: пост «launching Tuesday» в Telegram RU/EN и LinkedIn, без ссылки |
| 00:01 | Продукт опубликован, сразу первый комментарий мейкера |
| 00:15 | Ссылка в оба Telegram-канала, LinkedIn, X. Формулировка — «мы на PH, будем рады фидбеку», без «upvote please»: PH банит за призывы к голосованию |
| 01:00–12:00 | Отвечать на каждый комментарий в течение 15 минут. Это главный рычаг ранжирования |
| 06:00 | Пост в r/SideProject и r/iGaming (см. 3.4), Indie Hackers |
| 09:00 | Рассылка по личным контактам (1:1, не спам-рассылка) |
| 18:00 | Промежуточный итог в комментариях: что спросили, что чиним |
| +1 день | Пост «спасибо + что дальше», подача на остальные каталоги волной 2 |
| +7 дней | Бейдж PH на сайт (`/press.html` или подвал), метрики в отчёт |

**Чего не делать:** покупать голоса, просить апвоты прямым текстом, слать одинаковые
сообщения в чаты. PH это ловит и снимает продукт из ленты.

### 2.7 Заготовки ответов на комментарии

- **«Это же гемблинг?»** → *SpinHire is a job board, not a gambling product. We index vacancies at
  licensed operators, studios and vendors — the same way a fintech job board indexes banks. No
  betting or money games anywhere on the site.*
- **«Откуда вакансии?»** → *Employer career pages and ATS feeds, crawled every 6 hours. Every card
  links to the original posting, and jobs that disappear at the source are archived automatically.
  Employers can also post directly — those go through human moderation and must include a salary range.*
- **«Как монетизируетесь, если API открыт?»** → *Candidates are free forever. Employers pay for
  posting (from €49), promotion, and unlocking contacts in the CV database. The open API is the index,
  not the product: the product is the hiring workflow on top of it.*
- **«Чем вы лучше LinkedIn / Indeed?»** → *We don't compete on volume, we compete on fields. Vertical,
  licence, languages, relocation and crypto pay are structured filters here, not text buried in the
  description — and the industry's own data is public.*
- **«Данные точные?»** → *Methodology is public at /market, daily snapshots are never recalculated,
  and every month has a permanent URL. The raw index is at /api/jobs — check it yourself.*
- **«Что с приватностью кандидата?»** → *Profiles are anonymous by default: employers see skills,
  languages and expectations, and pay to unlock a contact. Incognito mode hides you from your current employer.*

---

## 3. Похожие площадки: волна 1 (день запуска и +1)

Подавать не всё сразу: PH-день посвящён только PH, остальное — со следующего дня, по 3–4 площадки в день.

### 3.1 Hacker News — Show HN

Ссылка: <https://news.ycombinator.com/showhn.html>. Лучшее время: вторник–четверг, 08:00–10:00 ET.
HN не любит маркетинг, но любит открытые данные — заходить надо через API, а не через джоб-борд.

**Заголовок (≤80 символов):**
`Show HN: Open API and public labour-market data for iGaming jobs`

**Первый комментарий:**

```
I run SpinHire, a job board for the iGaming industry (online casino, sportsbook, game studios,
affiliates, payments). The part that might interest HN is not the board, it's the data.

Every other board in this sector keeps its index behind a login or a paid employer account. Ours is
open: https://spinhire.io/en/api/jobs — no key, no registration, CC BY 4.0, up to 100 records per page,
every record links to the original posting. ~6,100 live jobs from ~530 companies, re-crawled every
6 hours; jobs that 404 at the source are archived automatically.

On top of it: monthly labour-market stats with methodology and permanent per-month URLs
(/market, CSV and JSON), 35 profession cards with salary bands, markdown mirrors of every page,
llms.txt, and an MCP server at /mcp so agents can query it without scraping.

Stack: FastAPI + SQLAlchemy + SQLite, server-rendered HTML, a crawler that normalises salary strings
into min/max/currency/unit and classifies roles into 12 departments. Happy to go into the
normalisation part — it's the ugliest and most interesting piece.

To be explicit: it's an employment platform for a licensed industry, not a gambling service.
```

Отвечать на каждый комментарий, не спорить, не защищаться. Если прилетит «зачем миру ещё один
джоб-борд» — отвечать про открытые данные и нормализацию зарплат, а не про продукт.

### 3.2 Indie Hackers

Ссылка: <https://www.indiehackers.com/> → Create post, группа `Show IH` или `Job Boards`.
Формат — история, а не анонс: почему ниша, сколько заняло, что зарабатывает.

```
Title: I built an open-data job board for iGaming — 6,000 jobs, 12 languages, API with no key

iGaming is a strange market: it hires thousands of people across Malta, Cyprus, Warsaw and Tbilisi,
pays above mainstream IT, and its job market is almost invisible. Every board in the sector sells
access to its index.

I built the opposite. The index is an open API (CC BY 4.0), the labour-market stats are public with
methodology, and there are 35 profession cards with salary bands. Candidates pay nothing; employers
pay for posting (from €49) and for unlocking contacts in the CV database.

Numbers today: 6,100+ live jobs, 530+ companies, refreshed every 6 hours, 12 languages.
Stack: FastAPI, SQLAlchemy, SQLite, a crawler over career pages and ATS feeds.

Happy to answer anything about the crawler, the salary normalisation, or selling into this niche.
```

### 3.3 BetaList

Ссылка: <https://betalist.com/submit>. Берут ранние продукты; бесплатная очередь — недели,
платная — дни. Лимит описания ~600 символов.

```
SpinHire is a job board for the iGaming industry: online casino, betting, game studios, affiliates
and payments. It collects jobs straight from employer career pages and ATS feeds every 6 hours, so
every listing is live and links to the source. The whole index is an open API with no key
(CC BY 4.0), alongside public labour-market statistics and 35 profession cards with salary bands.
Runs in 12 languages with a focus on relocation hubs — Malta, Cyprus, Warsaw, Tbilisi — and remote.
```

### 3.4 Reddit

Одинаковый текст в трёх сабах — бан. Пишем разное, и сначала читаем правила каждого саба.

- **r/SideProject** — история сборки. Заголовок: `Open-data job board for a closed industry: 6,000 iGaming jobs, free API`.
- **r/iGaming, r/gambling_industry** — польза для индустрии, без API-пафоса: где сейчас нанимают, ссылка на /market.
- **r/dataisbeautiful** — только с графиком по /market и подписью с методикой (OC-флейр обязателен).
- **r/expats, r/Malta, r/cyprus** — отвечать в существующих тредах о работе, шаблоны в `ai-outreach-kit.md`, раздел 7.
- **r/webdev / r/Python** — про краулер и нормализацию зарплат, ссылка второстепенна.

Заготовка для r/SideProject:

```
Title: Open-data job board for a closed industry — 6,000 iGaming jobs, free API

iGaming (online casino, betting, game studios, affiliates) hires a lot and pays well, but every job
board in the sector hides its index behind a login. I built one that publishes it instead:
https://spinhire.io/api/jobs — no key, CC BY 4.0, every record links to the original posting.

6,100 live jobs from 530 companies, re-crawled every 6 hours. On top: public labour-market stats
with methodology, 35 profession cards with salary bands, 12 languages.

FastAPI + SQLAlchemy + SQLite, server-rendered. Happy to answer anything about the crawler.
```

### 3.5 Uneed, Fazier, Peerlist, Launching Next, Startup Stash

Малые каталоги, у всех одна и та же анкета: название, tagline, описание, категория, логотип,
скриншот, ссылка. Берём tagline и описание из 2.3, логотип и обложку — из `/press.html`.

| Площадка | Ссылка на подачу | Особенность |
|---|---|---|
| Uneed | https://www.uneed.best/submit-a-tool | Бесплатно, очередь ~1–2 недели, есть «Tool of the day» |
| Fazier | https://fazier.com/submit | Быстрая модерация, даёт бейдж на сайт |
| Peerlist Launchpad | https://peerlist.io/launchpad | Нужен профиль основателя, аудитория — разработчики |
| Launching Next | https://www.launchingnext.com/submit/ | Бесплатно, живёт долго в поиске |
| Startup Stash | https://startupstash.com/add-listing/ | Каталог с высоким DR, хорошая ссылка |
| SaaSHub | https://www.saashub.com/submit | Сравнения с конкурентами, полезно для «alternative to» запросов |
| AlternativeTo | https://alternativeto.net | Завести карточку и указать альтернативы: iGamingCareers, Casino Jobs, Gaming Jobs Online |
| F6S | https://www.f6s.com | Профиль стартапа, нужен для питчей и грантов |
| Pitchwall (бывший BetaPage) | https://pitchwall.co/submit | Бесплатная очередь; betapage.co теперь редиректит сюда |

---

## 4. Волна 2: каталоги, где мы уникальны (неделя после запуска)

Здесь у SpinHire позиция сильнее, чем на PH: открытый API и MCP-сервер — редкость.

### 4.1 Каталоги MCP-серверов

У нас публичный MCP-сервер без ключа (`https://spinhire.io/mcp`, Streamable HTTP,
инструменты `search_jobs`, `get_job`, `market_stats`, `market_history`, `list_professions`,
`get_profession`, `get_company`). Это готовый повод для отдельной волны подач.

| Каталог | Как подаём |
|---|---|
| mcp.so | Форма добавления сервера |
| PulseMCP | pulsemcp.com — форма «submit a server» |
| Glama MCP directory | glama.ai/mcp/servers — берёт из репозитория или по URL |
| Smithery | smithery.ai — публикация remote-сервера |
| awesome-mcp-servers (GitHub) | PR в список, категория Jobs / Data |
| Модельные каталоги коннекторов | Пока сервер без авторизации — годится для ручного добавления в клиентах |

Описание для каталогов MCP:

```
SpinHire iGaming Jobs — remote MCP server (Streamable HTTP, no auth) over a live index of 6,000+
iGaming jobs (online casino, betting, game studios, affiliates, payments), refreshed every 6 hours.
Tools: search_jobs, get_job, market_stats, market_history, list_professions, get_profession,
get_company. Data licensed CC BY 4.0, attribution to spinhire.io.
URL: https://spinhire.io/mcp
```

### 4.2 Каталоги открытых API

| Каталог | Как подаём |
|---|---|
| public-apis (GitHub, 300k★) | PR в раздел Jobs: `SpinHire | iGaming industry job listings | No auth | CC BY 4.0` |
| APIs.guru | PR с нашим `openapi.json` |
| RapidAPI Hub | Публикация как free API |
| API Tracker / ProgrammableWeb-подобные | Ручная анкета |
| Postman Public API Network | Коллекция из `openapi.json` |

### 4.3 Каталоги данных

| Площадка | Что выкладываем |
|---|---|
| Hugging Face Datasets | Снимок индекса + история рынка, карточка датасета с методикой, лицензия CC BY 4.0 |
| Kaggle Datasets | То же, но с notebook-примером: «iGaming hiring by country» |
| data.world | Зеркало CSV `/market.csv` |
| Google Dataset Search | Подхватит сам из Dataset-разметки на `/market` — проверить через Rich Results Test |

### 4.4 Отраслевые каталоги iGaming и джоб-бордов

| Площадка | Ссылка/действие | Смысл |
|---|---|---|
| Jobboardsearch.com | Форма добавления | Каталог джоб-бордов, откуда рекрутеры выбирают площадки |
| Job Board Directory (jobboarddirectory.co) | Форма | То же |
| iGB / SBC / Casino Beats — партнёрские каталоги | Письмо редакции, шаблоны в `ai-outreach-kit.md` §8 | Отраслевые медиа |
| Affiliate-каталоги (Партнеркин, AffTimes) | §6 outreach-кита | Русскоязычная аудитория ниши |
| Telegram-каталоги вакансий | Обмен анонсами с профильными каналами | Прямой трафик |

---

## 5. Тексты для соцсетей в день запуска

**X / Twitter (тред из 3):**

```
1/ SpinHire is live on Product Hunt 🎰

A job board for iGaming — online casino, betting, game studios, affiliates, payments.
6,100+ live jobs from 530+ companies, refreshed every 6 hours.

The whole index is an open API. No key. CC BY 4.0. [PH LINK]

2/ Every other board in this sector sells access to its index. We publish ours:
→ /en/api/jobs — the full live index
→ /market — labour-market stats with methodology and a monthly archive
→ /mcp — an MCP server so agents can query it without scraping

3/ Built with FastAPI + SQLAlchemy, server-rendered, 12 languages.
Candidates pay nothing. Employers pay for posting and CV contacts.
Feedback on the PH thread very welcome: [PH LINK]
```

**LinkedIn:**

```
SpinHire is live on Product Hunt today.

We built a job board for the iGaming industry and made the opposite bet from everyone else in the
sector: instead of selling access to our index, we publish it. 6,100+ live jobs from 530+ companies,
refreshed every 6 hours, available as an open API under CC BY 4.0 — plus public labour-market
statistics with methodology and 35 profession cards with salary bands.

Candidates use it for free. Employers pay for posting and for contacts in the CV database.
The site runs in 12 languages, with a focus on the industry's relocation hubs: Malta, Cyprus,
Warsaw, Tbilisi and remote.

If you hire in iGaming — or you're thinking about moving into it — I'd love your feedback: [PH LINK]
```

**Telegram RU:**

```
Мы на Product Hunt 🎰

SpinHire — джоб-борд iGaming: 6 100+ живых вакансий от 530+ компаний, обновление каждые 6 часов.
Весь индекс открыт: API без ключа, публичная статистика рынка труда, 35 профессий с вилками.

Зайдите, посмотрите, напишите в комментариях, чего не хватает — сегодня отвечаем на всё: [PH LINK]
```

**Telegram EN:** взять текст из блока X, свести в один абзац.

---

## 6. Чек-лист владельца

Аккаунты (создаёт владелец, тексты выше). Адреса регистрации — одним списком,
чтобы не искать заново:

| Где | Регистрация | Когда нужен |
|---|---|---|
| Product Hunt | https://www.producthunt.com/login (вход через X или Google) | За 2–3 недели, с прогревом: комментарии к чужим запускам |
| Hacker News | https://news.ycombinator.com/login | За 2–3 недели: нужна хоть какая-то история комментариев |
| Reddit | https://www.reddit.com/register/ | За 2–3 недели: без кармы автомодератор снимет пост |
| Indie Hackers | https://www.indiehackers.com/sign-up | В день запуска |
| BetaList | https://betalist.com/submit | Подача за 1–2 недели: очередь модерации |
| Uneed | https://www.uneed.best/submit-a-tool | День запуска +1 |
| Fazier | https://fazier.com/submit | День запуска +1 |
| Peerlist | https://peerlist.io/signup, запуск — https://peerlist.io/launchpad | День запуска +1 |
| Launching Next | https://www.launchingnext.com/submit/ | Волна 2 |
| Startup Stash | https://startupstash.com/add-listing/ | Волна 2 |
| SaaSHub | https://www.saashub.com/submit | Волна 2 |
| AlternativeTo | https://alternativeto.net | Волна 2 |
| F6S | https://www.f6s.com | Волна 2 |
| Pitchwall | https://pitchwall.co/submit | Волна 2 |
| Hugging Face | https://huggingface.co/join, датасет — https://huggingface.co/new-dataset | Волна 2 |
| Kaggle | https://www.kaggle.com/account/login | Волна 2 |
| data.world | https://data.world | Волна 2 |
| GitHub | аккаунт уже есть — нужен для PR в public-apis и awesome-mcp-servers | Волна 2 |

Каталоги MCP и API (аккаунт нужен не везде): https://mcp.so/submit,
https://www.pulsemcp.com, https://glama.ai/mcp/servers, https://smithery.ai,
https://github.com/public-apis/public-apis, https://apis.guru,
https://www.postman.com/explore.

Перед днём X:

- [ ] Изменения этой ветки задеплоены на прод
- [ ] `python3 scripts/launch_facts.py` — цифры в текстах обновлены
- [ ] `python3 scripts/launch_shots.py` — галерея снята уже после деплоя
- [ ] `/en/` и `/en/press.html` открыты и прочитаны глазами: английский без машинных ляпов
- [ ] `/en/api/jobs` отвечает без кириллицы в значениях, `/mcp`, `/market.csv`, `/llms.txt` отвечают
- [ ] Ссылка `https://spinhire.io/en/` прогнана через отладчики карточек X и LinkedIn:
      заголовок английский, `og:locale` — `en_US`
- [ ] Сервер выдержит всплеск: PH даёт 2–5 тысяч визитов в день, проверить лимиты и кеш
- [ ] Аналитика: отдельная UTM-метка на каждую площадку (`?utm_source=producthunt&utm_medium=launch`)
- [ ] Почта hello@spinhire.io читается в день запуска, автоответ выключен

После:

- [ ] Бейдж Product Hunt на сайт (см. ниже)
- [ ] Итоги в отчёт: визиты, регистрации, обращения работодателей по каждой площадке
- [ ] Волна 2 (MCP- и API-каталоги) — в течение недели после

### Бейдж Product Hunt

PH выдаёт готовый код на странице продукта («Embed» → Badge). Он выглядит так —
подставьте свой `post-id` и slug:

```html
<a href="https://www.producthunt.com/posts/spinhire?utm_source=badge-featured&utm_medium=badge"
   target="_blank" rel="noopener" aria-label="SpinHire on Product Hunt">
  <img src="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=POST_ID&theme=dark"
       alt="SpinHire — open-data job board for iGaming | Product Hunt"
       width="250" height="54" loading="lazy">
</a>
```

Куда класть: в подвал (`server/templates/base.html` и статические страницы — тот же блок,
что и ссылка на пресс-кит) либо отдельным блоком в пресс-кит. Картинка тянется с
`api.producthunt.com`, поэтому ставить её с `loading="lazy"` и не в самый верх страницы.
