#!/usr/bin/env python3
import argparse
import json
import socket
import time
from collections import defaultdict
from pathlib import Path

PORT = 9000


def _socket(bind_ip=None):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((bind_ip or "", PORT))
    return sock


def send_packets(nem, parent, pps, seconds, payload_bytes=256):
    if pps <= 0 or seconds <= 0 or payload_bytes < 64:
        raise ValueError("pps and seconds must be positive; payload must be at least 64 bytes")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((f"10.100.0.{nem}", 0))
    count = int(pps * seconds)
    interval = 1.0 / pps
    start = time.monotonic()
    for sequence in range(count):
        packet = {
            "origin": nem,
            "sequence": sequence,
            "created_ns": time.monotonic_ns(),
            "hops": 0,
            "path": [nem],
            "ttl": 32,
        }
        encoded = json.dumps(packet, separators=(",", ":")).encode()
        encoded += b" " * max(0, payload_bytes - len(encoded))
        sock.sendto(encoded, (f"10.100.0.{parent}", PORT))
        target = start + (sequence + 1) * interval
        delay = target - time.monotonic()
        if delay > 0:
            time.sleep(delay)
    sock.close()
    print(json.dumps({"nem": nem, "parent": parent, "sent": count}))


def relay(nem, parent, seconds):
    sock = _socket()
    sock.settimeout(0.5)
    end = time.monotonic() + seconds
    forwarded = 0
    while time.monotonic() < end:
        try:
            data, _ = sock.recvfrom(4096)
        except socket.timeout:
            continue
        packet = json.loads(data.rstrip(b" ").decode())
        if int(packet.get("ttl", 0)) <= 0:
            continue
        packet["ttl"] = int(packet["ttl"]) - 1
        packet["hops"] = int(packet.get("hops", 0)) + 1
        packet["path"] = list(packet.get("path", [])) + [nem]
        sock.sendto(json.dumps(packet, separators=(",", ":")).encode(), (f"10.100.0.{parent}", PORT))
        forwarded += 1
    sock.close()
    print(json.dumps({"nem": nem, "parent": parent, "forwarded": forwarded}))


def sink(seconds, output):
    sock = _socket()
    sock.settimeout(0.5)
    end = time.monotonic() + seconds
    received = defaultdict(set)
    latency_ms = defaultdict(list)
    hop_counts = defaultdict(list)
    paths = defaultdict(list)
    while time.monotonic() < end:
        try:
            data, _ = sock.recvfrom(4096)
        except socket.timeout:
            continue
        packet = json.loads(data.rstrip(b" ").decode())
        origin = int(packet["origin"])
        received[origin].add(int(packet["sequence"]))
        latency_ms[origin].append((time.monotonic_ns() - int(packet["created_ns"])) / 1e6)
        hop_counts[origin].append(int(packet["hops"]))
        paths[origin].append(packet["path"])
    sock.close()
    report = {}
    for origin, sequences in received.items():
        values = latency_ms[origin]
        report[str(origin)] = {
            "received_unique": len(sequences),
            "mean_latency_ms": sum(values) / len(values),
            "max_latency_ms": max(values),
            "mean_hops": sum(hop_counts[origin]) / len(hop_counts[origin]),
            "last_path": paths[origin][-1],
        }
    Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    sender = sub.add_parser("send")
    sender.add_argument("--nem", type=int, required=True)
    sender.add_argument("--parent", type=int, required=True)
    sender.add_argument("--pps", type=float, default=10)
    sender.add_argument("--seconds", type=float, default=10)
    sender.add_argument("--payload-bytes", type=int, default=256)
    forwarder = sub.add_parser("relay")
    forwarder.add_argument("--nem", type=int, required=True)
    forwarder.add_argument("--parent", type=int, required=True)
    forwarder.add_argument("--seconds", type=float, default=20)
    receiver = sub.add_parser("sink")
    receiver.add_argument("--seconds", type=float, default=20)
    receiver.add_argument("--out", default="multihop_report.json")
    args = parser.parse_args()
    if args.mode == "send":
        send_packets(args.nem, args.parent, args.pps, args.seconds, args.payload_bytes)
    elif args.mode == "relay":
        relay(args.nem, args.parent, args.seconds)
    else:
        sink(args.seconds, args.out)


if __name__ == "__main__":
    main()
