#!/usr/bin/env bash
# Ставит защиту SpinHire на прод (идемпотентно, под root, после git pull кода с SPINHIRE_ROLE):
#   1. guard.conf — лимиты памяти/CPU веб-процесса, роль web, быстрый SIGKILL зависшего;
#   2. spinhire-worker.service — фон отдельным процессом, секреты веб-юнита через симлинки;
#   3. spinhire-watchdog.timer — сторож раз в минуту;
#   4. /opt/spinhire/deploy.sh — деплой с проверкой /healthz и откатом.
# Запуск: ssh -i ~/.ssh/coex root@165.232.79.152 'bash /opt/spinhire/deploy/install-guard.sh'
set -euo pipefail
SRC=/opt/spinhire/deploy
SD=/etc/systemd/system
mkdir -p "$SD/spinhire.service.d" "$SD/spinhire-worker.service.d" /var/lib/spinhire

install -m 644 "$SRC/spinhire-guard.conf" "$SD/spinhire.service.d/guard.conf"
rm -f "$SD/spinhire.service.d/limits.conf"       # прежний drop-in лимитов — теперь всё в guard.conf
install -m 644 "$SRC/spinhire-worker.service" "$SD/spinhire-worker.service"
# секреты веб-юнита (токены ботов, ключи, .env) — те же файлы для воркера, кроме socket/guard
for f in "$SD"/spinhire.service.d/*.conf; do
  case "$(basename "$f")" in socket.conf|guard.conf) continue;; esac
  ln -sfn "$f" "$SD/spinhire-worker.service.d/$(basename "$f")"
done
install -m 644 "$SRC/spinhire-watchdog.service" "$SRC/spinhire-watchdog.timer" "$SD/"
chmod +x "$SRC/spinhire-watchdog.sh" "$SRC/deploy.sh"
[ -f /opt/spinhire/deploy.sh ] && cp -f /opt/spinhire/deploy.sh "/opt/spinhire/deploy.sh.bak-$(date -u +%Y%m%d)"
install -m 755 "$SRC/deploy.sh" /opt/spinhire/deploy.sh

systemctl daemon-reload
systemctl restart spinhire.service                    # теперь как SPINHIRE_ROLE=web, с лимитами
systemctl enable --now spinhire-worker.service
systemctl enable --now spinhire-watchdog.timer
sleep 12
echo "--- состояние"
systemctl is-active spinhire.socket spinhire.service spinhire-worker.service spinhire-watchdog.timer | paste -sd' '
curl -s -m 10 -o /dev/null -w "healthz %{http_code} %{time_total}s\n" http://127.0.0.1:8100/healthz
systemctl show spinhire.service -p MemoryMax -p MemorySwapMax -p CPUWeight -p OOMScoreAdjust -p TimeoutStopUSec -p Environment | sed 's/SPINHIRE_SECRET=[^ ]*/SPINHIRE_SECRET=…/;s/TOKEN=[^ ]*/TOKEN=…/g;s/KEY=[^ ]*/KEY=…/g;s/PASSWORD=[^ ]*/PASSWORD=…/'
echo "--- воркер"
journalctl -u spinhire-worker.service -n 8 --no-pager -o cat
