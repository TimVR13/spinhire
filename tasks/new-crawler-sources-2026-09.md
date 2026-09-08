# Новые источники вакансий для краулера — проверка ATS-API (2026-09-08)

Все числа ниже — результат реальных HTTP-запросов к публичным API 8 сентября 2026 (UA `SpinHireBot/1.0`, паузы 0,35–1,8 с между запросами к одному хосту). Проверено ~620 слагов × 9 ATS (≈7 000 запросов) + сканирование карьерных страниц ~300 доменов на предмет встроенного ATS. В таблицы попали только компании, у которых API отдал ≥1 живую вакансию и принадлежность к iGaming подтверждена по локациям/ссылкам (коллизии слагов вынесены отдельно).

Что сейчас умеет `server/crawler.py`: **Greenhouse** (`crawl_greenhouse`), **Lever** (`crawl_lever`, словарь пуст), **SmartRecruiters** (`crawl_smartrecruiters`), **BambooHR** (`crawl_bamboohr`), WordPress REST (только SOFTSWISS), JSON-LD/sitemap. Адаптеров для **Workable, Ashby, Teamtailor, Recruitee, Personio нет** — для них ниже отдельная таблица и черновики функций.

Важно про регион Greenhouse: борды `job-boards.eu.greenhouse.io/<slug>` (Superbet, Kambi, Soft2Bet, Optimove, TrueLayer, Ela Games) отдаются тем же `boards-api.greenhouse.io` — отдельный EU-хост не нужен (проверено).

---

## 1. Проверено и работает — ATS уже поддерживается краулером (34 компании)

Зарплаты: Greenhouse/SmartRecruiters/BambooHR вилку в API не отдают (как и у текущих бордов — `salary: "по запросу"`); Lever отдаёт `salaryRange` только если компания заполнила — у найденных пусто. Локации есть везде. «В БД» — сколько вакансий этой компании уже лежит у нас через igamingcareers/discovery (дедуп по `(source, ext_id)` их не склеит — при подключении стоит гасить дубли по URL/названию или отключать компанию в IGC-фильтре).

### Greenhouse — `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`

| slug | Компания | Вакансий | Зарплата | Пример названий | В БД | Заметки |
|---|---|---|---|---|---|---|
| `super` | Superbet Group | **178** | нет | AI Accelerator – Commercial; AI Automation Engineer | 0 | Крупнейшая находка. RO/PL/BR/BE, много IT (Бухарест, Варшава, Загреб). Слаг нестандартный — найден через embed на superbetgroup.com |
| `fanduel` | FanDuel (Flutter US) | 86 | нет | Acquisition Strategy Manager; Acquisition Strategy Sr Associate | 78 (IGC) | США; для RU-аудитории мало, но фид чистый |
| `sportygroup` | Sporty Group (SportyBet) | 41 | нет | Analytics Implementation Consultant; Audio Operator | 111 (IGC) | Много remote-Europe, Болгария |
| `penninteractive` | Penn Interactive (theScore / ESPN Bet) | 38 | нет | Ad Operations Specialist; CX Manager, AI Optimization | 24 (IGC, как Penn Entertainment) | США/Канада |
| `easygo` | Stake.com / Easygo | 33 | нет | Backend Engineer – Engine; CRM Specialist | 28 (IGC) | Мельбурн + remote; крипто-казино №1. Вторая часть вакансий Stake — на Breezy `stake.breezy.hr` (не поддержан) |
| `prizepicks` | PrizePicks | 29 | нет | BI Analyst – Game Operations; Board Software Engineer III | 0 | DFS/предикшн-маркет, США |
| `rushstreetinteractive` | Rush Street Interactive (BetRivers) | 21 | нет | Affiliate Manager; Affiliate Manager | 25 (IGC) | США + Колумбия + Европа (Эстония, Мальта) |
| `optimove` | Optimove | 15 | нет | Account Executive; CRM Associate | 0 | B2B CRM-платформа, основная клиентура — iGaming; Tel Aviv/London/NY |
| `soft2bet` | Soft2Bet | 8 | нет | Affiliate Manager; CRM Manager | 8 (IGC) | Мальта/Кипр/Болгария |
| `kambi` | Kambi | 6 | нет | Director of Product – Engagement and Retention; Linux Platform Engineer | 8 (IGC) | Стокгольм/Лондон/Бухарест |
| `elagames` | Ela Games | 4 | нет | JavaScript/TypeScript Game Developer (Warsaw / Lisbon); CEO | 0 | Студия слотов, ES/PL/PT |
| `truelayer` | TrueLayer | 2 | нет | Customer Success Manager – iGaming; Head of Compliance | 0 | Open-banking платежи; 1 из 2 вакансий явно iGaming. Мало, но релевантно |

### SmartRecruiters — `https://api.smartrecruiters.com/v1/companies/{id}/postings?limit=100`

