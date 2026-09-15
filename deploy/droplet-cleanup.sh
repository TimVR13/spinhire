#!/bin/bash
# Еженедельная уборка дроплета 165.232.79.152 (общий сервер SpinHire/TRX/COEX/Quantium/PostForge).
# Установка: ln -sf /opt/spinhire/deploy/droplet-cleanup.sh /etc/cron.weekly/droplet-cleanup
# Разово:    bash /opt/spinhire/deploy/droplet-cleanup.sh
# Журнал:    /var/log/droplet-cleanup.log
#
# 15.09.2026 диск был на 93%: 40 старых SHA-тегов образов TRX (деплой тянет новый тег
# и не чистит), 12 ГБ кэша docker-сборок, 1.8 ГБ journald, логи контейнеров без ротации.
# Удаляет только то, что не привязано ни к одному контейнеру. Тома docker не трогает никогда.
set -u
LOG=/var/log/droplet-cleanup.log
exec >>"$LOG" 2>&1
echo "== $(date -u +%FT%TZ) start: $(df -h / | awk 'NR==2{print $3" of "$2", "$5}')"

# 1. SHA-теги образов TRX старше 3 дней, которые не использует ни один контейнер
used=$(docker ps -a --format '{{.Image}}' | sort -u)
now=$(date +%s)
for ref in $(docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^ghcr.io/timvr13/trx-(app|ops|web|crm|qa):[0-9a-f]{40}$'); do
  echo "$used" | grep -qx "$ref" && continue
  created=$(docker image inspect --format '{{.Created}}' "$ref" 2>/dev/null) || continue
  age=$(( (now - $(date -d "$created" +%s)) / 86400 ))
  if [ "$age" -ge 3 ]; then
    docker rmi "$ref" >/dev/null 2>&1 && echo "rmi $ref (${age}d)"
  fi
done

# 2. Безымянные слои, остановленные контейнеры старше суток, кэш сборок старше недели
docker image prune -f | tail -1
docker container prune -f --filter until=24h | tail -1
docker builder prune -f --filter until=168h | tail -1

# 3. Логи контейнеров: json-file без ротации растёт бесконечно (daemon.json задаёт
#    max-size только новым контейнерам) — обрезаем всё, что больше 50 МБ
find /var/lib/docker/containers -name '*-json.log' -size +50M -print -exec truncate -s 0 {} \;

# 4. Системное
journalctl --vacuum-size=300M 2>&1 | tail -1
apt-get clean
rm -rf /root/.npm/_cacache /root/.cache/pip 2>/dev/null

echo "== $(date -u +%FT%TZ) done:  $(df -h / | awk 'NR==2{print $3" of "$2", "$5}')"
