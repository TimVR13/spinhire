# YouTube Shorts SpinHire: 3 ролика в день, полностью автоматически

Дата: 2026-09-08. Канал RU, хэндл @spinhire_ru. Все ролики 1080×1920, 20–45 с, субтитры вшиты, озвучка ИИ.

## 1. Сетка форматов (разнообразие через ротацию)

Три слота в день, у каждого своя роль. Форматы чередуются по календарю, один и тот же формат не повторяется чаще 2 раз в неделю в одном слоте.

| Слот | Роль | Форматы в ротации | Источник данных |
|---|---|---|---|
| 09:00 | Вакансии | «3 горячих вакансии дня» · «Топ-5 недели» (пн) · «Удалёнка дня» · «Вакансия с самой большой вилкой» | crawler → Job (новые за 24 ч, salary ≥ $4k) |
| 14:00 | Знания | «Сколько платят: {профессия}» (столбики по регионам) · «Профессия за 30 секунд» · «Правда или миф» (квиз с паузой) · «Цифра дня» (рынок: +N вакансий, % remote) | professions.json, market-snapshots.json, salary.py |
| 19:00 | Карьера | «Без опыта: 3 шага в {профессию}» · «Релокация: Кипр / Мальта / Рига / Тбилиси» · «Компания недели» (офисы, роли, вилки) · «3 вопроса с собеса на {роль}» | blog-queue + статьи блога, companies.json, casino-operators.json |

Разнообразие визуала: 4 темы оформления (тёмный неон, «стол казино» с монетой, «фишки», «рулетка/кости») × 3 ритма (быстрый лист, одна крупная цифра, диалог-квиз). Фон и музыка выбираются из пула по хэшу даты, чтобы соседние ролики не совпадали. История выпусков в `data/youtube-posts.json`: профессия/компания не повторяется 14 дней, формат в слоте не чаще 2 раз в неделю.

Хук в первые 2 секунды всегда цифра или провокация: «€7 670 в месяц за SRE в Риге», «В iGaming берут без английского?». Финал: «Все вакансии на spinhire.io» + стрелка на ссылку в описании.

## 2. Конвейер

```
cron (GitHub Actions, 3 раза в день)
  → planner.py: выбирает формат по календарю и истории, тянет данные из spinhire.db/JSON
  → writer: Claude API пишет сценарий 60–90 слов + заголовок + описание + теги (промпт с фактами, без выдумок)
  → tts: Google Cloud Text-to-Speech (ru-RU Chirp3-HD) → voice.mp3 + тайминги слов для субтитров
  → remotion render <Composition> --props → out/YYYY-MM-DD-slot.mp4
  → uploader.py: YouTube Data API videos.insert (privacyStatus=private, publishAt=слот) + thumbnails
  → tgpost: кросс-пост в @spinhire_ru
  → лог в data/youtube-posts.json, коммит в repo
```

Где рендерить: GitHub Actions (ubuntu, Chrome headless для Remotion). Один рендер 3–5 мин, 3 в день ≈ 15 мин/день ≈ 450 мин/мес, укладывается в бесплатные 2000. Прод-сервер (4 ГБ, общий) не подходит. Мак как запасной вариант через launchd.

Что делаю я: 4 новые композиции Remotion (Salary, Profession, Quiz, Company), planner/writer/tts/uploader на Python, workflow `.github/workflows/shorts.yml`, ротация музыки и фонов, шаблоны заголовков.

## 3. Что регистрируешь ты (по шагам)

### A. Google Cloud + YouTube Data API (30 минут)
1. https://console.cloud.google.com → создать проект «SpinHire YouTube».
2. APIs & Services → Library → включить **YouTube Data API v3** и **Cloud Text-to-Speech API**.
3. APIs & Services → OAuth consent screen → External. Название SpinHire, support email твой, домен spinhire.io. Scopes: `https://www.googleapis.com/auth/youtube.upload` и `https://www.googleapis.com/auth/youtube`. Test users: твой Google-аккаунт (тот, где канал).
4. Там же переключить **Publishing status → In production**. Без этого refresh-токен умирает через 7 дней и автоматика ломается. Появится предупреждение «unverified app», для собственного использования это нормально.
5. Credentials → Create credentials → **OAuth client ID → Desktop app** → скачать JSON. Положи в `~/.spinhire/yt/client_secret.json` (не в репо).
6. Credentials → Create credentials → **Service account** → ключ JSON → `~/.spinhire/yt/tts-sa.json`. Он нужен только для Text-to-Speech. Для YouTube сервисные аккаунты НЕ работают: у них нет канала, загрузка идёт только через OAuth от твоего аккаунта.
7. Одноразовое согласие: я запускаю скрипт, ты открываешь ссылку, входишь аккаунтом канала, жмёшь «Разрешить», вставляешь код. Получаем refresh_token, дальше всё без тебя.

### B. Аудит API — не нужен
Проверено 08.09.2026: тестовый ролик, загруженный через API, переключается private → unlisted без блокировки. Проект quantium2 уже публиковал видео через API без аудита. Форму аудита не подаём; вернуться к ней только если YouTube начнёт ставить «Locked as private».

### C. YouTube Studio
1. Studio → Настройки → Канал → Дополнительные функции: подтвердить телефон (нужно для миниатюр и длинных видео).
2. Studio → Аудиотека: скачать 6–8 треков (electronic / hip-hop, без атрибуции) в `video/public/audio/`. Через API библиотека недоступна, только вручную.
3. Загрузить шапку и аватар, описание из `assets/brand/youtube/channel-ru.md`.

### D. Ключи
- `ANTHROPIC_API_KEY` для сценариев (если у блог-пайплайна уже есть, переиспользуем).
- Токен бота @postingspin_bot уже есть, для кросс-поста.
- Всё кладём в GitHub → Settings → Secrets → Actions: `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`, `GOOGLE_TTS_SA`, `ANTHROPIC_API_KEY`, `TG_BOT_TOKEN`.

Опционально: ElevenLabs (Creator, $22/мес, 100k символов) если голос Google покажется плоским. Google TTS бесплатен до 1 млн символов в месяц, нам нужно ~60k.

## 4. Порядок запуска
1. День 1: ты делаешь A, B, C. Я начинаю композиции и пайплайн.
2. День 2–3: первые 3 ролика уходят как private, ты смотришь в Studio и публикуешь руками, правим тон.
3. После проверки первых роликов: включаю `privacyStatus=public` через `publishAt`, полный автомат, ты только смотришь отчёт в TG раз в день.
