#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import threading
from pathlib import Path


DEFAULT_LOG_DIR_NAME = "XbellUdpLogs"


def get_default_log_dir() -> Path:
    log_dir = Path.home() / DEFAULT_LOG_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def build_session_log_path(
    prefix: str,
    directory: Path | None = None,
    suffix: str = ".log",
) -> Path:
    base_dir = directory or get_default_log_dir()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    normalized_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    return base_dir / f"{prefix}_{stamp}{normalized_suffix}"


class UdpLogJournal:
    def __init__(self, prefix: str, directory: Path | None = None, suffix: str = ".log") -> None:
        self._lock = threading.Lock()
        self._fallback_lines: list[str] = []
        self._path = build_session_log_path(prefix, directory, suffix)
        self._handle = None
        try:
            self._handle = self._path.open("a+", encoding="utf-8")
            self._handle.seek(0, 2)
        except OSError:
            self._handle = None

    @property
    def path(self) -> Path:
        return self._path

    def append(self, line: str) -> None:
        if not line:
            return

        entry = line if line.endswith("\n") else f"{line}\n"
        with self._lock:
            if self._handle is not None:
                try:
                    self._handle.write(entry)
                    self._handle.flush()
                    return
                except OSError:
                    try:
                        self._handle.close()
                    except OSError:
                        pass
                    self._handle = None

            self._fallback_lines.append(entry)

    def read_text(self) -> str:
        with self._lock:
            if self._handle is not None:
                try:
                    self._handle.flush()
                    self._handle.seek(0)
                    data = self._handle.read()
                    self._handle.seek(0, 2)
                    return data + "".join(self._fallback_lines)
                except OSError:
                    pass

            if self._path.exists():
                try:
                    return self._path.read_text(encoding="utf-8") + "".join(self._fallback_lines)
                except OSError:
                    pass

            return "".join(self._fallback_lines)

    def close(self) -> None:
        with self._lock:
            if self._handle is None:
                return
            try:
                self._handle.flush()
            except OSError:
                pass
            try:
                self._handle.close()
            except OSError:
                pass
            self._handle = None