| id | Компания | Вакансий (`totalFound`) | Зарплата | Пример названий | В БД | Заметки |
|---|---|---|---|---|---|---|
| `Entain` | Entain (Ladbrokes, bwin, Coral, PartyPoker) | **291** | нет | Director of Performance Marketing Analytics; Retail Customer Service | 5 (dev.bg) | Много ритейла (UK shops) — нужен фильтр `job_is_irrelevant` по «Retail», «Shop», «Cashier». Хабы: Лондон, Гибралтар, София, Вена, Хайдарабад |
| `tipico` | Tipico | 159 | нет | Legal Assistant – Deutschsprachig; CRM Campaign Manager iGaming | 0 | Мальта/Карлсруэ/Гибралтар, много немецкоязычного |
| `Playtech` | Playtech | 117 | нет | Scala Developer; Senior Database Administrator | 73 (IGC) | Таллин/Киев/София/Рига/Мальта — очень релевантно RU/UA-аудитории |
| `Bet3651` | bet365 | 117 | нет | Senior Data Scientist; Technical Lead, Verification | 85 (IGC) + 3 (jobsinmalta) | Стоук-он-Трент, Мальта, Манчестер; id именно с единицей |
| `sportradar` | Sportradar | 80 | нет | Engineering Manager (m/f/d); Senior Software Engineer | 161 (IGC, 3 сущности) | Регистр id не важен |
| `slotegrator` | Slotegrator | 5 | нет | HR BP; Head of Marketing | 0 | Прага/Лимассол, русскоязычные команды |
| `smartico` | Smartico.ai | 3 | нет | UX Designer; QA Specialist | 2 (discovery) | CRM/геймификация для iGaming |
| `atlasiac` | Atlas-IAC | 2 | нет | Lead Front-end Developer; Senior Java Developer | 0 | B2B платформа/спортбук |

SmartRecruiters отвечает 200 и пустым `content` для любого id — при добавлении новых проверять `totalFound > 0`.

### BambooHR — `https://{slug}.bamboohr.com/careers/list` + `/careers/{id}/detail`

| slug | Компания | Вакансий | Зарплата | Пример названий | В БД | Заметки |
|---|---|---|---|---|---|---|
| `digitainsoftware` | Digitain | **78** | нет | Incident Management Specialist; Receptionist | 0 | Ереван — прямое попадание в RU/AM-аудиторию (см. статью про Ереван). Слаг найден через digitain.com/careers |
| `videoslots` | Videoslots Group | 17 | нет | Junior Customer Service Agent (Danish); (Finnish) | 0 | Мальта, много саппорта на языках |
| `gamingtec` | Gamingtec | 17 | нет | Senior Frontend Developer (React/RN); Senior Sales Manager | 13 (discovery) | Лимассол/Лондон/Ереван. Через API чище, чем текущий discovery-обход |
| `catenamedia` | Catena Media | 12 | нет | Senior Web Developer (WordPress); General Application | 3 (IGC) | Аффилейт; Lever `catenamedia` умер (404) — переехали на BambooHR |
| `mediastream` | Global Bet (виртуальный спорт) | 6 | нет | Sports Betting Trader; Java Developer | 0 | Мостар (БиГ); слаг найден на globalbet.com |
| `derivco` | Derivco (тех-арм Games Global/Microgaming) | 6 | нет | Database Administrator; Technical Project Manager L2 | 0 | Дурбан/Претория (ЮАР) |
| `continent8` | Continent 8 Technologies | 5 | нет | Sr Vendor Manager; Facilities Manager | 0 | Хостинг/DDoS-защита для iGaming, Остров Мэн |
| `xace` | Xace | 3 | нет | Compliance Analyst – Chainalysis SME; – Sumsub SME | 0 | Банкинг для гемблинга/крипто |
| `duelbits` | Duelbits | 2 | нет | Junior VIP Manager; Director of VIP | 0 | Крипто-казино |

BambooHR возвращает 200 и `result: []` для любого несуществующего слага — проверять `len(result) > 0`.

### Lever — `https://api.lever.co/v0/postings/{slug}?mode=json`

| slug | Компания | Вакансий | Зарплата | Пример названий | В БД | Заметки |
|---|---|---|---|---|---|---|
| `winamax` | Winamax | 20 | нет | Agentes de Atención al Cliente para España; Chargé de Relation Clients – Germanophone | 0 | Париж; крупнейший покер/беттинг Франции |
| `oddin` | Oddin.gg | 26 | нет | Brand and Creative Designer; Chief of Staff (Prague) | 0 | Esports-odds провайдер, Прага/remote Europe |
| `betr` | Betr | 11 | нет | Casino Operations Manager; Frontend Engineer – Mobile | 0 | США (Jake Paul), микробеттинг |
| `unlimit` | Unlimit | 47 | нет | Business Development Manager; Agentic Systems Engineer | 0 | Платёжный провайдер (в т.ч. gambling-мерчанты), Лимассол/Лондон/LatAm. Пограничный — брать с фильтром релевантности |

---

## 2. Проверено и работает — нужен НОВЫЙ адаптер (≈40 компаний)

### Ashby — `GET https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true`

JSON `{jobs:[{id,title,department,team,employmentType,location,secondaryLocations,publishedAt,isRemote,workplaceType,jobUrl,applyUrl,descriptionHtml,descriptionPlain,compensation}]}` — полное описание в одном запросе, `compensation.compensationTierSummary` даёт вилку текстом. Самый удобный API из новых. 404 для несуществующего слага.

