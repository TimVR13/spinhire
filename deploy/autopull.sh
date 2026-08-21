#!/usr/bin/env bash
# Вариант «сервер сам тянет обновления» — без ключей в GitHub.
# Каждый запуск: сравнить локальный main с origin/main; если появились новые
# коммиты — обновиться и перезапустить spinhire. Ставится как systemd .timer
# (каждые 2 минуты) — см. deploy/spinhire-autopull.service/.timer.
set -euo pipefail

REPO=/opt/spinhire
cd "$REPO"

git fetch --quiet origin main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
  exit 0   # изменений нет
fi

echo "[$(date -u +%FT%TZ)] update $LOCAL -> $REMOTE"
git reset --hard origin/main
./venv/bin/pip install -q -r requirements.txt || true
systemctl restart spinhire
echo "[$(date -u +%FT%TZ)] deployed $(git rev-parse --short HEAD)"
