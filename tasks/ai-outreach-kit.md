# SpinHire outreach kit

Prepared 3 September 2026. Every block below is ready to copy-paste. Square brackets mark things you must fill in or verify before sending.

## Fact sheet (single source of truth for every text in this kit)

| Fact | Value |
|---|---|
| Site | https://spinhire.io |
| What it is | Job board for the iGaming industry: online casino, betting, game studios, affiliates, payments |
| Live vacancies | 5 601 (verified 3 Sept 2026) |
| Companies | 1 036 |
| Refresh | every 6 hours, from employer career pages and ATS feeds |
| Profession cards | 35, each with a salary band |
| Market stats | https://spinhire.io/market (monthly archive, methodology page) |
| Open API | https://spinhire.io/api/jobs (no key, CC BY 4.0, every record links to the original posting) |
| Machine-readable | markdown mirror for every job, company and profession; https://spinhire.io/llms.txt |
| Languages | Russian first, plus English, German, Polish, Ukrainian, French, Spanish, Portuguese, Italian, Greek, Romanian, Bulgarian |
| Telegram | @spinhire_ru (Russian), @spinhire (English) |
| LinkedIn | https://www.linkedin.com/company/spinhirejob |
| Launched | 2026 |
| Contact | hello@spinhire.io |
| Positioning | the only iGaming job board with a Russian/Ukrainian-speaking focus plus full English coverage; open data instead of a paywalled index; relocation focus (Malta, Cyprus, Warsaw, Tbilisi, remote) |

Note on language count: the brief says "11 languages" but lists 12 (Russian plus 11 more; the repo has 11 translation dictionaries plus Russian as default). The texts below say "12 languages" or "Russian plus 11 more". Change to 11 if Russian is not counted in your public copy.

Rounding rule used below: "5,600+ vacancies", "1,000+ companies". When quoting exact numbers, always add the date.

---

## 1. Wikidata

Before creating the item: Wikidata deletes items about companies that have no independent coverage. Safest order is (a) get at least one listicle or press mention live (sections 5 and 8), (b) then create the item and cite that mention plus the official site. If you create it earlier, keep the statement set minimal and sourced to the official site.

Start: https://www.wikidata.org/wiki/Special:NewItem

### Label, description, aliases

| Field | en | ru |
|---|---|---|
| Label | SpinHire | SpinHire |
| Description | online job board for the iGaming industry | онлайн-доска вакансий для индустрии iGaming |
| Aliases | spinhire.io; SpinHire Jobs; SpinHire iGaming jobs | Спинхайр; spinhire.io; СпинХайр |

Keep the description lowercase, no trailing period, no marketing words (Wikidata convention).

### Statements

| Property | Value | Qualifier | Source needed | Notes |
|---|---|---|---|---|
| P31 instance of | employment website [find QID, label "employment website"] | | yes (official site is acceptable) | Add a second P31 = website (Q35127) |
| P31 instance of | website (Q35127) | | no | |
| P571 inception | 2026 (precision: year) | | yes: official site "about" or launch post | Change to full date if you publish one |
| P856 official website | https://spinhire.io | P407 language of work = Russian (Q7737) | no | Add one P856 per language subfolder only if the URLs differ in a stable way, e.g. https://spinhire.io/en/ |
| P407 language of work or name | Russian (Q7737), English (Q1860), German (Q188), Polish (Q809), Ukrainian (Q8798), French (Q150), Spanish (Q1321), Portuguese (Q5146), Italian (Q652), Modern Greek (Q36510), Romanian (Q7913), Bulgarian (Q7918) | | no | Verify each QID before saving; the ones listed are the standard language items |
| P452 industry | online gambling [find QID]; employment website / recruitment [find QID] | | recommended | |
| P17 country | [COUNTRY QID: placeholder, legal entity country] | | yes (company register) | Leave empty rather than guess |
| P495 country of origin | [COUNTRY QID: placeholder] | | yes | Same as P17 unless the product was launched from elsewhere |
| P159 headquarters location | [CITY QID: placeholder] | | yes | Leave empty if no public address |
| P112 founded by | [FOUNDER NAME item, only if the person has a Wikidata item] | | yes | Do not create a person item for this |
| P1448 official name | SpinHire (mul or en) | | no | |
| P4264 LinkedIn company ID | spinhirejob | | no | From https://www.linkedin.com/company/spinhirejob |
| P3789 Telegram username | spinhire_ru | P407 = Russian | no | Second value: spinhire, P407 = English |
| P2002 X (Twitter) username | [placeholder, only if an account exists] | | no | |
| P2013 Facebook ID | [placeholder, only if a page exists] | | no | |
| P6634 (LinkedIn personal) | do not use | | | Personal profiles do not belong on the company item |
| P275 copyright license | Creative Commons Attribution 4.0 International [verify QID] | P518 applies to part = API / data | yes: https://spinhire.io/api/jobs docs page | Only if the license is stated on the site |
| P1324 source code repository | leave empty | | | Not open source |
| P8687 social media followers | leave empty for now | P585 point in time | yes | Add later with a dated screenshot or public count |

