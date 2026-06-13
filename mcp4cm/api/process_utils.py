from __future__ import annotations

import os
import signal
import subprocess

from mcp4cm.api.state import LOG


def pids_on_port(port: int) -> list[int]:
    command = ["lsof", "-ti", f":{port}"]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        LOG.warning("lsof_not_found port=%s", port)
        return []
    if completed.returncode not in {0, 1}:
        LOG.warning("lsof_failed port=%s returncode=%s stderr=%s", port, completed.returncode, completed.stderr.strip())
        return []
    pids: list[int] = []
    for line in completed.stdout.splitlines():
        try:
            pids.append(int(line.strip()))
        except ValueError:
            LOG.warning("invalid_lsof_pid port=%s value=%s", port, line)
    return pids


def kill_processes_on_port(port: int) -> list[int]:
    pids = pids_on_port(port)
    current_pid = os.getpid()
    killed: list[int] = []
    for pid in pids:
        if pid == current_pid:
            continue
        LOG.warning("killing_process_on_port port=%s pid=%s signal=SIGKILL", port, pid)
        os.kill(pid, signal.SIGKILL)
        killed.append(pid)
    return killed
