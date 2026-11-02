from __future__ import annotations

import argparse
import signal
import time

from _cli import PNPM, ROOT, exit_on_signal, load_env_file, run, spawn, stop

API_DIR = "apps/inmo24x7/api"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the API, the panel and the backoffice.")
    parser.add_argument("--seed", action="store_true", help="seed the dev accounts after migrating")
    args = parser.parse_args(argv)
    load_env_file(ROOT / ".env")
    signal.signal(signal.SIGTERM, exit_on_signal)

    run(["uv", "sync", "--all-packages"])
    run([*PNPM, "install", "--frozen-lockfile"])
    run(["docker", "compose", "up", "-d", "--wait", "db"])
    run(["uv", "run", "alembic", "upgrade", "head"])
    if args.seed:
        run(["uv", "run", "--all-packages", "python", "scripts/seed_dev.py"])

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