What reviewers look for: an independent reference on at least one statement (P31 or P571), an official website, and no promotional wording. Add the reference as "reference URL" (P854) + "retrieved" (P813) + "title" (P1476).

---

## 2. Crunchbase organization profile

Start: https://www.crunchbase.com/add-new (needs a free account).

**Organization name:** SpinHire

**Short description (≤150 characters):**

Job board for the iGaming industry: 5,600+ live vacancies from 1,000+ companies, open API, public labour-market stats, 12 languages.

(131 characters)

**Long description:**

SpinHire is a job board for the iGaming industry: online casinos, sportsbooks, game studios, affiliates, payments and the vendors around them. The index is rebuilt every 6 hours from employer career pages and ATS feeds, so listings are live and each record links back to the original posting. As of 3 September 2026 it holds 5,601 vacancies from 1,036 companies.

The site is built around open data. The full job index is available through a keyless API at spinhire.io/api/jobs under a CC BY 4.0 license, every job, company and profession page has a markdown mirror, and a public labour-market page at spinhire.io/market publishes monthly hiring statistics with an archive and a methodology note. 35 profession cards give salary bands for the roles most often hired in the sector.

SpinHire is the only iGaming job board with a Russian- and Ukrainian-speaking focus and full English coverage; the interface runs in 12 languages. A large share of listings are in relocation hubs (Malta, Cyprus, Warsaw, Tbilisi) or fully remote. Launched in 2026.

