#!/usr/bin/env python3
"""One-way UDP probe (no replies needed, so the receive-only gateway works).
  udp_probe.py recv  <seconds> <out.json>            count packets per sender
  udp_probe.py send  <my_nem> <pkts_per_s> <seconds> broadcast 1000-byte packets tagged with my NEM id"""
import json
import socket
import struct
import sys
import time

PORT = 9000


def recv(secs, path):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", PORT))
    s.settimeout(0.5)
    got, end = {}, time.time() + secs
    while time.time() < end:
        try:
            data, _ = s.recvfrom(2048)
        except socket.timeout:
            continue
        if len(data) >= 4:
            src = struct.unpack("!I", data[:4])[0]
            got[src] = got.get(src, 0) + 1
    json.dump(got, open(path, "w"))


def send(me, pps, secs):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind((f"10.100.0.{me}", 0))
    payload = struct.pack("!I", me) + b"x" * 996
    n, gap, t0 = int(pps * secs), 1.0 / pps, time.time()
    for i in range(n):
        s.sendto(payload, ("10.100.0.255", PORT))
        d = t0 + (i + 1) * gap - time.time()
        if d > 0:
            time.sleep(d)
    print(n)


if __name__ == "__main__":
    if sys.argv[1] == "recv":
        recv(float(sys.argv[2]), sys.argv[3])
    else:
        send(int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]))
