#!/usr/bin/env python3
from __future__ import annotations

import re
import json
from dataclasses import dataclass
from typing import Any


REMOTE_LOG_HEADER_RE = re.compile(r"^\[(?P<header>(?:imei|device|id)=[^\]]+)\]\s*")
REMOTE_LOG_FIELD_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*)=([^ \]]+)")
XBELL_FULL_RE = re.compile(
    r"^(?P<level>[EWIDV])\s+\[(?P<timestamp>[^\]]+)\]\[(?P<script>[^\]]+)\]"
    r"\[(?P<feature>[^\]]+)\]\s*(?P<message>.*)$"
)
XBELL_COMPACT_RE = re.compile(
    r"^(?P<level>[EWIDV])\s+\[(?P<feature>[^\]]+)\]\s*(?P<message>.*)$"
)
ESP_IDF_RE = re.compile(
    r"^(?P<level>[EWIDV])\s+\((?P<timestamp>\d+)\)\s+"
    r"(?P<feature>[^:]+):\s*(?P<message>.*)$"
)


@dataclass(frozen=True)
class UdpLogRecord:
    text: str
    source: str = "-"
    imei: str = "-"
    sequence: int | None = None
    level: str = ""
    timestamp: str = ""
    script: str = ""
    feature: str = ""
    message: str = ""

    def compact_text(self) -> str:
        suffix = "\n" if self.text.endswith("\n") else ""
        if self.level and self.feature:
            if not self.message:
                return f"{self.level} [{self.feature}]{suffix}"
            return f"{self.level} [{self.feature}] {self.message}{suffix}"
        return self.text

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "imei": self.imei,
            "sequence": self.sequence,
            "level": self.level,
            "timestamp": self.timestamp,
            "script": self.script,
            "feature": self.feature,
            "message": self.message,
            "text": self.text.rstrip("\r\n"),
        }


def parse_udp_log_line(text: str, source: str = "-") -> UdpLogRecord:
    line = text if text.endswith("\n") else f"{text}\n"
    body = line.rstrip("\r\n")

    imei = "-"
    sequence: int | None = None
    header_match = REMOTE_LOG_HEADER_RE.match(body)
    if header_match:
        fields = dict(REMOTE_LOG_FIELD_RE.findall(header_match.group("header")))
        imei = fields.get("imei") or fields.get("device") or fields.get("id") or "-"
        sequence_text = fields.get("seq") or fields.get("sequence")
        if sequence_text is not None:
            try:
                sequence = int(sequence_text)
            except ValueError:
                sequence = None
        body = body[header_match.end():]

    for pattern in (XBELL_FULL_RE, XBELL_COMPACT_RE, ESP_IDF_RE):
        match = pattern.match(body)
        if match:
            groups = match.groupdict(default="")
            parsed_text = body + "\n"
            return UdpLogRecord(
                text=parsed_text,
                source=source,
                imei=imei,
                sequence=sequence,
                level=groups.get("level", ""),
                timestamp=groups.get("timestamp", ""),
                script=groups.get("script", ""),
                feature=groups.get("feature", ""),
                message=groups.get("message", ""),
            )

    return UdpLogRecord(text=body + "\n", source=source, imei=imei, sequence=sequence)


def format_udp_log_record(
    record: UdpLogRecord,
    *,
    include_source: bool = False,
    compact: bool = False,
) -> str:
    text = record.compact_text() if compact else record.text
    if not include_source:
        return text

    fields = [f"source={record.source}"]
    if record.imei != "-":
        fields.insert(0, f"imei={record.imei}")
    if record.sequence is not None:
        fields.append(f"seq={record.sequence}")
    return f"[{' '.join(fields)}] {text}"


def format_udp_log_record_jsonl(record: UdpLogRecord) -> str:
    return json.dumps(record.to_json_dict(), ensure_ascii=False, separators=(",", ":")) + "\n"
