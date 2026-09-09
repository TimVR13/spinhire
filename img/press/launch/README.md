# Кадры галереи для Product Hunt и каталогов

Сами PNG в репозиторий не кладём (`.gitignore`): они устаревают на следующий же
день — вместе с цифрами на сайте и любой правкой текстов.

Собрать заново:

```bash
pip install playwright                    # один раз
python3 scripts/launch_shots.py           # 6 кадров 2540×1520 сюда же
python3 scripts/launch_shots.py --list    # что снимается и с какой подписью
```

Снимать **только после деплоя**: скрипт ходит на прод, и всё, что не выкачено,
попадёт в галерею в старом виде.

Порядок кадров задан в `scripts/launch_shots.py` — он же порядок галереи:
первый кадр видно в ленте Product Hunt, остальные открываются по клику.

| Файл | Страница | Подпись в кадре |
|---|---|---|
| `01-hero.png` | `/en/` | 6,000+ live iGaming jobs, refreshed every 6 hours |
| `02-jobs.png` | `/en/jobs` | Filters the industry actually needs… |
| `03-market.png` | `/en/market` | Public labour-market data with methodology… |
| `04-professions.png` | `/en/professions` | 35 profession cards with salary bands… |
| `05-api.png` | `/api/jobs?limit=3` | The whole index as an open API — no key, CC BY 4.0 |
| `06-employers.png` | `/en/post-job` | For employers: structured posting… |

Логотипы и обложки, которые просят каталоги, лежат в `/img` и собраны на
странице пресс-кита: <https://spinhire.io/press.html>.
