from __future__ import annotations

import os
import signal
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

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


def spawn(command: Sequence[str]) -> subprocess.Popen:
    command = list(command)
    if os.name == "nt":
        return subprocess.Popen(
            subprocess.list2cmdline(command),
            shell=True,
            cwd=ROOT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    return subprocess.Popen(command, cwd=ROOT, start_new_session=True)


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
