# Система публикаций SpinHire

Обновлено 2026-09-09. Реестр: `/admin/publications` (модуль `server/publications.py`, таблица `publications`).
Статусы: **в плане → создано → запланировано → опубликовано / ошибка / снято**.

## Площадки

| Площадка | Язык | Что публикуем | Ритм | Как | Статус |
|---|---|---|---|---|---|
| YouTube @spinhire_ru | RU | Shorts: вакансии дня, зарплаты, профессии, цифра дня; длинный ролик по воскресеньям | 3/день + 1/нед | `video/pipeline` → private + publishAt; лог `data/youtube-posts.json` → реестр | работает с 09.09 |
| Telegram @spinhire_ru | RU | дайджест «самые дорогие» 10:00, горячие от ~$5k до 3/день | ежедневно | `server/tgpost.py` на проде, таблицы `tg_*` → реестр | работает с 21.08 |
| Telegram @spinhire | EN | то же, только латиница-вакансии | ежедневно | то же | работает с 21.08 |
| Reddit | EN | 2–3 поста/нед: зарплатный отчёт, «hiring this week» подборка, разбор профессии; без прямой рекламы | пн/ср/пт | `scripts/reddit_post.py` через официальный API (script-приложение, ключи в `~/.spinhire/reddit.env`); браузерная сессия — запасной путь | ждёт ключей API |
| LinkedIn /company/spinhirejob | EN+RU | зарплатные отчёты, карточки вакансий, статьи блога | 3/нед | позже: API Community Management требует одобрения; старт через сохранённую сессию как Reddit | не начато |
| Блог spinhire.io | RU (+11 языков) | статья в день | ежедневно | плановая задача spinhire-daily-blog; `ARTICLE_FILES` → реестр (todo) | работает |

## Reddit: как публиковать, чтобы не забанили

- API закрыт (проверено 09.09.2026): на https://www.reddit.com/prefs/apps форма «create app» после капчи не создаёт приложение, а отсылает к Responsible Builder Policy. Новый доступ выдают только по заявке через support-форму (ticket_form_id=14868593862164, ссылка в /wiki/api), рассмотрение ручное и небыстрое; developers.reddit.com/app-registration — только для уже существующих приложений. Заявку подать стоит, но план на неё не опирается. Когда одобрят: ключи в `~/.spinhire/reddit.env` (chmod 600), 2FA у аккаунта выключить, `reddit_post.py` сам переключится на API.
- Рабочий путь сейчас — обычный Chrome владельца с живой сессией (аккаунт u/FluMuffiny): Claude через расширение Claude in Chrome открывает `r/<sub>/submit`, вставляет заголовок и текст из `content/`, владелец нажимает Post. Затем строка в реестр через `POST /api/publications/upsert`. Это ручной ритм 2–3 раза в неделю, автопостинг по cron невозможен, пока нет API.
- Браузерная сессия (Playwright + Google Chrome) оставлена как запасной путь, но 09.09 выяснилось: Reddit отвечает «Invalid email or password» и «Error: TY5MSX» на любой вход из окна, запущенного Playwright (и новая, и старая форма old.reddit). Скрывать признаки автоматизации не стали — это обход защиты площадки.
- Сабреддиты и правила (проверить перед первым постом, у всех есть анти-self-promo):
  - r/igaming — индустриальный, разрешены обсуждения найма и зарплат; ссылки на джоб-борд только в тексте, не как link-post.
  - r/gamblingindustry, r/OnlineGambling (осторожно, много спама → строгие моды).
  - r/cscareerquestions / r/remotework / r/digitalnomad — только контент о карьере, ссылка одна и в конце.
  - r/forhire — формат «[Hiring]» строго по шаблону сабреддита, 1 пост/неделя.
- Тон: разбор с цифрами (источник — spinhire.io/api/market-stats), без «мы лучший борд». Ссылка на spinhire.io — одна, с utm_source=reddit.
- Ритм: не больше одного поста в сабреддит в неделю, аккаунт должен иметь карму и комментарии; первые 2 недели — комментарии и ответы, потом посты.
- Реестр: каждая попытка пишется в `data/reddit-posts.json` и в `/api/publications/upsert` со статусом published/error.

## Как реестр наполняется

- Telegram и YouTube синхронизируются автоматически при открытии страницы (`sync_all`).
- Внешние скрипты (Reddit, облачные routines) шлют `POST /api/publications/upsert` с заголовком `X-Publish-Key: $SPINHIRE_PUBLISH_KEY`.
- План на неделю: `GET /api/publications/plan` — облачные агенты берут отсюда, что уже занято.
- Ручные строки плана и смена статусов — прямо на странице.

## Что делать дальше

1. Прод: задать `SPINHIRE_PUBLISH_KEY` в `/etc/systemd/system/spinhire.service.d/telegram.conf` и перезапустить (без ключа страница работает, API upsert закрыт).
2. Reddit: подать заявку на API через support-форму; до одобрения постить через Chrome владельца (Claude in Chrome), первые две недели — комментарии, потом посты по плану пн/ср/пт.
3. LinkedIn: после Reddit, тем же способом (storage_state), плюс заявка на Community Management API.
4. Блог: писать в реестр из плановой задачи (status published + URL) — одна строка в промпте задачи.
