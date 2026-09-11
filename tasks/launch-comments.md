# Банк комментариев к запуску

Всё, что придётся писать руками в дни запуска: прогрев аккаунта, первый комментарий мейкера,
ответы на вопросы и на скепсис. Тексты — на английском, пояснения — по-русски.

Цифры в примерах отражают индекс на 10 сентября 2026 (5 558 вакансий, 389 компаний, 847 новых
за неделю, зарплата раскрыта у 9%). Перед каждой подачей прогоняйте `python3 scripts/launch_facts.py`
и подставляйте свежие: расхождение в цифрах на PH и на сайте заметят в первый же час.

Общие правила, которые дороже любого текста:

- **Никогда не просить голоса.** Ни «upvote», ни «поддержите», ни намёками. PH за это снимает продукт.
- **Не копипастить.** Один и тот же комментарий под пятью запусками виден насквозь и работает в минус.
- **Не спорить с критикой.** Согласиться с фактом, показать, что делаете дальше. Спор в треде
  читают сотни человек, и выигрывает не тот, кто прав, а тот, кто спокоен.
- **Отвечать быстро.** Первые 15 минут после комментария — главный рычаг ранжирования на PH.
- **Не обещать того, чего нет.** «Скоро будет» без срока — нормально, «мы это уже умеем» про
  несуществующее — нет: проверят при вас же, API открыт.

---

## 1. Прогрев: комментарии к чужим запускам

Две-три недели до запуска, 1–2 комментария в день. Смысл не в количестве, а в том, чтобы к вашему
дню аккаунт не выглядел одноразовым, а несколько мейкеров вас узнавали.

**Кого комментировать:** продукты про hiring, HR-tech, job boards, открытые данные, API и
инструменты для агентов. Там же сидит ваша аудитория и будущие голосующие.

**Комментарий готов, если** в нём есть хотя бы одно из: конкретная деталь из продукта (значит, вы
его открыли), вопрос, на который мейкеру интересно отвечать, или ваш опыт по теме. Если нет
ничего — не отправляйте, это шум.

### 1.1 Шесть рабочих архетипов

**a) Заметили конкретное решение** — самый сильный комментарий, мейкеру приятно, что открыли продукт.

```
The [конкретная деталь] is the part I'd have gotten wrong. Most tools in this space [что делают
остальные], and you went the other way. Was that a deliberate call or something you landed on
after users complained?
```

**b) Вопрос из своего опыта** — показывает, что вы из индустрии, а не мимо проходили.

```
We run a job index in a niche vertical, and the thing that kills us is [конкретная проблема].
How do you handle it — [вариант A] or [вариант B]?
```

**c) Про данные и источники** — попадает в тех, кто строит на данных.

```
Where does the data come from, and how often does it refresh? Asking because the answer usually
decides whether a tool like this is a snapshot or something you can build on.
```

**d) Полезное возражение** — рискованно, но запоминается. Только если возражение честное.

```
Looks solid. One thing I'd push back on: [возражение] — in our experience [почему]. Curious
whether you've seen that play out differently.
```

**e) Короткое по делу** — когда добавить нечего, но продукт правда хорош. Три строки, не больше.

```
Clean execution. The [деталь] alone would have saved me a week last year.
```

**f) Ответ другому комментатору** — весит не меньше, чем комментарий мейкеру, и заводит знакомства.

```
Same experience here — [ваш факт]. What worked for us was [что именно], though the trade-off was
[минус].
```

### 1.2 Чего в прогреве не делать

- Не оставлять ссылку на SpinHire в чужих тредах. Это читается как реклама и запоминается плохо.
- Не писать «great launch, congrats 🎉» — такие комментарии PH не учитывает, а мейкеры не читают.
- Не комментировать 20 продуктов за вечер: всплеск активности перед своим запуском виден в профиле.

---

## 2. День запуска: ответы на комментарии

Первый комментарий мейкера — в основном плейбуке, раздел 2.5. Ниже — то, что спросят после него.

### 2.1 Про категорию (спросят обязательно, чаще всего первым)

**«Это же гемблинг? PH такое не пускает.»**

```
Fair question, and the honest answer is: SpinHire is an employment platform, not a gambling
service. There is no betting, no money games, no deposits anywhere on the site. We index vacancies
at licensed operators, game studios and payment providers — the same way a fintech job board
indexes banks. The people we serve are support agents, compliance officers, analysts and
developers who happen to work in a regulated industry.
```

