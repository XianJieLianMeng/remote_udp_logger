#!/usr/bin/env python3
import argparse
import socket
import sys

from udp_log_journal import UdpLogJournal
from udp_log_record import (
    format_udp_log_record,
    format_udp_log_record_jsonl,
    parse_udp_log_line,
)
from udp_log_sequence import UdpLogSequenceTracker


def main() -> int:
    parser = argparse.ArgumentParser(description="Receive UDP logs from the device.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host, default: 0.0.0.0")
    parser.add_argument("--port", type=int, default=8001, help="Bind port, default: 8001")
    parser.add_argument("--imei", default="", help="Only show logs from this IMEI/device id")
    parser.add_argument("--level", default="", help="Only show one log level: E/W/I/D/V")
    parser.add_argument("--feature", default="", help="Only show logs whose feature contains this text")
    parser.add_argument("--compact", action="store_true", help="Print compact level/feature/message lines")
    parser.add_argument("--jsonl", action="store_true", help="Print parsed records as JSON Lines")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host, args.port))
    journal = UdpLogJournal("udp_cli_session")
    sequence_tracker = UdpLogSequenceTracker()

    status_stream = sys.stderr if args.jsonl else sys.stdout
    print(f"Listening for device logs on udp://{args.host}:{args.port}", file=status_stream, flush=True)
    print(f"Session log: {journal.path}", file=status_stream, flush=True)
    try:
        while True:
            payload, addr = sock.recvfrom(2048)
            text = payload.decode("utf-8", errors="replace")
            source = f"{addr[0]}:{addr[1]}"
            record = parse_udp_log_line(text, source)
            journal.append(format_udp_log_record(record, include_source=True))
            gap = sequence_tracker.observe(record)
            if gap is not None:
                gap_line = gap.to_line()
                journal.append(gap_line)
                sys.stderr.write(gap_line)
                sys.stderr.flush()

            if args.imei and record.imei != args.imei:
                continue
            if args.level and record.level.upper() != args.level.upper():
                continue
            if args.feature and args.feature.lower() not in record.feature.lower():
                continue

            output = (
                format_udp_log_record_jsonl(record)
                if args.jsonl
                else format_udp_log_record(record, compact=args.compact)
            )
            sys.stdout.write(output)
            sys.stdout.flush()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
        return 0
    finally:
        journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
