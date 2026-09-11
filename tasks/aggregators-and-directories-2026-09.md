# Дистрибуция: агрегаторы вакансий и каталоги джоб-бордов

Дата: 11 сентября 2026. Четыре канала из разбора «где ещё можно разместиться».
Код уже готов и задеплоен — здесь только то, что требует твоего аккаунта и клика.

## Что сделано в коде

Два фида, которых раньше не было (`/feed.xml`, `/jobs.xml` отдавали 404):

| URL | Формат | Для кого |
|---|---|---|
| `https://spinhire.io/feed/jobs.xml` | Indeed XML | агрегаторы: Jooble, Adzuna, Talent.com, Jobsora, Jora, WhatJobs |
| `https://spinhire.io/feed/rss.xml` | RSS 2.0 | каталоги джоб-бордов, читалки, боты |

Параметры: `?src=<партнёр>` (проставляет utm_source — видно, кто сколько привёл),
`?lang=en|ru|de|…` (на какую языковую версию вести), `?limit=N`.

Что в фид **не** попадает, чтобы его не отклонили целиком:
- вакансии с описанием короче 160 символов (у агрегаторов это «тонкий контент»);
- вакансии, у которых не определились ни страна, ни город, ни удалёнка.

На проде в фиде **4708 вакансий** из 5582 живых, 429 с вилкой; 3,9 МБ в gzip, отдаётся за ~3,5 с.
Дублей URL нет, пустых `<title>`/`<url>`/`<company>`/`<description>` нет.

## A. Агрегаторы вакансий

Отдаём каждому свою ссылку — тогда в GA видно источник и одного можно отключить,
не трогая остальных.

| Партнёр | Ссылка для заявки | Что вставить | Условия |
|---|---|---|---|
| **Jooble** | https://jooble.org/partner/ppc — заявка партнёра; если форма не подойдёт, тикет на https://help.jooble.org | `https://spinhire.io/feed/jobs.xml?src=jooble&lang=en` | бесплатное органическое размещение + опционально PPC; 64 страны |
| **Adzuna** | https://www.adzuna.com/hire/partners/ | `https://spinhire.io/feed/jobs.xml?src=adzuna&lang=en` | органические вакансии из XML рекламируют бесплатно |
| **Talent.com** | заявка паблишера на talent.com | `…?src=talent&lang=en` | бесплатно + PPC |
| **Jobsora / Jora / WhatJobs** | заявка паблишера на сайте каждого | `…?src=jobsora` и т. д. | бесплатно |
| **Careerjet** | https://www.careerjet.com/recruiter | `…?src=careerjet&lang=en` | ⚠️ по одним данным — $0,10 за клик и $100 минимум, по другим есть органика. Проверять только заявкой |

Порядок: Jooble и Adzuna первыми — по ним условия бесплатного размещения подтверждены.
Careerjet последним, чтобы не упереться в оплату на старте.

В тексте заявки полезно указать: 5582 живые вакансии, 394 компании, обновление
каждые 6 часов, исчезнувшие у источника архивируются автоматически, 11 языковых версий.

## B. JobBoardSearch — подать бесплатно (15 минут)

https://jobboardsearch.com/add-board · DR 44 · 1 253 994 просмотра за 30 дней ·
сабреддит 27 119 · рассылка 15 981 · TG-группа 6 005 · в каталоге 843 борда.

Базовый листинг с логотипом бесплатный. Платные апгрейды ($19–$499) дают
do-follow-ссылку, подсветку и публикацию за 48 часов вместо очереди.

Готовые значения для формы:

- **Name:** SpinHire
- **URL:** `https://spinhire.io/en` (аудитория каталога англоязычная; корень отдаёт русскую версию)
- **RSS / API feed:** `https://spinhire.io/feed/rss.xml?src=jobboardsearch&lang=en`
  — именно он пускает наши вакансии в их Google for Jobs-сеть, в TG и в рассылку
- **Tagline:** `iGaming jobs across Europe and remote — casino, betting, game studios, affiliates`
- **Description:**
  > SpinHire is a job board for the iGaming industry: online casino, sports betting,
  > game studios, affiliates, payments and compliance roles across Europe and remote.
  > Its own index of vacancies is refreshed every 6 hours from employer career pages,
  > ATS feeds and public channels; jobs that disappear at the source are archived
  > automatically. Eleven language versions, with a focus on relocation (Malta, Cyprus,
  > Warsaw, Tbilisi) and remote work. Also publishes a directory of 35 iGaming
  > professions with salary bands and open market statistics with a citation line.
- **Launch date:** 14 August 2026
- **Job board software:** Custom / self-built (FastAPI)
- **Feature tags:** `iGaming Industry, Remote Jobs, Relocation, Multilingual, Europe`
  — тег «Salary required» не ставить: вилка есть только у 9 % вакансий, за такое снимают с листинга

⚠️ Не подтверждено, что каталог принимает гемблинг-тематику. Подача бесплатная,
так что цена проверки — 15 минут.

## C. Directory Submissions — 100+ каталогов, $199 разово

https://jobboardsearch.com/directory-submissions — они сами выбирают каталоги под нишу
и по DA, размещают только с do-follow-ссылками.

Покупать **после** пункта B: если выяснится, что гемблинг-борды в каталоги не берут,
$199 сэкономлены.

## D. Telegram — @bettingjob_price

Канал платного размещения вакансий при @betting_job (крупнейший русскоязычный канал
вакансий в беттинге/гемблинге). Аудитория ровно наша.

Черновик первого сообщения админу:

> Привет. Я SpinHire (spinhire.io) — джоб-борд iGaming: 5500+ живых вакансий от 394 компаний,
> русский и ещё 10 языков, обновление каждые 6 часов.
> Интересует размещение у вас. Два варианта, оба открыт обсуждать:
> 1) разовые посты — подборка вакансий недели со ссылкой на нас;
> 2) постоянное сотрудничество — мы отдаём вам готовые карточки вакансий, вы ставите их в канал.
> Подскажите прайс и формат, который вам удобнее.

Не начинать с просьбы о бесплатном кросс-промо: у канала это основной заработок.

## Порядок

1. Задеплоить фиды (автопулл подтянет сам за 2 минуты) и проверить, что открываются.
2. Подать на JobBoardSearch — бесплатно, сразу.
3. Заявки в Jooble и Adzuna.
4. Написать в @bettingjob_price.
5. Через неделю посмотреть в аналитике utm_source=jooble / adzuna / jobboardsearch.
6. Если каталоги берут гемблинг — купить Directory Submissions.