| slug | Компания | Вакансий | Зарплата | Пример названий | В БД | Заметки |
|---|---|---|---|---|---|---|
| `leovegasgroup` | LeoVegas Group (MGM) | **75** | нет | Backend Engineer – Reporting; Senior Manager, HR Business Partnering | 2 (arbeitnow) | Стокгольм/Мальта/Варшава/Милан |
| `playson` | Playson | 26 | нет | UI Artist for Games; Senior 2D Artist | 1 (djinni) | Провайдер слотов, Киев/Мальта/remote — очень релевантно |
| `midnite` | Midnite | 22 | нет | Sports Trader; Senior Backend Engineer | 1 (arbeitnow) | UK-оператор (esports/спорт/казино) |
| `trustly` | Trustly | 17 | **да** (tier summary) | Staff Security Engineer; CISO | 0 | Платежи, Стокгольм/Мальта/Лиссабон. Lever `trustly` — пустой (200, []) |
| `zeal-network` | ZEAL Network (Lotto24, Tipp24) | 15 | нет | Senior Brand Manager (m/w/d); Senior CRM Technical Expert (SQL) | 0 | Гамбург, лотереи |
| `seon` | SEON | 12 | **да** | Senior Software Engineer (ID Verification); Senior RevOps Lead | 0 | Антифрод, Будапешт/Лондон/Остин |
| `smarkets` | Smarkets | 11 | нет | Software Engineer; Senior Backend Software Engineer | 4 (arbeitnow) | Лондон, биржа ставок |
| `block-labs` | Block Labs | 4 | нет | Senior Backend Engineer (Go); Data Platform Engineer | 4 (IGC) | Португалия; крипто-iGaming медиа/аффилейт |
| `moonactive` | Moon Active (Coin Master) | 37 | нет | DevOps Engineer; Full Stack Developer | 0 | Соцказино, Тель-Авив/Киев/Варшава — пограничный (social gaming) |
| `sleeper` | Sleeper | 18 | нет | Sr. Product Designer; Sports Team Content Curator | 0 | DFS, США — пограничный |

### Workable — `GET https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true` (или `POST /api/v3/accounts/{slug}/jobs`)

Отдаёт `{name, description, jobs:[{title, shortcode, url, city, country, state, department, employment_type, telecommuting, published_on, description}]}`. **Осторожно: Cloudflare «Security challenge» (HTTP 429, HTML) после ~40 запросов за короткое окно с одного IP, независимо от UA; блок держится ~10–15 минут.** Для 7 аккаунтов по одному запросу с паузой 3 с — норм. 404 JSON для несуществующего слага.

| slug | Компания | Вакансий | Зарплата | Пример названий | В БД | Заметки |
|---|---|---|---|---|---|---|
| `nuvei` | Nuvei | **76** | нет | AI Product Owner; BackOffice Specialist | 66 (IGC) | Платежи; София/Тель-Авив/Монреаль |
| `payabl` | payabl. | 63 | нет | AML Officer; Analytics Engineer | 0 | Платежи для high-risk, Лимассол/Франкфурт/Лондон |
| `comeon-group` | ComeOn Group | 34 | нет | Agile Delivery Coordinator; Casino Commercial Manager – Sweden | 35 (IGC) | Мальта/Стокгольм/Лондон/Гданьск |
| `kingmakers` | KingMakers (BetKing) | 10 | нет | 3D Motion Designer; Brand, Media & Influencer Marketing Specialist | 13 (IGC) | Африка + Мальта/Лондон |
| `spotlightsportsgroup` | Spotlight Sports Group (Racing Post) | 9 | нет | Data Analyst; Commercial Finance Manager | 0 | Лондон; контент/аффилейт |
| `openbet-1` | OpenBet | 8 | нет | Associate Sports Trader; Associate Sports Content Coordinator | 0 | Слаг с суффиксом `-1`; `openbet` → 404 |
| `rhino-entertainment` | Rhino Entertainment | 5 | нет | Automation & AI Specialist | 7 (IGC) | Мальта, casino-бренды |

### Teamtailor — `https://{slug}.teamtailor.com/jobs.rss` (или кастомный домен `/jobs.rss`)

RSS без ключа: `<item>` с `title`, `description` (полный HTML), `link`, `pubDate`, `guid`, `remoteStatus`, `<tt:locations><tt:location><tt:city>/<tt:country>` — всего хватает для карточки. Зарплат нет. Кастомные домены часто не имеют записи `*.teamtailor.com` — брать URL из таблицы как есть.