**«Вы помогаете индустрии, которая вредит людям.»** — не оправдываться и не спорить с оценкой.

```
I won't argue with the position — it's a legitimate one. What I'd say is that ~200k people work
in this industry legally today, and a large part of the roles we list are the ones that keep it
regulated: KYC, AML, compliance, responsible gaming. Those people deserve a job market with
public salary data as much as anyone. If the industry itself isn't for you, that's completely
fair, and this product probably isn't either.
```

**«Почему на сайте мини-игры?»**

```
It's a small easter-egg section with virtual points — no stakes, no payouts, no money in or out.
It's excluded from the sitemap and from anything we submit. If it reads as confusing, that's
useful feedback and I'd rather move it than explain it every time.
```

### 2.2 Про данные

**«Откуда вакансии?»**

```
Employer career pages and ATS feeds, crawled every 6 hours. Every card links back to the original
posting, and when a job disappears at the source it's archived automatically, so the index is live
rather than cumulative. Employers can also post directly — those go through human moderation and
are only published with a salary range.
```

**«Насколько данные точные?»**

```
The methodology is public at /en/market: daily snapshots are never recalculated, every month has a
permanent URL, and the raw index is at /en/api/jobs with no key. Don't take my word for it —
the numbers on the landing page and the API are the same query.
```

**«Сколько вакансий с зарплатами?»** — цифра неудобная, называть её первым, не дожидаясь, пока найдут.

```
About 9% of the index discloses a range, and I'd rather say that out loud than round it up. That's
the industry, not a gap in our parsing: most operators hide the band. The part we control is our
own posting flow — a job posted directly on SpinHire is published only with a salary range.
```

**«Дублируются ли вакансии между компаниями?»**

```
Dedup runs on title + company + location, and re-posts of the same role update the existing record
instead of creating a new one. Aggregator noise is the harder case: if you spot a duplicate pair,
send me the two ids and I'll look at why they didn't collapse.
```

### 2.3 Про бизнес-модель

**«Как вы зарабатываете, если API открыт?»**

```
Candidates are free forever. Employers pay for posting (from €49), for promotion, and for
unlocking contacts in the CV database. The open index is not the product — the hiring workflow on
top of it is. Nobody has ever paid a job board for the right to read a list of vacancies.
```

**«Не боитесь, что конкурент выкачает базу?»**

```
They can, and the licence explicitly allows it — CC BY 4.0, attribution to spinhire.io. A copy of
the index without the refresh loop, the employer relationships and the moderation is a stale list
within a week. The moat is the pipeline, not the rows.
```

**«Есть ли rate limits?»**

```
No key and no hard limit today — be reasonable and we'll keep it that way. If you're pulling the
whole index regularly, the market CSV and the monthly aggregates are cheaper for both of us, and
I'm happy to set up something better if you tell me what you're building.
```

### 2.4 Про конкурентов

**«Чем вы лучше LinkedIn / Indeed?»**

```
We don't compete on volume — we'd lose. We compete on fields. Vertical (casino / betting / studio /
affiliate / payments), licence jurisdiction, working languages, relocation support and crypto pay
are structured filters here, not text buried in a description. And the industry's own hiring data
is public, which is not something a general board has any reason to do.
```

**«Есть же iGamingCareers / Casino Jobs.»**

```
There are, and they're real competitors. The difference is what's open: their index sits behind a
login or a paid employer account, and none of them publish the market data. Ours is an API with no
key, monthly aggregates with permanent URLs, and an MCP server so agents can query it directly.
```

### 2.5 Технические (это Hacker News-аудитория, отвечать точно)

**«Что за MCP-сервер?»**

```
A remote MCP server over Streamable HTTP at https://spinhire.io/mcp, no auth. Tools: search_jobs,
get_job, market_stats, market_history, list_professions, get_profession, get_company. Point Claude
or any MCP client at it and you can ask "senior payments roles in Malta with a salary band" without
scraping anything.
```

**«Какой стек?»**

```
FastAPI + SQLite, server-rendered HTML, no SPA. The whole thing runs on one small VPS. The crawler
is plain Python on a 6-hour schedule. Boring by design: the interesting part is the data, and I
didn't want an infrastructure bill to be the reason it stops being free.
```

