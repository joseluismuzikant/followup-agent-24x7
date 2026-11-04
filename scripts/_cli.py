from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import IO

ROOT = Path(__file__).resolve().parents[1]
PNPM = ["corepack", "pnpm"]


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def run(command: Sequence[str]) -> None:
    command = list(command)
    print(f"$ {' '.join(command)}", flush=True)
    if os.name == "nt":
        subprocess.run(
            subprocess.list2cmdline(command),
            shell=True,
            check=True,
            cwd=ROOT,
        )
    else:
        subprocess.run(command, check=True, cwd=ROOT)


def _copy_lines(source: IO[str], log_path: Path) -> None:
    with log_path.open("a", encoding="utf-8") as log:
        for line in source:
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
            log.flush()


def spawn(command: Sequence[str], tee: Path | None = None) -> subprocess.Popen:
    """Starts a long-running process. With `tee`, its output also goes to that file (for the
    local Grafana: scripts/dev.py --observability)."""
    command = list(command)
    output = {"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT, "text": True} if tee else {}
    if os.name == "nt":
        process = subprocess.Popen(
            subprocess.list2cmdline(command),
            shell=True,
            cwd=ROOT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            **output,
        )
    else:
        process = subprocess.Popen(command, cwd=ROOT, start_new_session=True, **output)
    if tee and process.stdout is not None:
        threading.Thread(target=_copy_lines, args=(process.stdout, tee), daemon=True).start()
    return process


def stop(processes: Sequence[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is not None:
            continue
        try:
            if os.name == "nt":
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            process.terminate()

    for process in processes:
        if process.poll() is not None:
            continue
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def exit_on_signal(signum: int, _frame: object) -> None:
    sys.exit(128 + signum)
