#!/usr/bin/env bash
# Безопасно положить секрет в окружение сервиса SpinHire (не в git, не в историю shell).
# Запуск на проде:  bash /opt/spinhire/deploy/set-secret.sh STRIPE_SECRET_KEY
# Значение вводится скрытно с клавиатуры. Файл виден только root. Сервис перезапускается.
set -euo pipefail
NAME="${1:?usage: set-secret.sh VAR_NAME}"
FILE=/etc/systemd/system/spinhire.service.d/payments.conf
read -r -s -p "Введите значение для $NAME (ввод скрыт): " VALUE; echo
[ -n "$VALUE" ] || { echo "пусто — ничего не записано"; exit 1; }
mkdir -p "$(dirname "$FILE")"; touch "$FILE"; chmod 600 "$FILE"
grep -q '^\[Service\]' "$FILE" || printf '[Service]\n' >> "$FILE"
# заменить существующую строку или добавить новую
if grep -q "^Environment=$NAME=" "$FILE"; then
  python3 - "$FILE" "$NAME" "$VALUE" <<'PY'
import sys; f,n,v=sys.argv[1:]
lines=[l for l in open(f).read().splitlines()]
out=[f"Environment={n}={v}" if l.startswith(f"Environment={n}=") else l for l in lines]
open(f,"w").write("\n".join(out)+"\n")
PY
else
  printf 'Environment=%s=%s\n' "$NAME" "$VALUE" >> "$FILE"
fi
systemctl daemon-reload && systemctl restart spinhire
sleep 3 && systemctl is-active spinhire && echo "$NAME сохранён, сервис перезапущен"