**«Почему 12 языков на джоб-борде?»**

```
Because this workforce is genuinely multilingual: a support agent in Limassol is hired for
Portuguese, a VIP manager in Warsaw for German. Interface language and job language are different
filters — you can browse in Greek and filter for roles requiring Ukrainian.
```

**«Markdown-зеркала и llms.txt — зачем?»**

```
Every page has a .md twin and there's an llms.txt index, so a model reading the site gets clean
text instead of a parsed layout. It costs nothing to serve and it's how a growing share of traffic
arrives.
```

### 2.6 Просьбы и фичи

**«Сделайте email-алерты / RSS / фильтр X.»**

```
RSS and per-filter alerts are the next thing on the list — the index already updates every 6 hours,
so it's plumbing rather than a rewrite. If you tell me the exact filter combination you'd subscribe
to, I'll build that one first.
```

**«Можно ваши данные в моём проекте?»**

```
Yes — CC BY 4.0, attribution to spinhire.io, no key needed. If you build something, post it here
or email hello@spinhire.io: I'd rather link to it than compete with it.
```

### 2.7 Тон в мелочах

- На «congrats» — благодарить конкретно, а не штампом: *Thanks! The market data page is the part
  I'd love feedback on — that's where I'm least sure.*
- На баг — благодарить и чинить в тот же день: *Reproduced, thanks. Fixing today, I'll reply here
  when it's live.* И правда ответить, когда выкатили: это лучший вид активности в треде.
- На вопрос, на который нет ответа: *Don't know yet — I'll find out and come back to you here.*
  Это сильнее любой импровизации.

### 2.8 Итог дня (публиковать в своём же треде вечером)

```
12 hours in. What I've learned from this thread:

• [самый частый вопрос] came up [N] times — I've rewritten the landing copy to answer it up front.
• [баг] was real and is fixed as of an hour ago, thanks [@name].
• [запрошенная фича] is now the top item on the list.

The index refreshed twice while we were talking: [N] live jobs from [N] companies as of now.
Thanks for the questions — they were sharper than any user interview I've run.
```

---

## 3. Show HN: другая тональность

HN не про продукт, а про то, как он устроен. Маркетинговые формулировки там режут первыми.

**В ответ на «why is this on HN?»**

```
Because the part I think is interesting isn't the job board — it's that the whole index is a public
API with no key and monthly aggregates that never get recalculated. Nobody publishes hiring data
for this industry, so I did.
```

**В ответ на «gambling is harmful»** — короче, чем на PH; на HN длинные оправдания читают как слабость.

```
Understood. It's a legal, regulated industry that employs a lot of people, and this is a job board
for them, not a gambling product. If that distinction doesn't work for you, fair enough.
```

**В ответ на технический разбор** — соглашаться с конкретикой, приводить цифры.

```
You're right about [что именно]. Current numbers: [цифра]. The reason it's built this way is
[причина], and the failure mode you're describing is [что происходит]. If you've solved this at a
larger scale, I'd genuinely like to hear how.
```

---

## 4. Reddit и Indie Hackers

**Reddit.** Читают правила сабреддита до поста; в r/iGaming и r/gambling ссылка на свой продукт
часто запрещена прямо. Формат, который проходит: пост с данными, ссылка — в комментарии.

```
I've been indexing iGaming job postings for a while and pulled the September numbers: [N] open
roles at [N] companies, [топ-3 страны], and only 9% disclose a salary range. Happy to pull any cut
of this that people want — data's open.
```

**Indie Hackers.** Там ценят цифры бизнеса, а не продукт. Работает честный пост про экономику:
сколько стоит краулинг, сколько платят работодатели, где ломалась юнит-экономика.

---

## 5. Если модерация PH спросит про категорию

Отвечать в личку модератору, коротко и по делу:

```
SpinHire is a job board — an employment platform for the iGaming industry (online casinos,
sportsbooks, game studios, affiliates, payment providers). We do not operate any gambling service:
no betting, no money games, no deposits or withdrawals anywhere on the site. Every listing links to
a vacancy at a licensed company. The product is closer to a fintech job board than to a casino.
Happy to answer anything else — hello@spinhire.io.
```
