#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass

from udp_log_record import UdpLogRecord


@dataclass(frozen=True)
class SequenceGap:
    imei: str
    source: str
    expected: int
    actual: int
    missing: int

    def to_line(self) -> str:
        return (
            f"W [udp.seq] event=gap imei={self.imei} source={self.source} "
            f"expected={self.expected} actual={self.actual} missing={self.missing}\n"
        )


class UdpLogSequenceTracker:
    def __init__(self) -> None:
        self._last_by_device: dict[tuple[str, str], int] = {}

    def observe(self, record: UdpLogRecord) -> SequenceGap | None:
        if record.sequence is None:
            return None

        key = (record.imei, record.source)
        previous = self._last_by_device.get(key)
        self._last_by_device[key] = record.sequence

        if previous is None:
            return None

        expected = previous + 1
        if record.sequence == expected or record.sequence <= previous:
            return None

        return SequenceGap(
            imei=record.imei,
            source=record.source,
            expected=expected,
            actual=record.sequence,
            missing=record.sequence - expected,
        )
