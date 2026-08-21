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
