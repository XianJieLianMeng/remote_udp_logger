#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import os
import re
import threading
from pathlib import Path


DEFAULT_LOG_DIR_NAME = "XbellUdpLogs"
DEFAULT_KEEP_SESSION_FILES = 100
KEEP_FILES_ENV_VAR = "XBELL_UDP_LOG_KEEP_FILES"
_SESSION_FILE_PATTERN = re.compile(r"^[A-Za-z0-9_]+_\d{8}_\d{6}_\d{6}\.(log|jsonl)$")


def get_default_log_dir() -> Path:
    log_dir = Path.home() / DEFAULT_LOG_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def prune_old_session_files(directory: Path | None = None, keep_files: int | None = None) -> int:
    """Delete the oldest session files beyond the retention limit.

    Only files matching this module's timestamped session naming pattern are
    considered, so user files in the log directory are never touched. Set the
    XBELL_UDP_LOG_KEEP_FILES environment variable to change the limit, or to
    0 (or a negative number) to disable pruning entirely.
    """
    base_dir = directory or get_default_log_dir()
    if keep_files is None:
        try:
            keep_files = int(os.environ.get(KEEP_FILES_ENV_VAR, DEFAULT_KEEP_SESSION_FILES))
        except ValueError:
            keep_files = DEFAULT_KEEP_SESSION_FILES
    if keep_files <= 0:
        return 0

    try:
        candidates = sorted(
            (
                path
                for path in base_dir.iterdir()
                if path.is_file() and _SESSION_FILE_PATTERN.match(path.name)
            ),
            key=lambda path: path.stat().st_mtime,
        )
    except OSError:
        return 0

    removed = 0
    for path in candidates[: max(0, len(candidates) - keep_files)]:
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


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
        prune_old_session_files(directory)
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
