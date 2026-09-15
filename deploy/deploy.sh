#!/bin/bash
# Авто-деплой SpinHire. Root-cron на проде: */2 * * * * /opt/spinhire/deploy.sh >> /var/log/spinhire-deploy.log
# Устанавливается копией (deploy/install-guard.sh): cp deploy/deploy.sh /opt/spinhire/deploy.sh
#
#  - тянет origin/main, только вперёд (локальный main впереди — bundle-деплой, не откатывать);
#  - рестартит сервисы только при изменении кода сервера, контент (статьи, журналы) — без рестарта;
#  - после рестарта ждёт /healthz; не поднялся за 90 с → откат на прошлый коммит, карантин
#    плохого SHA (не деплоить его повторно) и уведомление через сторож.
cd /opt/spinhire || exit 0
exec 9>/run/spinhire-deploy.lock
flock -n 9 || exit 0                         # прошлый запуск ещё идёт (ждёт healthz)
BAD=/var/lib/spinhire/bad-deploy             # SHA коммита, который положил сайт
HEALTH=http://127.0.0.1:8100/healthz
now() { date -u +%FT%TZ; }
probe() { curl -s -m 8 -o /dev/null -w '%{http_code}' "$HEALTH" 2>/dev/null || echo 000; }
restart_all() {
  systemctl restart spinhire.service
  systemctl is-enabled -q spinhire-worker.service 2>/dev/null && systemctl restart spinhire-worker.service
}
healthy() { local i; for i in $(seq 1 18); do sleep 5; [ "$(probe)" = "200" ] && return 0; done; return 1; }

git fetch origin --quiet 2>/dev/null || exit 0   # fetch не удался — origin/main устарел, ничего не делаем
LOCAL=$(git rev-parse HEAD 2>/dev/null)
REMOTE=$(git rev-parse origin/main 2>/dev/null)
[ -z "$REMOTE" ] && exit 0
[ "$LOCAL" = "$REMOTE" ] && exit 0
git merge-base --is-ancestor "$REMOTE" "$LOCAL" 2>/dev/null && exit 0
if [ -f "$BAD" ] && [ "$(cat "$BAD")" = "$REMOTE" ]; then exit 0; fi   # карантин: ждём следующий коммит

CHANGED=$(git diff --name-only "$LOCAL" "$REMOTE" 2>/dev/null)
# Бэкап живой БД (WAL) — только через sqlite backup API. Раньше здесь был cp: он снимал файл
# без WAL и после reset копировал его ОБРАТНО поверх открытой базы — каждый деплой давал
# «database disk image is malformed» и мог откатить checkpoint (15.09.2026).
# База в .gitignore, git reset её не трогает; копию возвращаем только если файла вдруг нет.
/opt/spinhire/venv/bin/python -c "import sqlite3; s=sqlite3.connect('data/spinhire.db'); d=sqlite3.connect('/root/spinhire.db.bak'); s.backup(d); d.close(); s.close()" 2>/dev/null
git reset --hard origin/main >/dev/null 2>&1
[ -s data/spinhire.db ] || cp -f /root/spinhire.db.bak data/spinhire.db 2>/dev/null

if ! echo "$CHANGED" | grep -qE "^(server/|requirements\.txt|deploy/|server\.json|data/professions\.json)"; then
  echo "$(now) deployed (no restart, content only) -> $REMOTE"; exit 0
fi
echo "$CHANGED" | grep -qE "^requirements\.txt" && ./venv/bin/pip install -q -r requirements.txt >/dev/null 2>&1
restart_all
if healthy; then
  echo "$(now) deployed+restart -> $REMOTE"; rm -f "$BAD"; exit 0
fi

# сайт не поднялся — откат на прошлый коммит, карантин нового
mkdir -p "$(dirname "$BAD")"; echo "$REMOTE" > "$BAD"
git reset --hard "$LOCAL" >/dev/null 2>&1
restart_all
sleep 20
CODE=$(probe)
echo "$(now) ROLLBACK: $REMOTE не поднялся (healthz≠200 за 90 с), вернулись на $LOCAL, сейчас healthz=$CODE"
/opt/spinhire/deploy/spinhire-watchdog.sh notify "Деплой ${REMOTE:0:8} не поднялся (healthz не ответил 200 за 90 с). Откатились на ${LOCAL:0:8}, сейчас healthz=$CODE. Коммит в карантине — следующий пуш в main задеплоится как обычно." 2>/dev/null
exit 1
