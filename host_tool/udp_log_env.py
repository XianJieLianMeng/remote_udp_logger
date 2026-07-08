"""Runtime environment checks shared by the UDP log host tools.

This module must stay compatible with old Python versions (it only uses
Python 3.6+ syntax) so the version check itself can run and print a friendly
message instead of a SyntaxError from the newer modules.
"""
import errno
import socket
import sys

MIN_PYTHON = (3, 10)


def ensure_supported_python(tool_name):
    """Exit with a readable message when Python is too old for the tools."""
    if sys.version_info < MIN_PYTHON:
        raise SystemExit(
            "{0} requires Python {1}.{2}+ (current: {3}.{4}). "
            "Install a newer Python from https://www.python.org/downloads/ and retry.".format(
                tool_name,
                MIN_PYTHON[0],
                MIN_PYTHON[1],
                sys.version_info[0],
                sys.version_info[1],
            )
        )


def bind_udp_socket(host, port, tool_name):
    """Bind the shared log UDP port with a friendly port-in-use message."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError as error:
        sock.close()
        if getattr(error, "winerror", None) == 10048 or error.errno == errno.EADDRINUSE:
            raise SystemExit(
                "{0}: UDP port {1} is already in use.\n"
                "Only one UDP log tool can listen on a port at a time. Close the other "
                "tool (GUI / Web viewer / CLI receiver / TCP bridge), or pass a "
                "different --port and update the device target accordingly.".format(
                    tool_name, port
                )
            )
        raise SystemExit(
            "{0}: failed to bind udp://{1}:{2}: {3}".format(tool_name, host, port, error)
        )
    return sock
