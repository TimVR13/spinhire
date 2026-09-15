# -*- coding: utf-8 -*-
"""Фоновый воркер SpinHire — отдельный процесс для всего, что не отвечает на HTTP.

Запуск: SPINHIRE_ROLE=worker python -m server.worker  (systemd: deploy/spinhire-worker.service).

Импорт server.app с ролью worker поднимает планировщики рассылок и ботов — они стартуют на
уровне модуля под флагом RUNS_BACKGROUND, — а start_background_threads() добавляет суточный
краулер и (по флагу) прогрев кластеров. Веб-процесс с SPINHIRE_ROLE=web этих потоков не
запускает, поэтому тяжёлая фоновая работа не держит GIL веб-сервера и не раздувает его память,
а systemd режет воркеру CPU и память отдельно. Оба процесса делят одну SQLite в режиме WAL.

Миграции схемы делает веб на старте; воркер их не гоняет, а ждёт, пока веб ответит на /healthz.
"""
import os
import sys
import threading
import time
import urllib.request

os.environ.setdefault("SPINHIRE_ROLE", "worker")
if os.environ["SPINHIRE_ROLE"].strip().lower() != "worker":
    sys.exit("server.worker запускается только с SPINHIRE_ROLE=worker")

from server import app as web  # noqa: E402  (планировщики стартуют при импорте)

HEALTH = os.environ.get("SPINHIRE_WEB_HEALTH", "http://127.0.0.1:8100/healthz")


def wait_for_web(timeout: float = 120.0) -> bool:
    """Даём вебу первому применить миграции; без веба (локально) просто идём дальше."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(5)
    return False


def main() -> None:
    print(f"[worker] pid {os.getpid()}: фоновые задачи SpinHire (роль {web.ROLE})", flush=True)
    if not wait_for_web():
        print("[worker] веб не ответил на /healthz за 2 минуты — стартуем без него", flush=True)
    web.start_background_threads()
    names = sorted(t.name for t in threading.enumerate() if t is not threading.current_thread())
    print(f"[worker] потоки: {', '.join(names) or 'нет'}", flush=True)
    threading.Event().wait()


if __name__ == "__main__":
    main()
