#!/bin/bash
# авто-деплой: тянет origin/main, делает бэкап боевой БД, рестартит сервис — только при изменениях
# Живёт в /opt/spinhire/deploy.sh (root-cron */2 * * * *), это эталонная копия.
# Установка: cp /opt/spinhire/deploy/deploy.sh /opt/spinhire/deploy.sh && chmod +x /opt/spinhire/deploy.sh
cd /opt/spinhire || exit 0
git fetch origin --quiet 2>/dev/null || exit 0   # fetch не удался — origin/main устарел, ничего не делаем
LOCAL=$(git rev-parse HEAD 2>/dev/null)
REMOTE=$(git rev-parse origin/main 2>/dev/null)
[ -z "$REMOTE" ] && exit 0
[ "$LOCAL" = "$REMOTE" ] && exit 0
# только вперёд: локальный main впереди origin (деплой через bundle) — не откатывать
git merge-base --is-ancestor "$REMOTE" "$LOCAL" 2>/dev/null && exit 0
# Бэкап живой БД (WAL) — только через sqlite backup API. Раньше здесь был cp: он снимал
# файл без WAL и после reset копировал его ОБРАТНО поверх открытой базы — каждый деплой
# давал «database disk image is malformed» и мог откатить checkpoint (15.09.2026).
# База в .gitignore, git reset её не трогает, обратная запись не нужна.
/opt/spinhire/venv/bin/python -c "import sqlite3; s=sqlite3.connect('data/spinhire.db'); d=sqlite3.connect('/root/spinhire.db.bak'); s.backup(d); d.close(); s.close()" 2>/dev/null
CHANGED=$(git diff --name-only "$LOCAL" "$REMOTE" 2>/dev/null)
git reset --hard origin/main >/dev/null 2>&1
[ -s data/spinhire.db ] || cp -f /root/spinhire.db.bak data/spinhire.db 2>/dev/null
# рестарт только если менялся код сервера: контентные коммиты (статьи, YouTube-расписание,
# журналы бота) раньше перезапускали сервис до 200 раз в день и давали Googlebot окна 502
if echo "$CHANGED" | grep -qE "^(server/|requirements\\.txt|deploy/|server\\.json|data/professions\\.json)"; then
  systemctl restart spinhire.service
  echo "$(date -u +%FT%TZ) deployed+restart -> $REMOTE"
else
  echo "$(date -u +%FT%TZ) deployed (no restart, content only) -> $REMOTE"
fi
