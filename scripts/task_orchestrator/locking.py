from __future__ import annotations

from contextlib import AbstractContextManager
import json
import os
from pathlib import Path
import socket
import time


class LockBusy(RuntimeError):
    pass


class ProcessLock(AbstractContextManager):
    def __init__(self, path: Path, stale_after: int):
        self.path = path
        self.stale_after = stale_after
        self.held = False

    @staticmethod
    def _alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"pid": os.getpid(), "host": socket.gethostname(), "created": time.time()}
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle)
                    handle.flush()
                    os.fsync(handle.fileno())
                self.held = True
                return
            except FileExistsError:
                try:
                    current = json.loads(self.path.read_text(encoding="utf-8"))
                    stale = time.time() - float(current["created"]) > self.stale_after and not self._alive(int(current["pid"]))
                except Exception:
                    stale = time.time() - self.path.stat().st_mtime > self.stale_after
                if not stale:
                    raise LockBusy(f"orchestrator lock is active: {self.path}")
                stale_name = self.path.with_name(self.path.name + f".stale.{int(time.time())}")
                os.replace(self.path, stale_name)
        raise LockBusy("could not acquire lock")

    def release(self) -> None:
        if self.held:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            self.held = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False
