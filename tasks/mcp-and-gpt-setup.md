# SpinHire как инструмент для ИИ: MCP-сервер и GPT

Дата: 3 сентября 2026. Всё ниже уже работает на проде без ключей.

## Что есть

| Что | Адрес | Для кого |
|---|---|---|
| MCP-сервер (Streamable HTTP, stateless, JSON) | `https://spinhire.io/mcp` | Claude (коннекторы), ChatGPT (коннекторы/Deep Research), Cursor, Windsurf, любые агенты на MCP SDK |
| OpenAPI 3.1 схема публичного API | `https://spinhire.io/openapi.json` | GPT Actions, Postman, генераторы клиентов |
| Swagger UI | `https://spinhire.io/docs` | люди |
| Открытое API | `https://spinhire.io/api/jobs`, `/api/market-stats`, `/api/market-history` | все, CC BY 4.0 |

Инструменты MCP: `search_jobs`, `get_job`, `market_stats`, `market_history`, `list_professions`, `get_profession`, `get_company`. Страны и направления принимаются по-английски и по-русски.

Проверка из терминала:

```bash
curl -s -X POST https://spinhire.io/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## Что сделать тебе (аккаунты)

1. **Claude.ai → Settings → Connectors → Add custom connector**: URL `https://spinhire.io/mcp`, без авторизации. После этого в чате можно спросить «find KYC jobs in Malta» и Claude вызовет наш инструмент.
2. **Anthropic MCP Registry** (публичный каталог): https://github.com/modelcontextprotocol/registry — публикация через `mcp-publisher` из GitHub-репозитория; нужен репозиторий с `server.json`. Заготовка ниже.
3. **Smithery**: https://smithery.ai/new — «Add remote server», URL `https://spinhire.io/mcp`.
4. **Glama**: https://glama.ai/mcp/servers — «Submit server», remote URL.
5. **mcp.so**: https://mcp.so/submit.
6. **ChatGPT → Explore GPTs → Create → Configure → Actions → Import from URL**: `https://spinhire.io/openapi.json`. Название «iGaming Jobs by SpinHire», описание из outreach-кита, privacy policy `https://spinhire.io/privacy.html`. Опубликовать в GPT Store (нужен верифицированный домен spinhire.io в Builder profile: Settings → Builder profile → Verify domain, добавляется TXT-запись в DNS).
7. **ChatGPT Connectors (для Deep Research / Pro)**: Settings → Connectors → Add MCP server, URL `https://spinhire.io/mcp`, «No authentication».

## Заготовка server.json для MCP Registry

```json
{
  "$schema": "https://static.modelcontextprotocol.io/schemas/2025-07-09/server.schema.json",
  "name": "io.spinhire/igaming-jobs",
  "description": "Live iGaming job index (5,000+ open jobs, refreshed every 6 hours), 35 profession cards with salary bands and labour-market statistics. CC BY 4.0.",
  "repository": { "url": "https://github.com/TimVR13/spinhire", "source": "github" },
  "version": "1.0.0",
  "remotes": [ { "type": "streamable-http", "url": "https://spinhire.io/mcp" } ]
}
```

Для верификации namespace `io.spinhire` реестр попросит DNS TXT-запись или файл на домене; текст выдаст сам `mcp-publisher login dns`.

## Датасет для Kaggle / Hugging Face

```bash
python3 scripts/export_dataset.py
```

Создаёт `data/dataset/` с `jobs.csv`, `jobs.jsonl`, `market_monthly.csv`, `market_daily.csv` и `README.md` (карточка датасета). Загрузить как:

- Kaggle: https://www.kaggle.com/datasets → New Dataset → загрузить папку, лицензия CC BY 4.0, название «iGaming Job Market (SpinHire)».
- Hugging Face: https://huggingface.co/new-dataset → `spinhire/igaming-jobs`, README.md станет dataset card.

Обновлять раз в месяц вместе с выпуском Hiring Index (`/market/YYYY-MM`).
