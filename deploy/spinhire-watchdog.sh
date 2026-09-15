#!/usr/bin/env bash
# Сторож SpinHire — раз в минуту по spinhire-watchdog.timer (deploy/install-guard.sh).
#
#  1. /healthz веб-процесса не отвечает два запуска подряд → SIGKILL + restart и уведомление.
#     Graceful stop зависшего event loop ждёт TimeoutStopSec, SIGKILL — мгновенный.
#  2. Память веб-процесса выше порога → предупреждение (убивает его systemd по MemoryMax,
#     сторож только сообщает, чтобы утечку заметили до того).
#  3. На сервере кончается память → предупреждение с топом процессов-соседей (раз в час):
#     дроплет общий, и чужой процесс может утащить всех в своп.
#  4. Воркер выключен/упал → поднять и сообщить.
#
# Уведомления: Telegram через бота SPINHIRE_TG_BOT_TOKEN в чат SPINHIRE_OPS_TG_CHAT
# (если не задан — в SPINHIRE_TG_LEAD_CHAT) и письмо через Resend на SPINHIRE_OPS_EMAIL.
# Окружение берётся из юнита spinhire.service (drop-in'ы) и /opt/spinhire/.env.
#
# Подкоманды:  spinhire-watchdog.sh            — обычный проход
#              spinhire-watchdog.sh notify "…" — просто отправить уведомление (зовёт deploy.sh)
#              spinhire-watchdog.sh status     — показать состояние без действий
set -u
LOG=/var/log/spinhire-watchdog.log
STATE=/run/spinhire-watchdog
URL=${SPINHIRE_WD_URL:-http://127.0.0.1:8100/healthz}
RSS_WARN_MB=${SPINHIRE_WD_RSS_MB:-700}
MEM_AVAIL_MIN_MB=${SPINHIRE_WD_MEM_MB:-300}
FAILS_TO_RESTART=2
WARMUP_SECONDS=75          # после старта сервису дают время подняться, неответ не считается
mkdir -p "$STATE"

log() { echo "$(date -u +%FT%TZ) $*" >> "$LOG"; }

load_env() {
  # Environment= из юнита и всех его drop-in'ов (там токены ботов), затем .env
  local kv
  while IFS= read -r kv; do
    [[ "$kv" =~ ^[A-Z_][A-Z0-9_]*= ]] && export "$kv"
  done < <(systemctl show spinhire.service -p Environment --value 2>/dev/null | xargs -n1 printf '%s\n' 2>/dev/null)
  if [ -r /opt/spinhire/.env ]; then
    while IFS= read -r kv; do
      [[ "$kv" =~ ^[A-Z_][A-Z0-9_]*= ]] && export "$kv"
    done < /opt/spinhire/.env
  fi
}

notify() {
  local text="🛡 SpinHire watchdog · $(hostname -s) · $(date -u +%H:%M) UTC
$1"
  local chat="${SPINHIRE_OPS_TG_CHAT:-${SPINHIRE_TG_LEAD_CHAT:-}}"
  if [ -n "${SPINHIRE_TG_BOT_TOKEN:-}" ] && [ -n "$chat" ]; then
    curl -s -m 10 -o /dev/null -X POST "https://api.telegram.org/bot${SPINHIRE_TG_BOT_TOKEN}/sendMessage" \
      --data-urlencode "chat_id=$chat" --data-urlencode "text=$text" || true
  fi
  if [ -n "${RESEND_API_KEY:-}" ]; then
    local to="${SPINHIRE_OPS_EMAIL:-timlookinar@gmail.com}"
    local from="${RESEND_FROM:-SpinHire <hello@spinhire.io>}"
    local payload
    payload=$(python3 -c 'import json,sys; print(json.dumps({"from": sys.argv[1], "to": [sys.argv[2]], "subject": sys.argv[3], "text": sys.argv[4]}))' \
      "$from" "$to" "SpinHire watchdog: $(echo "$1" | head -1 | cut -c1-80)" "$text" 2>/dev/null) || return 0
    curl -s -m 10 -o /dev/null https://api.resend.com/emails -H "Authorization: Bearer $RESEND_API_KEY" \
      -H "Content-Type: application/json" -H "User-Agent: spinhire-watchdog/1.0" -d "$payload" || true
  fi
}

probe() { curl -s -m 8 -o /dev/null -w '%{http_code}' "$URL" 2>/dev/null || echo 000; }

snapshot() {
  local pid rss
  pid=$(systemctl show spinhire.service -p MainPID --value 2>/dev/null)
  rss=$(ps -o rss= -p "${pid:-0}" 2>/dev/null | awk '{print int($1/1024)}')
  echo "load $(cut -d' ' -f1-3 /proc/loadavg) · RAM свободно $(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo) MB · своп занят $(free -m | awk '/Swap/{print $3}') MB · spinhire RSS ${rss:-?} MB"
  echo "топ по памяти: $(ps -eo rss=,comm= --sort=-rss | head -5 | awk '{printf "%s %dMB; ", $2, $1/1024}')"
}

# уведомление не чаще чем раз в N секунд на тему (файл-метка)
throttled() { # $1 тема, $2 секунд
  local f="$STATE/$1.stamp" now
  now=$(date +%s)
  if [ -f "$f" ] && [ $((now - $(cat "$f" 2>/dev/null || echo 0))) -lt "$2" ]; then return 1; fi
  echo "$now" > "$f"; return 0
}

heal() { # $1 код пробы, $2 число неудач
  local snap code2
  snap=$(snapshot)
  log "RESTART: healthz=$1 ×$2 · $snap"
  systemctl kill --kill-whom=main -s SIGKILL spinhire.service 2>/dev/null
  systemctl restart spinhire.service
  sleep 15
  code2=$(probe)
  log "after restart: healthz=$code2"
  notify "Сайт не отвечал (healthz=$1 два раза подряд). Веб-процесс перезапущен → сейчас healthz=$code2.
$snap"
  echo 0 > "$STATE/fails"
}

check_web() {
  local code fails since_start
  code=$(probe)
  if [ "$code" != "200" ]; then sleep 4; code=$(probe); fi
  if [ "$code" = "200" ]; then echo 0 > "$STATE/fails"; return; fi
  since_start=$(( $(date +%s) - $(date -d "$(systemctl show spinhire.service -p ActiveEnterTimestamp --value 2>/dev/null)" +%s 2>/dev/null || echo 0) ))
  if [ "$since_start" -ge 0 ] && [ "$since_start" -lt "$WARMUP_SECONDS" ]; then
    log "healthz=$code, но сервис стартовал ${since_start}с назад — ждём"; return
  fi
  fails=$(( $(cat "$STATE/fails" 2>/dev/null || echo 0) + 1 ))
  echo "$fails" > "$STATE/fails"
  log "healthz=$code (неудача $fails из $FAILS_TO_RESTART)"
  [ "$fails" -ge "$FAILS_TO_RESTART" ] && heal "$code" "$fails"
}

check_rss() {
  local pid rss
  pid=$(systemctl show spinhire.service -p MainPID --value 2>/dev/null)
  [ -n "$pid" ] && [ "$pid" != "0" ] || return
  rss=$(ps -o rss= -p "$pid" 2>/dev/null | awk '{print int($1/1024)}')
  [ -n "$rss" ] && [ "$rss" -gt "$RSS_WARN_MB" ] || return
  log "RSS веб-процесса $rss MB > $RSS_WARN_MB MB"
  throttled rss 1800 && notify "Веб-процесс распух до $rss MB (порог $RSS_WARN_MB, MemoryMax убьёт на $(systemctl show spinhire.service -p MemoryMax --value | awk '{printf "%d", $1/1048576}') MB).
$(snapshot)"
}

check_box() {
  local avail
  avail=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
  [ "$avail" -lt "$MEM_AVAIL_MIN_MB" ] || return
  log "на сервере свободно $avail MB"
  throttled box 3600 && notify "На сервере осталось $avail MB свободной памяти — кто-то из соседей распух, сайт рискует уехать в своп.
$(snapshot)"
}

check_worker() {
  systemctl is-enabled -q spinhire-worker.service 2>/dev/null || return
  systemctl is-active -q spinhire-worker.service && return
  local st; st=$(systemctl is-active spinhire-worker.service)
  log "воркер в состоянии $st — перезапуск"
  systemctl restart spinhire-worker.service
  throttled worker 1800 && notify "Фоновый воркер был в состоянии «$st», перезапущен. Сайт не пострадал."
}

case "${1:-run}" in
  notify) load_env; notify "${2:-(пусто)}" ;;
  status) echo "healthz=$(probe) · fails=$(cat "$STATE/fails" 2>/dev/null || echo 0) · worker=$(systemctl is-active spinhire-worker.service 2>/dev/null)"; snapshot ;;
  run)    load_env; check_web; check_rss; check_box; check_worker ;;
  *)      echo "usage: $0 [run|status|notify TEXT]"; exit 2 ;;
esac
