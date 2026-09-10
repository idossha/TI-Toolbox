"""Attribute sampled focus/windows to a test process tree, without reading content.

The launcher uses a fresh session and a pipe gate: its root is observed before it
can execute the command. Descendants are tracked by PID plus microsecond birth
time, including detached/reparented descendants. An unseen orphan or a missing
process record is unknown, never evidence that a window was unrelated.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def _processes(records):
    if not isinstance(records, list) or not records:
        raise ValueError("missing process inventory")
    result = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("invalid process record")
        for field in ("pid", "ppid", "pgid"):
            if type(record.get(field)) is not int or record[field] < (
                1 if field == "pid" else 0
            ):
                raise ValueError("invalid process identity")
        if not isinstance(record.get("start"), str) or not record["start"].isdigit():
            raise ValueError("missing process birth time")
        if record["pid"] in result:
            raise ValueError("duplicate process identity")
        result[record["pid"]] = record
    return result


def _identity(process):
    return process["pid"], process["start"]


class Attribution:
    """Classify observed processes using a baseline and the isolated command root."""

    def __init__(self, baseline: list[dict], root_pid: int):
        self.unrelated = {_identity(p) for p in _processes(baseline).values()}
        self.owned: set[tuple[int, str]] = set()
        self.root_pid = root_pid
        self.root_identity: tuple[int, str] | None = None
        self.pending: list[tuple[int, str]] = []

    def check(self, sample: dict) -> tuple[int, list[str]]:
        """Return 0 for quiet, 1 for a test window/focus, 2 for unknown evidence."""
        try:
            processes = _processes(sample.get("processes"))
            focus = sample.get("frontmost")
            windows = sample.get("windows")
            if (
                not isinstance(focus, dict)
                or type(focus.get("pid")) is not int
                or not isinstance(focus.get("name"), str)
            ):
                raise ValueError("unreadable frontmost PID/name")
            if not isinstance(windows, list):
                raise ValueError("unreadable window list")
            for window in windows:
                if not isinstance(window, dict) or any(
                    type(window.get(key)) is not int for key in ("pid", "id", "layer")
                ):
                    raise ValueError("unreadable window owner PID")
        except (AttributeError, ValueError) as exc:
            return 2, [f"ERROR: {exc}"]

        current_root = processes.get(self.root_pid)
        if self.root_identity is None and current_root is not None:
            # First observation is made while the genuine root is held at the
            # startup gate. Never rebind this PID to a later process birth.
            self.root_identity = _identity(current_root)
        root_alive = (
            current_root is not None and _identity(current_root) == self.root_identity
        )
        cache = {}

        def classify(pid, trail=frozenset()):
            if pid in cache:
                return cache[pid]
            process = processes.get(pid)
            if not process or pid in trail:
                return "unknown"
            identity = _identity(process)
            if (
                identity == self.root_identity
                or (root_alive and process["pgid"] == self.root_pid)
                or identity in self.owned
            ):
                kind = "test"
            elif identity in self.unrelated:
                kind = "unrelated"
            elif process["ppid"] <= 1:
                # launchd adoption is not an ancestry trace: an unobserved test
                # child could have detached and lost its parent before sampling.
                kind = "unknown"
            else:
                parent = processes.get(process["ppid"])
                if parent and int(parent["start"]) <= int(process["start"]):
                    kind = classify(process["ppid"], trail | {pid})
                else:
                    kind = "unknown"
            cache[pid] = kind
            if kind == "test":
                self.owned.add(identity)
            elif kind == "unrelated":
                self.unrelated.add(identity)
            return kind

        # Track even descendants without windows, before their parent can exit.
        for pid in processes:
            classify(pid)
        # A newly orphaned process without a window could be an unobserved test
        # child. It must drain, or prevent a quiet receipt after command exit.
        self.pending = [
            (pid, cache[pid])
            for pid in processes
            if cache[pid] in ("test", "unknown")
            and _identity(processes[pid]) != self.root_identity
        ]
        status = 0
        messages = []
        events = [(focus["pid"], f"focus name={focus['name']!r}")]
        events.extend(
            (
                w["pid"],
                f"window id={w['id']} layer={w['layer']} owner={w.get('owner', '?')!r}",
            )
            for w in windows
        )
        for pid, detail in events:
            kind = classify(pid)
            if kind == "unknown":
                status = 2
                messages.append(f"ERROR: unknown ancestry pid={pid} {detail}")
            elif kind == "test":
                status = max(status, 1)
                messages.append(f"FAIL: test descendant pid={pid} {detail}")
            else:
                label = detail if detail.startswith("focus ") else "visible window"
                messages.append(f"note: unrelated pid={pid} {label}")
        return status, messages


def _snapshot(binary: Path) -> dict:
    result = subprocess.run(
        [str(binary)], check=True, capture_output=True, text=True, timeout=10
    )
    return json.loads(result.stdout)


def main() -> int:
    """Launch after a metadata baseline, sample through exit, and report attribution."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    command = command or ["npm", "run", "e2e"]
    errors = (OSError, ValueError, subprocess.SubprocessError)
    try:
        baseline = _snapshot(args.snapshot)
        baseline_processes = _processes(baseline.get("processes"))
        precheck = Attribution(list(baseline_processes.values()), -1)
        status, messages = precheck.check(baseline)
        if status:
            raise ValueError("; ".join(messages))
    except errors as exc:
        print(f"e2e-quiet-check: ERROR — cannot acquire baseline: {exc}", flush=True)
        return 2

    read_fd, write_fd = os.pipe()
    child = None
    released = False
    seen = set()
    samples = 0
    overall = 0
    exit_seen_at = None
    # The fresh session covers early/crashed apps without any helper-side logs.
    gate = "import os,sys; fd=int(sys.argv[1]); ready=os.read(fd,1); os.close(fd); sys.exit(125) if ready!=b'1' else os.execvp(sys.argv[2],sys.argv[2:])"
    try:
        child = subprocess.Popen(
            [sys.executable, "-c", gate, str(read_fd), *command],
            pass_fds=(read_fd,),
            start_new_session=True,
        )
        os.close(read_fd)
        read_fd = -1
        guard = Attribution(list(baseline_processes.values()), child.pid)
        initial = _snapshot(args.snapshot)
        if child.pid not in _processes(initial.get("processes")):
            raise ValueError("command root was not observed before execution")
        initial_status, _ = guard.check(initial)
        if initial_status:
            raise ValueError("startup metadata could not be attributed")
        print(
            f"e2e-quiet-check: command root pid={child.pid}; frontmost before={baseline['frontmost']}",
            flush=True,
        )
        os.write(write_fd, b"1")
        os.close(write_fd)
        write_fd = -1
        released = True
        while True:
            # Observe exit BEFORE acquiring its final inventory. A snapshot taken
            # before poll() could miss a child created just as the root exits.
            command_exited = child.poll() is not None
            if command_exited and exit_seen_at is None:
                exit_seen_at = time.monotonic()
            try:
                sample = _snapshot(args.snapshot)
                status, messages = guard.check(sample)
                samples += 1
                overall = max(overall, status)
                for message in messages:
                    if message not in seen:
                        print(f"e2e-quiet-check: {message}", flush=True)
                        seen.add(message)
            except errors as exc:
                overall = 2
                status = 2
                print(f"e2e-quiet-check: ERROR — unreadable sample: {exc}", flush=True)
            if command_exited:
                if status == 2:
                    break  # Already an honest failure; inventory is not trustworthy.
                if not guard.pending:
                    break
                if time.monotonic() - exit_seen_at >= 5:
                    overall = 2
                    print(
                        f"e2e-quiet-check: ERROR — unresolved processes after exit: {guard.pending}",
                        flush=True,
                    )
                    break
            time.sleep(0.5)
        result = child.wait()
        print(
            f"e2e-quiet-check: command exited {result}; {samples} attributed samples",
            flush=True,
        )
        if samples == 0:
            overall = 2
        if overall == 0 and result == 0:
            print(
                "e2e-quiet-check: PASS — no test window or focus observed in samples (0.5 s polling)",
                flush=True,
            )
        return overall or (result if result >= 0 else 128 - result)
    except errors as exc:
        print(f"e2e-quiet-check: ERROR — {exc}", flush=True)
        return 2
    finally:
        for fd in (read_fd, write_fd):
            if fd >= 0:
                os.close(fd)
        if child is not None and child.poll() is None:
            # Only our new session. A failed startup gate must not leave a test
            # command running unobserved; interruption likewise owns this tree.
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)
        if not released:
            print("e2e-quiet-check: command was not released", flush=True)


if __name__ == "__main__":
    sys.exit(main())
