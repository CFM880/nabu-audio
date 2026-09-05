#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read the local QRTR name service; does not start or stop DSP services."""
import argparse
import socket
import struct
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-slim', action='store_true')
    args = parser.parse_args()
    found = False
    with socket.socket(42, socket.SOCK_DGRAM) as sock:
        node, _ = sock.getsockname()
        sock.sendto(struct.pack('<IIIII', 10, 0, 0, 0, 0),
                    (node, 0xfffffffe))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            sock.settimeout(max(0.001, deadline - time.monotonic()))
            try:
                packet, peer = sock.recvfrom(4096)
            except TimeoutError:
                break
            if peer != (node, 0xfffffffe) or len(packet) != 20:
                continue
            cmd, service, instance, remote, port = struct.unpack('<IIIII', packet)
            if cmd != 4:
                continue
            if not any((service, instance, remote, port)):
                break
            print(f'service=0x{service:04x} version={instance & 255} '
                  f'instance={instance >> 8} node={remote} port={port}')
            found |= service == 0x301 and instance == 1
    if args.require_slim and not found:
        print('SLIMbus QMI service 0x301 v1 instance 0 is absent', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except OSError as error:
        print(f'QRTR lookup failed: {error}', file=sys.stderr)
        sys.exit(2)
