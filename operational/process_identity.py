#!/usr/bin/env python3
"""Process identity shared by the operational skills: who a process is, and whether it is still that process.

    process_identity.py --self-test

A process is identified by host, boot, PID and start time; a PID alone is reused by the operating system. liveness()
answers live, dead or unknown, and never turns missing evidence into an answer: a process whose start time cannot be
read is unknown, not ended. `development-coordination` (claim holders) and `agent-handoff` (recorded jobs) carry
byte-identical generated copies of this file; change it here and regenerate (scripts/operational_sync.py).
Standard library only; macOS (`ps -o lstart=`, `kern.boottime`) and Linux (`/proc`).
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True


def process_start(pid: int) -> str | None:
    """A stable start-time token for a process, or None when it cannot be read (gone, or not visible)."""
    proc = Path(f"/proc/{pid}/stat")
    if proc.exists():
        try:
            data = proc.read_text()
            return "proc:" + data[data.rindex(")") + 2:].split()[19]
        except (OSError, ValueError, IndexError):
            return None
    try:
        r = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=10,
                           env={**os.environ, "LC_ALL": "C", "TZ": "UTC"})
    except (OSError, subprocess.SubprocessError):
        return None
    out = " ".join(r.stdout.split())
    return f"lstart:{out}" if r.returncode == 0 and out else None


def boot_id() -> str | None:
    proc = Path("/proc/sys/kernel/random/boot_id")
    if proc.exists():
        try:
            return "linux:" + proc.read_text().strip()
        except OSError:
            return None
    try:
        r = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"sec = (\d+)", r.stdout)
    return f"bsd:{m.group(1)}" if m else None


def here() -> dict:
    return {"host": socket.gethostname(), "boot": boot_id()}


def liveness(pid, start, host, boot=None, local: dict | None = None) -> tuple[str, str]:
    """("live" | "dead" | "unknown", reason) for a recorded process identity, judged from this machine."""
    local = local if local is not None else here()
    if host != local["host"]:
        return "unknown", "held on another host"
    if boot and local["boot"] and boot != local["boot"]:
        return "dead", "the host has rebooted since it was recorded"
    if pid is None or start is None:
        return "unknown", "the process identity was not recorded"
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "dead", f"process {pid} no longer exists"
    except PermissionError:
        pass                                          # exists, owned by another user: its start time decides
    except (OSError, OverflowError, TypeError) as e:
        return "unknown", f"process {pid} cannot be inspected: {e}"
    now = process_start(pid)
    if now is None:
        return "unknown", f"the start time of process {pid} cannot be read"
    if now != start:
        return "dead", f"PID {pid} now belongs to another process (reused)"
    return "live", f"process {pid} is running"


def self_test() -> list[str]:
    failures: list[str] = []
    local = here()
    me = os.getpid()
    mine = process_start(me)
    if not mine or liveness(me, mine, local["host"], local["boot"], local)[0] != "live":
        failures.append(f"this process is not live: {mine}")
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    if liveness(child.pid, "lstart:x", local["host"], None, local)[0] != "dead":
        failures.append("an exited process is not dead")
    for label, args, want in [
            ("reused PID", (me, "lstart:Thu Jan  1 00:00:00 1970", local["host"]), "dead"),
            ("another host", (me, mine, "another-host.example"), "unknown"),
            ("no identity", (None, None, local["host"]), "unknown"),
            ("rebooted", (me, mine, local["host"], "previous-boot"), "dead" if local["boot"] else "live")]:
        got = liveness(*args, local=local)[0]
        if got != want:
            failures.append(f"{label}: expected {want}, got {got}")
    saved = globals()["process_start"]
    globals()["process_start"] = lambda pid: None
    try:
        if liveness(me, mine, local["host"], None, local)[0] != "unknown":
            failures.append("an unreadable start time was not unknown")
    finally:
        globals()["process_start"] = saved
    return failures


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        found = self_test()
        for f in found:
            print("FAIL:", f)
        print("process_identity self-test: " + ("PASS" if not found else f"{len(found)} FAILED"))
        sys.exit(1 if found else 0)
    print(__doc__.split("\n\n")[1].strip())
    sys.exit(2)
