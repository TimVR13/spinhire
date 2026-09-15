# Автодеплой SpinHire

Две независимые опции. Выбери одну.

## Вариант A — GitHub Actions (мгновенно при пуше в main)
Файл: `.github/workflows/deploy.yml`. При каждом пуше в `main` GitHub заходит по SSH
на сервер и делает `git reset --hard origin/main` + `pip install` + `systemctl restart`.

Нужно один раз добавить 3 секрета в репозитории GitHub
(Settings → Secrets and variables → Actions → New repository secret):
- `DEPLOY_HOST` = `165.232.79.152`
- `DEPLOY_USER` = `root`
- `DEPLOY_SSH_KEY` = полное содержимое приватного ключа `~/.ssh/coex`
  (`cat ~/.ssh/coex`, вставить целиком, включая строки BEGIN/END).

⚠️ Риск: этот ключ = root на общем сервере. Кто получит доступ к секретам репо —
получит root. Безопаснее завести отдельного deploy-пользователя с ограниченным ключом
(или использовать Вариант B, где ключ вообще не покидает сервер).

## Вариант B — сервер сам опрашивает GitHub (рекомендую, без ключей в GitHub)
Файлы: `deploy/autopull.sh`, `deploy/spinhire-autopull.service`, `deploy/spinhire-autopull.timer`.
Сервер раз в 2 минуты проверяет origin/main и обновляется, только если есть новые коммиты.
Никаких секретов в GitHub, никакого входящего порта.

Установка на сервере (один раз):
```bash
ssh -i ~/.ssh/coex root@165.232.79.152 '
  cd /opt/spinhire && git pull --ff-only &&
  chmod +x deploy/autopull.sh &&
  cp deploy/spinhire-autopull.service deploy/spinhire-autopull.timer /etc/systemd/system/ &&
  systemctl daemon-reload &&
  systemctl enable --now spinhire-autopull.timer &&
  systemctl list-timers spinhire-autopull.timer --no-pager
'
```
Отключить: `systemctl disable --now spinhire-autopull.timer`.
Посмотреть журнал: `journalctl -u spinhire-autopull.service -n 30 --no-pager`.

## После 15.09.2026 — поставить руками (root на дроплете)

```bash
cp /opt/spinhire/deploy/deploy.sh /opt/spinhire/deploy.sh && chmod +x /opt/spinhire/deploy.sh
cp /opt/spinhire/deploy/limits.conf /etc/systemd/system/spinhire.service.d/limits.conf && systemctl daemon-reload
```

- `deploy.sh`: бэкап БД через sqlite backup API вместо cp живого WAL-файла и без обратной
  перезаписи поверх открытой базы (давала «database disk image is malformed» на каждом деплое).
- `limits.conf`: MemoryMax=1500M и TimeoutStopSec=20 — раздувшийся процесс убивается и
  поднимается за 3 секунды вместо 20 минут мёртвого сайта.

## Защита от падений (15.09.2026)

Что случилось: фоновый поток рассылки (`server/alerts.py`) внутри uvicorn перебирал резюме × вакансии,
держал GIL и раздувал память; сосед по дроплету (`wallet-control`, ~900 МБ) утащил сервер в своп;
graceful stop зависшего процесса ждал 90 с. Сайт молчал, хотя systemd считал сервис «active».

Слои защиты (все файлы в `deploy/`, установка — `bash /opt/spinhire/deploy/install-guard.sh`):

| Слой | Файл | Что делает |
|---|---|---|
| Роль процесса | `server/app.py` (`SPINHIRE_ROLE`), `server/worker.py` | `web` — только HTTP, без фоновых потоков; `worker` — рассылки, боты, краулер отдельным процессом; `all` — как раньше (локально, тесты) |
| Лимиты веба | `spinhire-guard.conf` → `spinhire.service.d/guard.conf` | MemoryMax 1000M (ядро убивает, systemd поднимает за 2 с), своп ≤300M, TimeoutStopSec 12, приоритет CPU/OOM выше соседей |
| Воркер | `spinhire-worker.service` | Nice 10, CPUQuota 60%, MemoryMax 700M, первый кандидат на OOM. Секреты — симлинки на drop-in'ы веб-юнита |
| Сторож | `spinhire-watchdog.sh` + `.service`/`.timer` | раз в минуту `/healthz`; два провала подряд → SIGKILL + restart; предупреждения о памяти процесса и сервера; поднимает упавший воркер. Уведомления в Telegram (`SPINHIRE_OPS_TG_CHAT`, иначе `SPINHIRE_TG_LEAD_CHAT`) и на почту (`SPINHIRE_OPS_EMAIL`) |
| Деплой с откатом | `deploy.sh` → `/opt/spinhire/deploy.sh` | после рестарта ждёт `/healthz` 90 с; нет — откат на прошлый коммит, плохой SHA в карантине (`/var/lib/spinhire/bad-deploy`), уведомление |

Проверка: `bash /opt/spinhire/deploy/spinhire-watchdog.sh status`, журналы `/var/log/spinhire-watchdog.log`,
`/var/log/spinhire-deploy.log`, `journalctl -u spinhire-worker -n 30`.
Снять карантин вручную: `rm /var/lib/spinhire/bad-deploy`. Отключить сторож: `systemctl disable --now spinhire-watchdog.timer`.
