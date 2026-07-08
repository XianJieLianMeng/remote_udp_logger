#!/usr/bin/env python3
import argparse
import errno
import select
import socket
import sys

from udp_log_env import bind_udp_socket, ensure_supported_python

ensure_supported_python("udp_log_tcp_bridge")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridge UDP device logs to TCP clients.")
    parser.add_argument("--udp-host", default="0.0.0.0", help="UDP bind host, default: 0.0.0.0")
    parser.add_argument("--udp-port", type=int, default=8001, help="UDP bind port, default: 8001")
    parser.add_argument("--tcp-host", default="127.0.0.1", help="TCP bind host, default: 127.0.0.1")
    parser.add_argument("--tcp-port", type=int, default=19001, help="TCP bind port, default: 19001")
    args = parser.parse_args()

    udp_sock = bind_udp_socket(args.udp_host, args.udp_port, "udp_log_tcp_bridge")

    tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        tcp_server.bind((args.tcp_host, args.tcp_port))
    except OSError as error:
        udp_sock.close()
        tcp_server.close()
        if getattr(error, "winerror", None) == 10048 or error.errno == errno.EADDRINUSE:
            raise SystemExit(
                f"udp_log_tcp_bridge: TCP port {args.tcp_port} is already in use. "
                "Close the other bridge instance or pass a different --tcp-port."
            )
        raise SystemExit(
            f"udp_log_tcp_bridge: failed to bind tcp://{args.tcp_host}:{args.tcp_port}: {error}"
        )
    tcp_server.listen(5)
    tcp_server.setblocking(False)

    clients: list[socket.socket] = []
    print(f"UDP listening on udp://{args.udp_host}:{args.udp_port}", flush=True)
    print(f"TCP bridge listening on tcp://{args.tcp_host}:{args.tcp_port}", flush=True)

    try:
        while True:
            readable, _, _ = select.select([udp_sock, tcp_server], [], [], 0.5)
            for ready in readable:
                if ready is tcp_server:
                    client, addr = tcp_server.accept()
                    client.setblocking(False)
                    clients.append(client)
                    print(f"TCP client connected: {addr[0]}:{addr[1]}", flush=True)
                    continue

                payload, addr = udp_sock.recvfrom(4096)
                text = payload.decode("utf-8", errors="replace")
                if not text.endswith("\n"):
                    text += "\n"
                print(text, end="", flush=True)

                disconnected = []
                encoded = text.encode("utf-8", errors="replace")
                for client in clients:
                    try:
                        client.sendall(encoded)
                    except OSError:
                        disconnected.append(client)

                for client in disconnected:
                    try:
                        client.close()
                    finally:
                        clients.remove(client)
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
    finally:
        for client in clients:
            try:
                client.close()
            except OSError:
                pass
        udp_sock.close()
        tcp_server.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OSError as exc:
        print(str(exc), file=sys.stderr, flush=True)
        raise SystemExit(1)