**Categories (pick up to 5 from Crunchbase's list):** Recruiting, Employment, Gambling, Online Portals, Information Services

**Tags / keywords:** iGaming jobs, online casino careers, sportsbook hiring, job board, open data, labour market statistics, relocation Malta, relocation Cyprus, remote iGaming, Russian-speaking jobs

**Founded:** 2026

**Website:** https://spinhire.io

**Email:** hello@spinhire.io

**LinkedIn:** https://www.linkedin.com/company/spinhirejob

**Twitter / X:** [leave empty unless an account exists]

**Facebook:** [leave empty]

**Headquarters:** [CITY, COUNTRY: placeholder]

**Founders:** [FOUNDER NAME], [FOUNDER NAME]

**Operating status:** Active

**Company type:** For Profit

**Number of employees:** [1-10 / 11-50: choose]

**Funding:** leave the funding section empty. Do not add a "bootstrapped" round; it requires a date and amount.

**Logo:** square PNG, at least 400x400, no text smaller than the wordmark.

---

## 3. Product Hunt launch

Start: https://www.producthunt.com/posts/new

**Name:** SpinHire

**Tagline (≤60 characters):**

iGaming jobs with an open API and public salary data

(52 characters)

Alternatives if the first is taken or feels flat:
- Open-data job board for the iGaming industry (44)
- 5,600 iGaming jobs, open API, no paywall (40)

**Description (shown under the gallery):**

SpinHire is a job board for the iGaming industry: online casinos, betting, game studios, affiliates and payments. It pulls vacancies directly from employer career pages and ATS feeds every 6 hours, so what you see is live and each listing links to the source. Today: 5,600+ jobs from 1,000+ companies.

What makes it different from other job boards in the sector:
- The whole index is an open API at spinhire.io/api/jobs. No key, CC BY 4.0.
- A public labour-market page (spinhire.io/market) with monthly stats, archive and methodology.
- 35 profession cards with salary bands.
- Markdown mirrors of every page and an llms.txt, so agents and LLMs can read it too.
- 12 languages. Russian and Ukrainian speakers get first-class coverage; English is complete.
- Relocation-friendly: Malta, Cyprus, Warsaw, Tbilisi and remote are the biggest clusters.

**Topics (5):** Hiring and Recruiting, Career, Developer Tools, Data and Analytics, Remote Work

**Links to add:** https://spinhire.io, https://spinhire.io/api/jobs, https://spinhire.io/market

**Maker's first comment (English, about 180 words):**

Hi Product Hunt, I'm [FOUNDER NAME], maker of SpinHire.

The iGaming industry (online casinos, sportsbooks, game studios, affiliates, payments) hires a lot and pays well, but its job market is oddly closed. The existing boards keep their indexes behind logins or paid employer accounts, and there is no public data on who hires what and where.

We built SpinHire the other way round. The whole index is open: https://spinhire.io/api/jobs returns every live vacancy, no API key, licensed CC BY 4.0, and every record points to the original posting on the employer's site. The index is refreshed every 6 hours from career pages and ATS feeds. Right now that's 5,600+ jobs from 1,000+ companies.

On top of the data we publish a monthly labour-market page (spinhire.io/market) with methodology and an archive, 35 profession cards with salary bands, and markdown mirrors plus an llms.txt so agents can read the site without scraping.

The interface runs in 12 languages, with Russian and Ukrainian as first-class citizens, because that is where a large part of the industry's workforce comes from.

Happy to answer anything about the data, the crawler, or the sector. What would you build on top of the API?

**Three launch-day posts for X / LinkedIn / Telegram:**

1. SpinHire is live on Product Hunt. 5,600+ iGaming jobs from 1,000+ companies, refreshed every 6 hours. The whole index is an open API, no key, CC BY 4.0. [PH LINK]

2. Most job boards sell access to their index. We publish ours: spinhire.io/api/jobs plus a monthly labour-market report at spinhire.io/market. Launching today on Product Hunt: [PH LINK]

3. If you are thinking about Malta, Cyprus, Warsaw or Tbilisi, iGaming is the industry hiring there. We built a job board for it in 12 languages. Today on Product Hunt: [PH LINK]

---

## 4. LinkedIn company page, About section

Edit: https://www.linkedin.com/company/spinhirejob/admin/ (Page info > About)

**EN (about 120 words):**

SpinHire is a job board for the iGaming industry: online casinos, sportsbooks, game studios, affiliates, payments and their vendors. We collect vacancies directly from employer career pages and ATS feeds every 6 hours, so every listing is live and links to the original posting. As of September 2026 the index holds 5,600+ jobs from 1,000+ companies.

We publish our data instead of selling access to it: an open API (spinhire.io/api/jobs, no key, CC BY 4.0), a monthly labour-market report at spinhire.io/market, and 35 profession cards with salary bands.

The site runs in 12 languages, with full coverage for Russian- and Ukrainian-speaking candidates, and focuses on relocation hubs: Malta, Cyprus, Warsaw, Tbilisi and remote.

Contact: hello@spinhire.io

**RU:**

SpinHire: доска вакансий для индустрии iGaming. онлайн-казино, беттинг, игровые студии, партнёрские сети, платёжные сервисы и их подрядчики. Вакансии собираются напрямую с карьерных страниц работодателей и из ATS каждые 6 часов, поэтому каждое объявление актуально и ведёт на первоисточник. На сентябрь 2026 года в индексе 5 600+ вакансий от 1 000+ компаний.

Мы публикуем данные, а не продаём доступ к ним: открытый API (spinhire.io/api/jobs, без ключа, лицензия CC BY 4.0), ежемесячная статистика рынка труда на spinhire.io/market и 35 карточек профессий с вилками зарплат.

Сайт работает на 12 языках. Русский и украинский основные, английский покрыт полностью. Фокус на релокацию: Мальта, Кипр, Варшава, Тбилиси и удалёнка.

Контакт: hello@spinhire.io

Specialties field (comma-separated): iGaming recruitment, online casino jobs, sportsbook jobs, game studio jobs, affiliate marketing jobs, payments jobs, relocation Malta, relocation Cyprus, remote jobs, labour market data, open API

---

## 5. Outreach emails to listicle editors (English)

Targets and what to ask for:

| Target | Page | Ask | Where to find the contact |
|---|---|---|---|
| businessofigaming.com | "Best iGaming Job Platforms" | add SpinHire as an entry | editorial email on the site footer or author byline |
| europeangaming.eu | "Best iGaming jobs" | add SpinHire; offer a stats quote | editor@ / contact form; they also take press releases |
| startup.jobs | job boards directory | directory listing | submit form on the directory page, then email |
| jobboardsearch.com | job board directory | listing in the "Gaming / Gambling" niche | submit form, then email the founder |
| jobboardfinder.com | job board directory | listing + short review | "Add a job board" form; paid upgrade is optional |

Replace [ARTICLE TITLE] and [SITE] per target. Send from hello@spinhire.io or a named founder address; named senders get more replies.

### Variant A: short cold email (≤120 words)

Subject options:
- One more entry for "[ARTICLE TITLE]"
- iGaming job board with an open API, for your list
- Missing from [ARTICLE TITLE]: SpinHire

Hi [NAME],

I read your piece "[ARTICLE TITLE]" and would like to suggest one addition: SpinHire (https://spinhire.io), a job board for the iGaming industry launched in 2026.

Why it might be worth a line:
- 5,600+ live vacancies from 1,000+ companies, refreshed every 6 hours from career pages and ATS feeds
- the full index is an open API (no key, CC BY 4.0), which no other board in the sector offers
- public monthly labour-market stats at spinhire.io/market
- 12 languages, with Russian and Ukrainian coverage on top of English

Happy to send a logo, a one-paragraph blurb, or an exclusive stat for the article.

Best,
[FOUNDER NAME]
SpinHire, hello@spinhire.io

### Variant B: follow-up (≤60 words), send 5 to 7 days later

Subject: Re: One more entry for "[ARTICLE TITLE]"

Hi [NAME],

Quick nudge on SpinHire for "[ARTICLE TITLE]". If a listing is out of scope, no problem; if it helps, here is a ready 40-word blurb:

"SpinHire: iGaming job board with 5,600+ live vacancies from 1,000+ companies, an open CC BY 4.0 API and public monthly hiring stats. 12 languages."

Thanks,
[FOUNDER NAME]

### Variant C: data-led pitch with a free market-stats quote

Subject options:
- Free data point for your iGaming jobs article: [STAT]
- Which iGaming roles are hiring most this quarter (data for your piece)

Hi [NAME],

I run SpinHire, an iGaming job board that publishes its labour-market data openly (spinhire.io/market). I would like to offer you a stat or two for "[ARTICLE TITLE]" or a future update, no strings attached.

Examples from the current month, all reproducible from the public page:
- [X]% of live iGaming vacancies are fully remote; [Y]% are in Malta, [Z]% in Cyprus
- the three most-hired roles are [ROLE 1], [ROLE 2], [ROLE 3]
- [N] companies posted their first iGaming vacancy this month

Method: we index 1,000+ employer career pages and ATS feeds every 6 hours, dedupe, and count live postings; the methodology is on the page. The raw data is available via an open API (spinhire.io/api/jobs, CC BY 4.0), so you or your readers can check any number.

If a custom cut would be more useful (by country, by role family, by seniority), tell me what you need and I will send it within a day, with a chart if you want one. Attribution to SpinHire is the only ask.

Best,
[FOUNDER NAME]
SpinHire, hello@spinhire.io

---

## 6. Outreach in Russian: Партнеркин, vc.ru, Habr Career, AffTimes

Общие правила: писать с именного адреса, одну ссылку в коротком варианте, до трёх в длинном, цифры с датой. Имя редактора и название подборки подставить руками.

### Партнеркин (подборки ресурсов для iGaming / арбитража)

**Короткое письмо / DM**

Тема: Дополнение в подборку «[НАЗВАНИЕ ПОДБОРКИ]»

Здравствуйте, [ИМЯ]!

Читал вашу подборку «[НАЗВАНИЕ ПОДБОРКИ]». Предлагаю добавить SpinHire (https://spinhire.io), доску вакансий по iGaming: казино, беттинг, игровые студии, партнёрки, платежи. Запущена в 2026 году.

Коротко: 5 600+ живых вакансий от 1 000+ компаний, обновление каждые 6 часов с карьерных страниц и ATS, русский и украинский языки на первом месте, открытый API без ключа, публичная статистика рынка труда.

Могу прислать логотип, описание на 40 слов или эксклюзивную цифру для материала.

[ИМЯ ОСНОВАТЕЛЯ], SpinHire, hello@spinhire.io

**Длинный питч с данными**

Тема: Данные по рынку труда iGaming для Партнеркина: кого нанимают партнёрки в [МЕСЯЦ] 2026

Здравствуйте, [ИМЯ]!

Я делаю SpinHire, доску вакансий по iGaming, где вся статистика открыта: https://spinhire.io/market. Хочу предложить вам цифры для подборки или отдельного материала.

Что есть прямо сейчас (все данные воспроизводимы по публичной странице и открытому API):
- сколько вакансий в affiliate-направлении открыто сегодня и как это изменилось за месяц: [X] вакансий, [±Y]% к прошлому месяцу
- топ-3 роли в партнёрском сегменте: [РОЛЬ 1], [РОЛЬ 2], [РОЛЬ 3]
- медианная вилка для affiliate-менеджера по карточке профессии: [$A–$B]
- доля удалёнки против офисов на Кипре и Мальте: [X]% / [Y]% / [Z]%
- сколько компаний впервые вышли на рынок найма в этом месяце: [N]

Методика: индексируем 1 000+ карьерных страниц и ATS-фидов каждые 6 часов, дедуплицируем, считаем живые объявления. API открыт без ключа под CC BY 4.0, каждая запись ведёт на первоисточник.

Могу сделать выгрузку под ваш запрос (по гео, по роли, по грейду) за день, с графиком. Единственное условие: ссылка на источник.

[ИМЯ ОСНОВАТЕЛЯ], SpinHire, hello@spinhire.io

### vc.ru (редакция / предложение колонки)

**Короткое письмо**

Тема: Колонка для vc.ru: рынок труда iGaming в цифрах, с открытыми данными

Здравствуйте!

Я основатель SpinHire (https://spinhire.io), доски вакансий по iGaming с открытой статистикой рынка. Предлагаю колонку для vc.ru: «Кого и где нанимает iGaming в 2026: [N] вакансий, [K] компаний, цифры по Мальте, Кипру, Варшаве, Тбилиси и удалёнке».

Все цифры из публичной страницы и API, любую можно проверить. Без рекламы тарифов, только данные и выводы. Черновик на 6–8 тысяч знаков пришлю за 3 дня.

Подойдёт ли формат? Если нужен другой угол (релокация, зарплаты по 35 профессиям, кто нанимает русскоязычных), могу сделать под него.

[ИМЯ ОСНОВАТЕЛЯ], hello@spinhire.io

**Длинный питч с данными**

Тема: Материал с данными: iGaming нанимает русскоязычных, и вот сколько

Здравствуйте, [ИМЯ]!

Пишу с предложением материала для vc.ru. Тема, на которую нет открытой статистики: рынок труда индустрии онлайн-казино, беттинга и игровых студий, куда уходит заметная часть русскоязычных разработчиков, маркетологов и саппорта.

У нас есть данные. SpinHire индексирует карьерные страницы 1 000+ iGaming-компаний каждые 6 часов; на 3 сентября 2026 в индексе 5 601 живая вакансия. Всё открыто: страница статистики https://spinhire.io/market с архивом и методикой, API без ключа под CC BY 4.0.

План колонки:
1. Сколько вакансий и в каких хабах: Мальта [X]%, Кипр [Y]%, Варшава [Z]%, Тбилиси [W]%, удалёнка [R]%.
2. Кого нанимают чаще всего: топ-10 ролей с долями.
3. Зарплаты: вилки по 35 профессиям, где iGaming платит выше «обычного» IT.
4. Кто нанимает русскоязычных: доля вакансий с требованием русского/украинского языка.
5. Как читать вакансии в этой индустрии: лицензии, юрисдикции, что значит «B2B» и «B2C».

Формат: 8–10 тысяч знаков, 4–5 графиков, все данные с ссылками на источник. Никаких скидок и промокодов в тексте. Готов сделать под ваш редакционный формат и сроки.

[ИМЯ ОСНОВАТЕЛЯ], SpinHire, hello@spinhire.io

### Habr Career (партнёрства / контент)

**Короткое письмо**

Тема: Данные по зарплатам в iGaming для Habr Career

Здравствуйте!

Я делаю SpinHire (https://spinhire.io), доску вакансий по iGaming с открытыми данными. У нас 35 карточек профессий с зарплатными вилками и 5 600+ живых вакансий от 1 000+ компаний.

Предлагаю сотрудничество по данным: сравнить ваш зарплатный калькулятор с нашими вилками по инженерным ролям в iGaming (backend, frontend, QA, data, DevOps) и сделать совместную публикацию. Данные с нашей стороны открыты под CC BY 4.0.

Если интересно, пришлю таблицу по 10 ролям за день.

[ИМЯ ОСНОВАТЕЛЯ], hello@spinhire.io

**Длинный питч с данными**

Тема: Совместный материал: сколько платят разработчикам в iGaming против рынка

Здравствуйте, [ИМЯ]!

У Habr Career лучший открытый источник по зарплатам в русскоязычном IT. У нас есть то, чего в нём нет: срез по индустрии iGaming, куда ушла заметная часть аудитории Хабра после 2022 года.

SpinHire индексирует карьерные страницы и ATS 1 000+ iGaming-компаний каждые 6 часов. На 3 сентября 2026 в индексе 5 601 вакансия. По 35 профессиям есть вилки, статистика опубликована на https://spinhire.io/market, API открыт без ключа под CC BY 4.0.

Идея материала: «Разработчик в iGaming: сколько платят и где», сравнение с медианами Habr Career.
- медиана для backend-разработчика в iGaming: [$X] против [$Y] по Habr Career
- доля вакансий с релокацией на Кипр / Мальту / в Варшаву: [A]% / [B]% / [C]%
- доля полностью удалённых позиций: [R]%
- какие стеки чаще всего: [СТЕК 1], [СТЕК 2], [СТЕК 3]
- сколько компаний ищут русскоговорящих инженеров: [N] из 1 036

Формат: совместная статья в блоге Habr Career или на Хабре, взаимные ссылки на источники данных. Готов отдать сырые данные для вашей проверки.

[ИМЯ ОСНОВАТЕЛЯ], SpinHire, hello@spinhire.io

### AffTimes

**Короткое письмо / DM**

Тема: SpinHire для подборки сервисов / раздела вакансий AffTimes

Здравствуйте, [ИМЯ]!

Предлагаю добавить SpinHire (https://spinhire.io) в подборку сервисов для арбитражников и iGaming-специалистов. Это доска вакансий по индустрии: партнёрки, казино, беттинг, платежи. 5 600+ живых вакансий от 1 000+ компаний, обновление каждые 6 часов, русский язык на первом месте, открытый API и статистика рынка.

Если у вас есть раздел вакансий или рассылка, могу отдавать подборку горячих affiliate-вакансий раз в неделю бесплатно.

[ИМЯ ОСНОВАТЕЛЯ], hello@spinhire.io

**Длинный питч с данными**

Тема: Цифры для AffTimes: рынок найма в affiliate-сегменте iGaming, [МЕСЯЦ] 2026

Здравствуйте, [ИМЯ]!

Я основатель SpinHire, доски вакансий по iGaming с открытыми данными (https://spinhire.io/market). Предлагаю AffTimes ежемесячную рубрику или разовый материал по найму в affiliate-сегменте.

Что можем дать по данным на [ДАТА]:
- количество открытых вакансий с affiliate / partnerships / media buying в названии: [X], динамика за месяц [±Y]%
- топ-5 нанимающих компаний в сегменте: [СПИСОК]
- гео: Кипр [A]%, Мальта [B]%, удалёнка [C]%, остальное [D]%
- вилки по карточкам профессий: Affiliate Manager [$..], Head of Affiliates [$..], Media Buyer [$..]
- сколько вакансий требуют русский язык: [N]%

Методика открыта, API без ключа под CC BY 4.0, каждая вакансия ведёт на первоисточник. Выгрузку под любой ваш запрос делаю за день. Просьба одна: ссылка на SpinHire как на источник.

[ИМЯ ОСНОВАТЕЛЯ], SpinHire, hello@spinhire.io

---

## 7. Community answer templates

Rules: answer the actual question first, mention SpinHire once at most, one link maximum, disclose that you run it. Do not post the same text twice on one platform. Each template is under 140 words.

### EN 1: r/Malta, "Moving to Malta, what jobs are there?"

Most non-tourism hiring in Malta is iGaming: online casinos, sportsbooks and the studios and payment companies around them. Roles go well beyond dealers: customer support in a dozen languages, compliance/AML, CRM, affiliate management, data, backend and QA. Entry roles are mostly support and KYC; those hire year-round and often sponsor the work permit.

Practical tips: apply directly on company career pages (most Malta employers use Greenhouse, Workable or Lever), expect a language test if you apply for a language-specific role, and ask about relocation package and the first month of housing, both are common.

Disclosure: I run spinhire.io, a job board for this industry; roughly [X]% of our live listings are in Malta right now, and the market page shows which roles dominate. Happy to answer questions about specific companies.

### EN 2: r/cyprus, "Jobs in Limassol for English speakers?"

Limassol's biggest employers of English-speaking foreigners are forex/fintech and iGaming (betting, casino, game studios, payments). Both hire non-Greek speakers for support, sales, compliance, marketing, product and engineering. Salaries in iGaming are typically above local averages for the same title, and many companies handle the work permit.

Where to look: company career pages first, then LinkedIn with location "Limassol" and keywords like "iGaming", "casino", "sportsbook". Expect a lot of listings to be marked remote or hybrid.

For transparency, I run spinhire.io, a job board for this industry. We publish a public stats page (spinhire.io/market) where you can see the Cyprus share and the most-hired roles this month, which is a decent proxy for what is actually open. No signup needed to browse.

### EN 3: Quora, "How do I get into the iGaming industry?"

Three realistic entry points:

1. Customer support or KYC/verification at an operator. Language skills matter more than experience. Six to twelve months there and you can move into CRM, fraud/payments or compliance.
2. Transfer your existing profession. iGaming hires the same backend developers, QA, data analysts, PPC/SEO specialists, designers and product managers as any tech company. Learn the vocabulary (GGR, RTP, bonus abuse, licences like MGA/UKGC) and apply.
3. Affiliate marketing, if you can run traffic or write.

Where the jobs are: Malta, Cyprus, Gibraltar, Warsaw, Tbilisi, and a large remote share.

I run spinhire.io, a job board for this sector. Our 35 profession cards describe each role, typical requirements and salary bands, which is a good way to see where your background fits before applying.

### EN 4: r/jobs, "Career switch into a well-paid niche?"

One niche that is under-discussed: iGaming (online betting and casino, plus game studios, payment and compliance vendors). It pays above the general market for the same titles, hires a lot of career switchers, and most roles are the ordinary ones: support, CRM, data, QA, backend, marketing, product, compliance.

What to expect: a background check, a short test task for most roles, and a strong preference for candidates who understand the product. Spend a weekend reading about how bonuses, RTP and licences work and you are ahead of most applicants. Downsides: the sector is regulated differently by country, and some people are uncomfortable with gambling as a product. Decide that first.

Disclosure: I run spinhire.io, a job board for the sector, with public salary bands per role if you want to compare against your current pay.

### RU 1: vc.ru, комментарий под постом о релокации / поиске работы за рубежом

Добавлю индустрию, которую в таких обсуждениях обычно пропускают: iGaming (онлайн-казино, беттинг, игровые студии, платёжки). Это один из крупнейших работодателей для русскоязычных на Кипре, Мальте, в Варшаве и Тбилиси, плюс много удалёнки. Роли обычные: разработка, QA, аналитика, маркетинг, саппорт, комплаенс, продукт. Русский язык часто нужен как рабочий, а не как минус.

Что важно знать до отклика: юрисдикция и лицензия компании, B2B это или B2C, есть ли релокационный пакет. Отклики лучше слать напрямую на карьерную страницу, а не через агрегаторы.

Раскрою интерес: я делаю spinhire.io, доску вакансий по этой индустрии. На странице статистики видно, сколько вакансий сейчас в каждом хабе и какие роли нанимают чаще всего.

### RU 2: Пикабу, пост/комментарий в теме про работу за границей

Расскажу про индустрию, о которой мало кто думает при поиске работы за рубежом: iGaming, то есть онлайн-казино, беттинг и всё вокруг них (игровые студии, платежи, партнёрки). В ней тысячи открытых вакансий, значительная часть на Кипре, Мальте, в Варшаве и Тбилиси, и много удалёнки.

Кого берут без опыта в индустрии: саппорт (особенно со вторым языком), KYC/верификация, контент, junior-аналитики. Дальше обычный рост в CRM, антифрод, комплаенс. Разработчиков, тестировщиков, маркетологов и дизайнеров берут как в любом IT.

Из минусов: продукт не всем подходит морально, нужно решить это для себя заранее. Плюс в том, что зарплаты выше средних по тем же должностям.

Для честности: я делаю сайт spinhire.io с вакансиями по этой теме, там же карточки профессий с вилками зарплат.

### RU 3: TG-чат релокантов (Кипр / Мальта / Грузия / Польша)

Кто спрашивал про работу на месте: здесь главный работодатель для приезжих это iGaming (беттинг, казино, игровые студии, платёжки). Берут саппорт, KYC, CRM, антифрод, разработку, QA, аналитику, маркетинг. Русский часто рабочий язык, английский нужен почти везде.

Как искать: карьерные страницы компаний напрямую, LinkedIn по городу, локальные чаты. Спрашивайте про релокационный пакет, оплату жилья на первый месяц и помощь с разрешением на работу. Это стандартная практика, а не наглость.

Я делаю spinhire.io, там вакансии по индустрии собираются с карьерных страниц каждые 6 часов и есть страница со статистикой по городам. Если нужно, подскажу по конкретным компаниям в личке.

---

## 8. Press pitch: quarterly report "iGaming labour market Q3 2026"

Publish the report as a page on spinhire.io/market (permanent URL, e.g. /market/2026-q3) before pitching. Attach a 1-page PDF summary and 3 to 4 PNG charts. Send 7 to 10 days before quarter-end coverage slows down, i.e. first week of October.

### Example headline stats (fill from /market, keep the exact wording pattern)

1. "[N] live iGaming vacancies across [K] companies at the end of Q3 2026, [±X]% quarter on quarter."
2. "[X]% of open roles are fully remote; Malta ([A]%), Cyprus ([B]%) and Poland ([C]%) remain the largest on-site clusters."
3. "The most-hired role in Q3 was [ROLE]; demand for [ROLE 2] grew [Y]% while [ROLE 3] fell [Z]%."
4. "[M] companies posted iGaming vacancies for the first time in Q3, [P]% of them game studios / B2B suppliers."
5. "Median advertised salary band for [ROLE] is [$A–$B]; the widest gap between hubs is [HUB 1] vs [HUB 2] at [D]%."

### EN pitch: iGB, SBC News, EGR, CasinoBeats, Gambling Insider

Subject options:
- Q3 2026 iGaming labour market: [N] open roles, [X]% remote, [ROLE] most hired (data + charts)
- New quarterly report: who is hiring in iGaming, with open data behind every number

Hi [NAME],

SpinHire has published its first quarterly labour-market report for the iGaming industry, covering Q3 2026: https://spinhire.io/market/[2026-q3]

The report is built from the live job index we maintain by crawling 1,000+ employer career pages and ATS feeds every 6 hours. Unlike survey-based salary guides, every number is a count of real postings and can be re-run by anyone through our open API (CC BY 4.0, no key).

Headline findings:
- [STAT 1]
- [STAT 2]
- [STAT 3]
- [STAT 4]
- [STAT 5]

Included: breakdowns by country and hub (Malta, Cyprus, Gibraltar, Poland, Georgia, remote), by role family (tech, product, marketing/affiliates, operations/support, compliance, payments), by seniority, and salary bands for 35 professions. Methodology and limitations are on the page.

I can provide charts in your format, a custom cut for your readership ([e.g. UK-licensed operators only / B2B suppliers only]), or a short comment from [FOUNDER NAME]. If you would like exclusive first publication of one segment, let me know which and I will hold it.

Best,
[FOUNDER NAME]
SpinHire, hello@spinhire.io
https://www.linkedin.com/company/spinhirejob

### RU pitch: Login Casino, Партнеркин

Тема: Отчёт: рынок труда iGaming за Q3 2026: [N] вакансий, [X]% удалёнки, самая востребованная роль [РОЛЬ]

Здравствуйте, [ИМЯ]!

SpinHire опубликовал первый квартальный отчёт по рынку труда индустрии iGaming за третий квартал 2026 года: https://spinhire.io/market/[2026-q3]

Отчёт построен не на опросах, а на живом индексе вакансий: мы каждые 6 часов обходим карьерные страницы и ATS-фиды 1 000+ компаний. Любую цифру можно перепроверить через открытый API (CC BY 4.0, без ключа), каждая запись ведёт на оригинальное объявление.

Главное:
- [ЦИФРА 1]
- [ЦИФРА 2]
- [ЦИФРА 3]
- [ЦИФРА 4]
- [ЦИФРА 5]

Отдельно для вашей аудитории: доля вакансий с требованием русского или украинского языка, разбивка по Кипру, Мальте, Варшаве и Тбилиси, срез по affiliate-сегменту и вилки зарплат по 35 профессиям.

Могу прислать графики в вашем формате, сделать отдельный срез под ваш материал или дать комментарий от [ИМЯ ОСНОВАТЕЛЯ]. Если хотите эксклюзив на какой-то из разделов до общей публикации, скажите какой.

С уважением,
[ИМЯ ОСНОВАТЕЛЯ]
SpinHire, hello@spinhire.io

---

## 9. Account checklist for the owner

Use hello@spinhire.io (or a founder address that forwards to it) for every account, enable 2FA, and store recovery codes. Do the accounts in this order; the first four are prerequisites for the outreach above.

| # | Service | Start here | What to paste from this kit | Notes |
|---|---|---|---|---|
| 1 | Bing Webmaster Tools | https://www.bing.com/webmasters | nothing; add site spinhire.io, verify via DNS or the existing GSC import, submit https://spinhire.io/sitemap.xml | "Import from Google Search Console" skips verification. Also feeds Copilot / DuckDuckGo |
| 2 | Yandex Webmaster | https://webmaster.yandex.ru/ | nothing; add spinhire.io, verify via meta tag or DNS, submit sitemap, set region | Needed for the Russian-first audience; also submit the Turbo/IndexNow key if you use it |
| 3 | LinkedIn company page | https://www.linkedin.com/company/spinhirejob/admin/ | Section 4 (About EN + RU), specialties list | Page already exists; add the launch year 2026 and website |
| 4 | Product Hunt | https://www.producthunt.com/ (sign up), then https://www.producthunt.com/posts/new | Section 3: tagline, description, topics, maker comment; schedule for 00:01 PT on a Tuesday to Thursday | Create the maker account at least 2 weeks before launch and upvote/comment on other products first, new accounts get down-weighted |
| 5 | Crunchbase | https://www.crunchbase.com/register, then https://www.crunchbase.com/add-new | Section 2 in full | Free contributor account is enough; profile goes live after moderation (1 to 3 days) |
| 6 | Wikidata | https://www.wikidata.org/wiki/Special:CreateAccount, then https://www.wikidata.org/wiki/Special:NewItem | Section 1: labels, descriptions, aliases, statements table | Wait for at least one independent mention before creating; add it as a reference |
| 7 | Reddit | https://www.reddit.com/register/ | Section 7 EN templates, adapted per thread | Age the account: 2 to 3 weeks of normal comments before posting anything with a link; check each subreddit's self-promotion rule |
| 8 | Kaggle | https://www.kaggle.com/account/login?phase=startRegisterTab, then https://www.kaggle.com/datasets/new | Dataset title "iGaming Job Postings (SpinHire open API)", license CC BY 4.0, description from the fact sheet, link to https://spinhire.io/api/jobs and /market methodology | Upload a monthly CSV snapshot of the API; add a short notebook that loads it. Update on a schedule so the dataset stays "active" |
| 9 | Hugging Face | https://huggingface.co/join, then https://huggingface.co/new-dataset | Same dataset card as Kaggle; add a dataset card README with fields, license CC BY 4.0, source link, refresh cadence | Use an organization account named "spinhire"; tag: tabular, text, en, ru, jobs |

After each account is live, add its URL to the fact sheet at the top and to the Wikidata statements (P2002, P2013, etc.) so the identifiers stay consistent everywhere.