| URL фида | Компания | Вакансий | Пример названий | В БД | Заметки |
|---|---|---|---|---|---|
| `https://boylesports.teamtailor.com/jobs.rss` | BoyleSports | 79 | Assistant Manager – Coventry; Cleaner – Adare | 15 (discovery) | ~80 % — ритейл-точки Ирландии/UK; фильтровать по «Shop/Cashier/Cleaner/Assistant Manager» |
| `https://everymatrix.teamtailor.com/jobs.rss` | EveryMatrix | 33 | Trader Specialist; Account Director – German | 41 (IGC) + 11 (discovery) | Бухарест/Лондон/Львов/Ереван; RSS чище discovery-обхода |
| `https://careers.sumsub.com/jobs.rss` | Sumsub | 33 | TM/TR Solutions Engineer (EMEA); Education Manager | 0 | KYC; Лимассол/Лондон/Берлин, много remote |
| `https://careers.relax-gaming.com/jobs.rss` | Relax Gaming | 8 | Test Automation Engineer; DevOps Engineer | 10 (IGC) + 6 (discovery) | Мальта/Таллин/Белград |
| `https://pushgaming.teamtailor.com/jobs.rss` | Push Gaming | 8 | Senior Account Manager; Go To Market Executive | 0 | Мальта/Лондон; `pushgaming.bamboohr.com` — редирект на маркетинг, мёртв |
| `https://statsperform.teamtailor.com/jobs.rss` | Stats Perform (Opta) | 7 | Data Collection Analyst; HR Coordinator | 0 | Спорт-данные |
| `https://shuffle.teamtailor.com/jobs.rss` | Shuffle.com | 7 | Business Development Representative – Edinburgh/Manchester | 0 | Крипто-казино |
| `https://finnplay.teamtailor.com/jobs.rss` | Finnplay | 5 | Project Manager; Marketing Manager | 0 | Платформа, Хельсинки/Мальта |
| `https://careers.ezugi.com/jobs.rss` | Ezugi (Evolution) | 5 | Game Presenter, English; C&B Specialist, Bucharest | 0 | Лайв-казино |
| `https://karriere.danskespil.dk/jobs.rss` | Danske Spil | 5 | Senior Commercial Analyst; paid media | 0 | Дания, на датском |
| `https://careers.britepayments.com/jobs.rss` | Brite Payments | 5 | Senior Sales Executive, iGaming; SWE – Payment Ops | 0 | A2A-платежи, Стокгольм/Мальта |
| `https://careers.gentoomedia.com/jobs.rss` | Gentoo Media (ex-GiG Media) | 5 | Website Coordinator – Norwegian; Product Manager | 0 | Аффилейт; корневой домен даёт 403, брать `careers.` |
| `https://careers.jumbointeractive.com/jobs.rss` | Jumbo Interactive | 4 | Customer Service Advisor; Senior Paid Media Specialist | 0 | Лотереи, Австралия/UK |
| `https://careers.lckygroup.com/jobs.rss` | LCKY Group (Swintt) | 3 | IT Systems Engineer; Customer Support Agent (Finnish) | 0 | Мальта; найдено на swintt.com |
| `https://thecasumolimited.teamtailor.com/jobs.rss` | Casumo | 2 | Senior Accountant; Casino Manager | 8 (IGC) | `casumo.bamboohr.com` даёт ещё 1 |
| `https://careers.wildz.group/jobs.rss` | Rootz / Wildz | 2 | UI Designer; Finnish-speaking Support | 0 | Мальта |
| `https://career.svenskaspel.se/jobs.rss` | Svenska Spel | 2 | Product Manager; Chief Platform Owner | 0 | Швеция, госоператор |
| `https://coolbet.teamtailor.com/jobs.rss` | Coolbet (GAN) | 2 | Operations Manager; Data Analyst | 0 | Таллин; ссылки ведут на careers.coolbet.ee |
| `https://careers.clickoutmedia.com/jobs.rss` | ClickOut Media (Finixio) | 2 | Programmatic Ad Ops Specialist; Treasury Ops Analyst | 0 | Аффилейт |
| `https://pmu.teamtailor.com/jobs.rss` | PMU | 2 | стажировки (Chief of Staff Junior; Compliance) | 0 | Франция, только стажировки |
| `https://tombola.teamtailor.com/jobs.rss` | tombola (Flutter) | 1 | Customer Service Team Leader – Italian | 0 | Сандерленд |
| `https://careers.leadstarmedia.com/jobs.rss` | Leadstar Media | 1 | Account Manager (English Speaking) | 0 | Аффилейт, Стокгольм |
| `https://herogaming.teamtailor.com/jobs.rss` | Hero Gaming | 1 | Senior Paid Media Specialist | 0 | Мальта |
| `https://sportserve.teamtailor.com/jobs.rss` | Sportserve (Dafabet) | 1 | Lead Generation Specialist – China | 0 | |

`softswiss.teamtailor.com/jobs.rss` — 53 вакансии, но SOFTSWISS уже собирается через WP REST (56) — не дублировать.

### Recruitee — `https://{slug}.recruitee.com/api/offers/`

JSON `{offers:[{id,title,description,requirements,city,country,location,careers_url,created_at,department,employment_type_code,remote,hybrid,salary:{min,max,currency,period},…}]}` — единственный из новых ATS с **вилкой в структурированном поле** (заполнена не всегда). 404 для несуществующего слага.

| slug | Компания | Вакансий | Зарплата | Пример названий | В БД | Заметки |
|---|---|---|---|---|---|---|
| `hardrockdigital` | Hard Rock Digital (Hard Rock Bet) | **53** | **да** | Director – VIP Player Development; Senior Performance Manager – Verifications | 0 | США/Канада/Мальта |
| `bettercollective` | Better Collective | 15 | **да** | Senior AI Engineer | 21 (IGC) | Копенгаген/Вена/Париж/Ниш |
| `grid` | GRID Esports (+ Bayes Esports) | 12 | **да** | Junior Live Esports Trader – MOBA; Backend Engineer (m/f/x) | 0 | Берлин/Вроцлав; bayesesports.com ведёт на тот же слаг |
| `zota` | Zotapay (Zota) | 9 | поле есть, пусто | Junior Financial Operator (Hong Kong); Customer Success Manager (Singapore) | 0 | Платежи для high-risk; `zotapay` — алиас того же борда |
| `huuuge` | Huuuge Games | 7 | **да** | Head of User Acquisition; Senior Data Analyst | 0 | Соцказино, Варшава/Щецин — пограничный |
| `raketech` | Raketech | 3 | **да** | Content Writers – Freelancers (Casino); Freelance News Editor (Danish market) | 0 | Аффилейт, Мальта |
| `fasttrack` | Fast Track | 1 | **да** | NOC Engineer (Service Operations) | 0 | CRM для iGaming, Мальта |

