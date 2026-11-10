import socket
import sys
import time

PORT = 9010

if sys.argv[1] == "recv":
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("10.100.0.1", PORT))
    sock.settimeout(0.5)

    received = set()
    end = time.monotonic() + 6

    while time.monotonic() < end:
        try:
            data, address = sock.recvfrom(1024)
            received.add(data.decode())
        except socket.timeout:
            pass

    print("Gateway received:", len(received), "/ 20")
    print("Packets:", sorted(received))
    sock.close()

elif sys.argv[1] == "send":
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("10.100.0.2", 0))

    for i in range(20):
        sock.sendto(f"unicast-test-{i}".encode(), ("10.100.0.1", PORT))
        time.sleep(0.1)

    sock.close()
    print("NEM 2 transmitted: 20 packets")
