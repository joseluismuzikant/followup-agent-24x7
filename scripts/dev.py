from __future__ import annotations

import os
import signal
import time
from pathlib import Path

from _cli import PNPM, ROOT, exit_on_signal, run, spawn, stop

API_DIR = "apps/inmo24x7/api"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def main() -> int:
    load_env_file(ROOT / ".env")
    signal.signal(signal.SIGTERM, exit_on_signal)

    run(["uv", "sync", "--all-packages"])
    run([*PNPM, "install", "--frozen-lockfile"])
    run(["docker", "compose", "up", "-d", "--wait", "db"])
    run(["uv", "--directory", API_DIR, "run", "alembic", "upgrade", "head"])

    processes = [
        spawn(
            [
                "uv",
                "--directory",
                API_DIR,
                "run",
                "uvicorn",
                "inmo24x7_api.main:app",
                "--reload",
                "--host",
                "0.0.0.0",
                "--port",
                "8001",
            ]
        ),
        spawn([*PNPM, "--filter", "@inmo24x7/web", "dev"]),
        spawn([*PNPM, "--filter", "@inmo24x7/backoffice", "dev"]),
    ]

    print("\nPanel:      http://localhost:5173", flush=True)
    print("Backoffice: http://localhost:5174", flush=True)
    print("API:        http://localhost:8001/docs", flush=True)

    exit_code = 0
    try:
        while True:
            for process in processes:
                code = process.poll()
                if code is not None:
                    exit_code = code if code > 0 else 1
                    print("Un proceso se detuvo. Cerrando el resto.", flush=True)
                    return exit_code
            time.sleep(0.5)
    except KeyboardInterrupt:
        return 0
    finally:
        stop(processes)


if __name__ == "__main__":
    raise SystemExit(main())