### Personio — `https://{slug}.jobs.personio.de/search.json`

JSON-список `{id,name,office,offices,department,description,employment_type,seniority,schedule,category,keywords}`. **Агрессивный 429** (Astro-страница) уже после нескольких запросов подряд к разным поддоменам — брать ≤ 3 аккаунта с паузой 5+ с.

| slug | Компания | Вакансий | Пример названий | Заметки |
|---|---|---|---|---|
| `xtremepush` | Xtremepush | 6 | Product Designer; Sales Team Lead (Dublin/London) | CRM/маркетинг-платформа для iGaming |
| `booming-games` | Booming Games | 3 | Senior HTML5 Game Developer; Senior Backend Developer | Remote EU/Мальта; сайт boominggames.com недоступен ботам, а Personio отвечает |
| `playbook-engineering` | Playbook Engineering | 3 | SEO Marketing Manager; Social Media (Working Student) | Sportsbook-платформа, Краков/Лондон; `office` пустой |

---

## 3. Проверено, но пусто / закрыто / неподдерживаемый ATS

**Пустые или заглушки на поддерживаемых ATS**
- `greenhouse:lottoland` — 1 запись «Join our Talent Community!» (не вакансия).
- `greenhouse:stoiximan` — 1 вакансия (Kaizen уже покрыт `kaizengaming`).
- `smartrecruiters:bgaming` — 1 тестовый пост «SuperWork».
- `bamboohr:yggdrasilgaming` — 1 запись «Test Title».
- `bamboohr:praxistech` (Praxis Tech) — 0. `bamboohr:casumo` — 1 (основной фид — Teamtailor выше).
- `lever:trustly`, `lever:doubledown` — 200, пустой список (переехали на Ashby / закрыли).
- `lever:catenamedia`, `lever:hippodromecasino`, `lever:coinspaid`, `lever:kto` — 404 (ссылки из IGC/сайтов устарели).
- `careers.gan.com/jobs.rss`, `jobs.abiosgaming.com/jobs.rss` — валидный RSS, 0 вакансий.

**Работают на ATS без публичного JSON (адаптер не имеет смысла или отдельная задача)**
- **Workday** (`*.myworkdayjobs.com`, нужен POST к `/wday/cxs/...` с сессией): Light & Wonder / SciPlay (`lnw.wd5`), Super Group / Betway (`myhcm.wd3`), BetMGM (`betmgminc.wd5`), DraftKings (`draftkings.wd1`), Bragg (`bragggaming`), Sisal (`sisal`), Aristocrat / Product Madness (`aristocrat.wd3`).
- **Jobvite**: Pragmatic Play (`jobs.jobvite.com/pragmaticplay`). `pragmatic.teamtailor.com` — это Pragmatic Semiconductor, не наш.
- **iCIMS**: Games Global (`employees-gamesglobal.icims.com`), Penn Entertainment corporate.
- **Oracle HCM**: Caesars, Fanatics, Hollywoodbets. **SuccessFactors**: IGT.
- **Breezy HR** (`{slug}.breezy.hr/json` — есть простой публичный JSON, кандидат на будущий адаптер): Betclic (`betclic-group`), Stake (`stake`).
- **Pinpoint** (`{slug}.pinpointhq.com/postings.json` — тоже публичный JSON): GiG (`gig`), Everi/IGT.
- **Rippling**: BetMakers, White Hat Gaming. **Jobylon**: Zimpler. **PeopleForce**: Blask. **softgarden**: Gamomat. **HiBob**: Paysafe. **Welcome to the Jungle**: Winamax (но у них есть Lever), PandaScore. **Manatal**: Brazino777.

**Ни на одном из 9 ATS не найдены ни по слагам, ни при сканировании карьерных страниц** (свои формы/JS-порталы или вакансий нет): Evoplay, Endorphina, BetConstruct, Betby, Delasport, Uplatform, Pin-Up, 1xBet, Fonbet, Winline, BetBoom, Liga Stavok, Paynetics, Gambling.com Group, Acroud, Pronet Gaming, Boomerang Partners, Alpha Affiliates, evoke/888/William Hill, Novibet, bet-at-home, LiveScore Group, Sky Betting & Gaming, Bally's/Gamesys, Flutter/PokerStars/Betfair/Paddy Power, Kindred (careers.kindredgroup.com — свой портал, `jobs.rss` 404), Yolo Group/Coingaming (careers.yolo.com отвечает 200 HTML, RSS нет), Roobet, Cloudbet, 1win, Mostbet, Yggdrasil, Play'n GO (Teamtailor-генератор на сайте, но кастомный домен не найден), Hacksaw (уже BambooHR, 1), Thunderkick, Quickspin, Nolimit City, Red Tiger, Big Time Gaming, Wazdan, Amusnet, Spribe, Habanero, Spinomenal, PG Soft, Greentube/Novomatic, Inspired, Aspire Global/Pariplay, NeoGames, Hub88, Betsoft, Kiron, Golden Race, LSports, Rivalry, Thunderpick, Luckbox, Paf, ATG (`jobs.atg.se` не резолвится), Veikkaus, Allwyn, FDJ, Codere, Cirsa, Luckia, STS, Fortuna, Tipsport, Interwetten, Merkur, Admiral, Meridianbet, Mozzart, OlyBet, TonyBet, Pinnacle, SportPesa, Bet9ja, Betika, Gamanza, Pragmatic Solutions, Blexr (embed Greenhouse на сайте, но борд `blexr` → 404), MiFinity, MuchBetter, Jeton, Corefy, Devcode, PaymentIQ, AstroPay, Volt, Noda, emerchantpay, Payz, GeoComply, Mindway AI, iGaming Academy, SiGMA, Clarion Gaming, Affilka, Income Access, MyAffiliates, Cellxpert, Scaleo, Voluum, Traffic Devils.

