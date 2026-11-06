from __future__ import annotations

import argparse
import os
import signal
import time

from _cli import PNPM, ROOT, exit_on_signal, load_env_file, run, spawn, stop

# Where each product's API, port, panels and log files live. Both run by default.
PRODUCTS = {
    "inmo24x7": {
        "api_dir": "apps/inmo24x7/api",
        "module": "inmo24x7_api",
        "port": "8001",
        "web": "@inmo24x7/web",
        "backoffice": "@inmo24x7/backoffice",
        "urls": ("http://localhost:5173", "http://localhost:5174"),
        "logs": ("api.log", "worker.log"),
    },
    "cuentas-claras": {
        "api_dir": "apps/cuentas-claras/api",
        "module": "cuentas_claras_api",
        "port": "8002",
        "web": "@cuentas-claras/web",
        "backoffice": "@cuentas-claras/backoffice",
        "urls": ("http://localhost:5175", "http://localhost:5176"),
        "logs": ("cc-api.log", "cc-worker.log"),
    },
}
# Where the APIs' and the workers' output is copied for the local Alloy (--observability).
DEV_LOGS = ROOT / ".dev-logs"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run each product's API, worker, panel and backoffice (both by default)."
    )
    parser.add_argument(
        "--product",
        choices=sorted(PRODUCTS),
        help="run only this product (the database and the migrations are shared)",
    )
    parser.add_argument("--seed", action="store_true", help="seed the dev accounts after migrating")
    parser.add_argument(
        "--observability",
        action="store_true",
        help="also start Loki, Alloy and Grafana (http://localhost:3000) with the APIs' logs",
    )
    args = parser.parse_args(argv)
    load_env_file(ROOT / ".env")
    signal.signal(signal.SIGTERM, exit_on_signal)
    products = [args.product] if args.product else list(PRODUCTS)

    run(["uv", "sync", "--all-packages"])
    run([*PNPM, "install", "--frozen-lockfile"])
    run(["docker", "compose", "up", "-d", "--wait", "db", "mailpit"])
    if args.observability:
        DEV_LOGS.mkdir(exist_ok=True)
        # Log lines go through a pipe: unbuffered, so they reach Grafana right away.
        os.environ["PYTHONUNBUFFERED"] = "1"
        run(["docker", "compose", "--profile", "observability", "up", "-d", "--wait"])
    # Every product's migration branch, and core's.
    run(["uv", "run", "alembic", "upgrade", "heads"])
    if args.seed:
        run(["uv", "run", "--all-packages", "python", "scripts/seed_dev.py"])

    processes = []
    for name in products:
        product = PRODUCTS[name]
        api_log, worker_log = (
            (DEV_LOGS / product["logs"][0], DEV_LOGS / product["logs"][1])
            if args.observability
            else (None, None)
        )
        api = ["uv", "--directory", product["api_dir"], "run"]
        processes += [
            spawn(
                [
                    *api,
                    "uvicorn",
                    f"{product['module']}.main:app",
                    "--reload",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    product["port"],
                ],
                tee=api_log,
            ),
            # Background jobs (each product claims only its own queue).
            spawn([*api, "python", "-m", f"{product['module']}.worker"], tee=worker_log),
            spawn([*PNPM, "--filter", product["web"], "dev"]),
            spawn([*PNPM, "--filter", product["backoffice"], "dev"]),
        ]

    for name in products:
        product = PRODUCTS[name]
        panel, backoffice = product["urls"]
        print(f"\n{name}", flush=True)
        print(f"  Panel:      {panel}", flush=True)
        print(f"  Backoffice: {backoffice}", flush=True)
        print(f"  API:        http://localhost:{product['port']}/docs", flush=True)
    print("\nMailpit:      http://localhost:8025", flush=True)
    if args.observability:
        print("Grafana:      http://localhost:3000 (admin / admin)", flush=True)

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