**Не удалось проверить**: Personio — большинство аккаунтов ответили 429 до получения данных (Tipico в итоге найден на SmartRecruiters). Workable — после первых ~40 запросов Cloudflare-челлендж, ~270 слагов из списка остались непроверенными (в т.ч. LiveScore, Novibet, Tipico, Bally's, Hero Gaming); повторить через день с паузой 3 с или с прод-IP.

**Коллизии слагов (НЕ подключать, выглядят как хиты, но это другие компании)**: `greenhouse:aviatrix` (облачные сети, США), `greenhouse:sts` (сантехника, Северная Каролина), `greenhouse:sbg`/`recruitee:sbg` (ботсад / немецкий завод), `ashby:atg` (AI-лаба NYC), `ashby:clarion` (стартап NYC), `ashby:kindred` (US-стартап, не Kindred Group), `recruitee:merkur` (австрийская страховая), `personio:feg` (берлинский консалтинг), `lever:coolbet` (US-компания; настоящий Coolbet — Teamtailor выше), `teamtailor:pragmatic` (Pragmatic Semiconductor), `teamtailor:endeavor`/`bamboohr:endeavor` (Endeavor entrepreneurs), `bamboohr:pinnacle` (медклиника, GP Locum), `bamboohr:adtechholding` (PropellerAds — adtech, не iGaming), `smartrecruiters:jumio` (2 вакансии, KYC общего профиля).

---

## 4. Готовые строки для crawler.py

### 4.1. Уже поддерживаемые ATS — просто дописать в словари

```python
# --- GREENHOUSE_BOARDS (добавить к существующим 4) ---
    "super": "Superbet Group",                      # 178, job-boards.eu
    "fanduel": "FanDuel",                           # 86, США
    "sportygroup": "Sporty Group (SportyBet)",      # 41
    "penninteractive": "Penn Interactive (theScore / ESPN Bet)",  # 38
    "easygo": "Stake.com (Easygo)",                 # 33
    "prizepicks": "PrizePicks",                     # 29, США
    "rushstreetinteractive": "Rush Street Interactive (BetRivers)",  # 21
    "optimove": "Optimove",                         # 15, B2B CRM
    "soft2bet": "Soft2Bet",                         # 8
    "kambi": "Kambi",                               # 6
    "elagames": "Ela Games",                        # 4
    "truelayer": "TrueLayer",                       # 2, платежи

# --- LEVER_SITES (сейчас {}) ---
LEVER_SITES = {
    "winamax": "Winamax",           # 20, Париж
    "oddin": "Oddin.gg",            # 26, esports odds, Прага
    "betr": "Betr",                 # 11, США
    "unlimit": "Unlimit",           # 47, платежи — прогонять через job_is_irrelevant
}

# --- SMARTRECRUITERS_COMPANIES (добавить к "Evolution") ---
    "Entain": "Entain",             # 291, много ритейла — фильтр Retail/Shop/Cashier
    "tipico": "Tipico",             # 159
    "Playtech": "Playtech",         # 117
    "Bet3651": "bet365",            # 117 — id именно Bet3651
    "sportradar": "Sportradar",     # 80
    "slotegrator": "Slotegrator",   # 5
    "smartico": "Smartico.ai",      # 3
    "atlasiac": "Atlas-IAC",        # 2

# --- BAMBOO_ACCOUNTS (добавить к altenar/kalambagames/hacksawoperations) ---
    "digitainsoftware": "Digitain",           # 78, Ереван
    "videoslots": "Videoslots Group",         # 17
    "gamingtec": "Gamingtec",                 # 17
    "catenamedia": "Catena Media",            # 12
    "mediastream": "Global Bet",              # 6, Мостар
    "derivco": "Derivco (Games Global)",      # 6, ЮАР
    "continent8": "Continent 8 Technologies", # 5
    "xace": "Xace",                           # 3
    "duelbits": "Duelbits",                   # 2
```

Замечание по `MAX_PER_BOARD = 100`: Superbet (178), Entain (291), Tipico (159), Playtech/bet365 (117) режутся до 100. Для Greenhouse ответ уже полный (лимит применяется срезом), для SmartRecruiters нужно добавить пагинацию `offset=` или поднять лимит для этих id.

SOURCE_REGISTRY — по шаблону существующих записей, например:

```python
    {"key": "greenhouse:super", "name": "Superbet Group", "type": "Greenhouse API",
     "status": "подключён", "note": "Публичный JSON API; 170+ вакансий RO/PL/BR, борд в EU-регионе"},
    {"key": "smartrecruiters:Entain", "name": "Entain", "type": "SmartRecruiters API",
     "status": "подключён", "note": "Публичный ATS API, ~290 вакансий; ритейл-точки UK отсекаем фильтром"},
    {"key": "bamboohr:digitainsoftware", "name": "Digitain", "type": "Публичный карьерный портал",
     "status": "подключён", "note": "BambooHR /careers/list + /detail, ~80 вакансий, Ереван"},
    {"key": "lever:winamax", "name": "Winamax", "type": "Lever Postings API",
     "status": "подключён", "note": "Публичный JSON, Париж"},
```

### 4.2. Новые ATS — словари + черновики адаптеров (регистрировать в collect() по образцу `fetch_source(f"ashby:{slug}", ...)`)

```python
# Ashby: один GET, полный descriptionHtml и вилка (compensationTierSummary)
ASHBY_BOARDS = {
    "leovegasgroup": "LeoVegas Group",   # 75
    "playson": "Playson",                # 26
    "midnite": "Midnite",                # 22
    "trustly": "Trustly",                # 17, вилка есть
    "zeal-network": "ZEAL Network",      # 15
    "seon": "SEON",                      # 12, вилка есть
    "smarkets": "Smarkets",              # 11
    "block-labs": "Block Labs",          # 4
    # пограничные (соцказино/DFS): "moonactive": "Moon Active", "sleeper": "Sleeper"
}


def crawl_ashby(board, company):
    data = json.loads(_fetch(
        f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"))
    out = []
    for j in (data.get("jobs") or [])[:MAX_PER_BOARD]:
        title = (j.get("title") or "").strip()
        if not title or j.get("isListed") is False:
            continue
        loc = ", ".join(filter(None, [j.get("location")] +
                               [s.get("location") for s in (j.get("secondaryLocations") or [])]))
        desc = _clean_html(j.get("descriptionHtml") or j.get("descriptionPlain") or "")
        comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
        lang = detect_lang(title, desc)
        out.append({"title": title, "company_name": company, "location": loc,
                    "fmt": "удалёнка" if j.get("isRemote") else _fmt_from(loc, desc),
                    "tags": _tags_from(f"{title} {j.get('department') or ''}", desc, lang),
                    "description": desc, "source_url": j.get("jobUrl") or j.get("applyUrl", ""),
                    "source": f"ashby:{board}", "ext_id": str(j.get("id", "")),
                    "salary": comp or "по запросу",
                    "posted_at": (j.get("publishedAt") or "")[:10], "deadline": ""})
    return out


# Workable: widget API, GET; Cloudflare-челлендж (429/HTML) при >~40 запросах за окно —
# держать паузу 3 с между аккаунтами и не ретраить в том же прогоне.
WORKABLE_ACCOUNTS = {
    "nuvei": "Nuvei",                                  # 76
    "payabl": "payabl.",                               # 63
    "comeon-group": "ComeOn Group",                    # 34
    "kingmakers": "KingMakers (BetKing)",              # 10
    "spotlightsportsgroup": "Spotlight Sports Group",  # 9
    "openbet-1": "OpenBet",                            # 8 — слаг с «-1»
    "rhino-entertainment": "Rhino Entertainment",      # 5
}


def crawl_workable(account, company):
    data = json.loads(_fetch(
        f"https://apply.workable.com/api/v1/widget/accounts/{account}?details=true"))
    out = []
    for j in (data.get("jobs") or [])[:MAX_PER_BOARD]:
        title = (j.get("title") or "").strip()
        if not title:
            continue
        loc = ", ".join(filter(None, [j.get("city"), j.get("country")]))
        desc = _clean_html(j.get("description") or "")
        lang = detect_lang(title, desc)
        out.append({"title": title, "company_name": company, "location": loc,
                    "fmt": "удалёнка" if j.get("telecommuting") else _fmt_from(loc, desc),
                    "tags": _tags_from(f"{title} {j.get('department') or ''}", desc, lang),
                    "description": desc, "source_url": j.get("url", ""),
                    "source": f"workable:{account}", "ext_id": str(j.get("shortcode") or j.get("id", "")),
                    "salary": "по запросу", "posted_at": (j.get("published_on") or "")[:10], "deadline": ""})
    time.sleep(3)
    return out


# Teamtailor: RSS без ключа (полный HTML в description, tt:locations, remoteStatus, pubDate).
# Ключ словаря — полный URL фида: кастомные домены часто не имеют *.teamtailor.com.
TEAMTAILOR_FEEDS = {
    "https://boylesports.teamtailor.com/jobs.rss": "BoyleSports",             # 79, много ритейла
    "https://everymatrix.teamtailor.com/jobs.rss": "EveryMatrix",             # 33
    "https://careers.sumsub.com/jobs.rss": "Sumsub",                          # 33
    "https://careers.relax-gaming.com/jobs.rss": "Relax Gaming",              # 8
    "https://pushgaming.teamtailor.com/jobs.rss": "Push Gaming",              # 8
    "https://statsperform.teamtailor.com/jobs.rss": "Stats Perform",          # 7
    "https://shuffle.teamtailor.com/jobs.rss": "Shuffle.com",                 # 7
    "https://finnplay.teamtailor.com/jobs.rss": "Finnplay",                   # 5
    "https://careers.ezugi.com/jobs.rss": "Ezugi",                            # 5
    "https://karriere.danskespil.dk/jobs.rss": "Danske Spil",                 # 5
    "https://careers.britepayments.com/jobs.rss": "Brite Payments",           # 5
    "https://careers.gentoomedia.com/jobs.rss": "Gentoo Media",               # 5
    "https://careers.jumbointeractive.com/jobs.rss": "Jumbo Interactive",     # 4
    "https://careers.lckygroup.com/jobs.rss": "LCKY Group (Swintt)",          # 3
    "https://thecasumolimited.teamtailor.com/jobs.rss": "Casumo",             # 2
    "https://careers.wildz.group/jobs.rss": "Rootz (Wildz)",                  # 2
    "https://career.svenskaspel.se/jobs.rss": "Svenska Spel",                 # 2
    "https://coolbet.teamtailor.com/jobs.rss": "Coolbet (GAN)",               # 2
    "https://careers.clickoutmedia.com/jobs.rss": "ClickOut Media",           # 2
    "https://tombola.teamtailor.com/jobs.rss": "tombola",                     # 1
    "https://careers.leadstarmedia.com/jobs.rss": "Leadstar Media",           # 1
    "https://herogaming.teamtailor.com/jobs.rss": "Hero Gaming",              # 1
    "https://sportserve.teamtailor.com/jobs.rss": "Sportserve (Dafabet)",     # 1
}


def crawl_teamtailor(feed_url, company):
    import xml.etree.ElementTree as ET
    TT = "{https://teamtailor.com/locations}"
    root = ET.fromstring(_fetch(feed_url).encode("utf-8"))
    out = []
    for item in root.findall(".//item")[:MAX_PER_BOARD]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        cities = [c.text for c in item.iter(f"{TT}city") if c.text]
        countries = [c.text for c in item.iter(f"{TT}country") if c.text]
        loc = ", ".join(dict.fromkeys(cities + countries))
        desc = _clean_html(item.findtext("description") or "")
        remote = (item.findtext("remoteStatus") or "").lower()
        lang = detect_lang(title, desc)
        host = urlparse(feed_url).netloc
        out.append({"title": title, "company_name": company, "location": loc,
                    "fmt": "удалёнка" if remote == "fully" else _fmt_from(loc, desc),
                    "tags": _tags_from(title, desc, lang), "description": desc,
                    "source_url": link, "source": f"teamtailor:{host}",
                    "ext_id": item.findtext("guid") or link.rsplit("/", 1)[-1].split("-")[0],
                    "salary": "по запросу", "posted_at": "", "deadline": ""})
    return out


# Recruitee: единственный из новых ATS со структурированной вилкой (salary.min/max/currency/period).
RECRUITEE_COMPANIES = {
    "hardrockdigital": "Hard Rock Digital",   # 53
    "bettercollective": "Better Collective",  # 15
    "grid": "GRID Esports",                   # 12
    "zota": "Zotapay",                        # 9
    "raketech": "Raketech",                   # 3
    "fasttrack": "Fast Track",                # 1
    # пограничный: "huuuge": "Huuuge Games"
}


def crawl_recruitee(slug, company):
    data = json.loads(_fetch(f"https://{slug}.recruitee.com/api/offers/"))
    out = []
    for o in (data.get("offers") or [])[:MAX_PER_BOARD]:
        title = (o.get("title") or "").strip()
        if not title:
            continue
        loc = o.get("location") or ", ".join(filter(None, [o.get("city"), o.get("country")]))
        desc = _clean_html("\n".join(filter(None, [o.get("description"), o.get("requirements")])))
        sal = o.get("salary") or {}
        salary = "по запросу"
        if sal.get("min") or sal.get("max"):
            salary = f"{sal.get('min') or ''}–{sal.get('max') or ''} {sal.get('currency') or ''}/{sal.get('period') or ''}".strip()
        lang = detect_lang(title, desc)
        out.append({"title": title, "company_name": company, "location": loc,
                    "fmt": "удалёнка" if o.get("remote") else _fmt_from(loc, desc),
                    "tags": _tags_from(f"{title} {o.get('department') or ''}", desc, lang),
                    "description": desc, "source_url": o.get("careers_url", ""),
                    "source": f"recruitee:{slug}", "ext_id": str(o.get("id", "")),
                    "salary": salary, "posted_at": (o.get("created_at") or "")[:10], "deadline": ""})
    return out


# Personio: search.json; жёсткий 429 — не больше 3 аккаунтов, пауза 5 с.
PERSONIO_ACCOUNTS = {
    "xtremepush": "Xtremepush",                 # 6
    "booming-games": "Booming Games",           # 3
    "playbook-engineering": "Playbook Engineering",  # 3
}
# crawl_personio: GET https://{slug}.jobs.personio.de/search.json -> список {id,name,office,description,...};
# ссылка на вакансию: https://{slug}.jobs.personio.de/job/{id}
```

Приоритет подключения по объёму и релевантности RU/EU-аудитории: **Superbet, Digitain, Playtech, Entain (с фильтром), Tipico, bet365, LeoVegas (Ashby), Playson (Ashby), Sumsub/EveryMatrix (Teamtailor), Nuvei/payabl (Workable), Hard Rock Digital (Recruitee)** — вместе это ~1 100 вакансий с полными описаниями от первоисточников.

Рабочие файлы проверки (сырые JSONL с каждым запросом): `/private/tmp/claude-501/-Users-afin-Desktop-Ihiring/7d34fe95-22d2-4c1c-83cf-0276250f539b/scratchpad/{results,results2,results_workable,discover}.jsonl`, скрипты `probe.py`, `discover.py` там же.
