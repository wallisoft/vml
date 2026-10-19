"""
Finding things on the local network that say they're there (mDNS / DNS-SD, as printers and phones do): plain Python,
nothing to install. Used for Mountie's phones nearby: a phone sharing itself says "_sftp-ssh._tcp".

    browse("_sftp-ssh._tcp", seconds=2)  ->  [{"name", "host", "port", "txt": {...}}]

Asks once on the network's multicast address and gathers what answers in the time given; a service that answers
with its name, port (SRV) and address (A) is listed.
"""
import socket
import struct
import time

GROUP, PORT = "224.0.0.251", 5353
PTR, TXT, SRV, A = 12, 16, 33, 1


def _name(data, at):
    """A DNS name at data[at:], following compression pointers: (name, where the name ended)."""
    parts, end, seen = [], None, 0
    while True:
        n = data[at]
        if n == 0:
            at += 1
            break
        if n & 0xC0 == 0xC0:                                   # a pointer to a name earlier in the packet
            if end is None:
                end = at + 2
            at = ((n & 0x3F) << 8) | data[at + 1]
            seen += 1
            if seen > 20:
                raise ValueError("loop")
            continue
        parts.append(data[at + 1:at + 1 + n].decode("utf-8", "replace"))
        at += 1 + n
    return ".".join(parts), (end if end is not None else at)


def _query(service):
    q = struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0)
    for label in (service.strip(".") + ".local").split("."):
        b = label.encode()
        q += bytes([len(b)]) + b
    return q + b"\x00" + struct.pack(">HH", PTR, 0x8001)       # (PTR, asking for a unicast answer)


def _records(data):
    """Every answer, authority and additional record: (name, type, rdata start, rdata length)."""
    _, _, qd, an, ns, ar = struct.unpack(">HHHHHH", data[:12])
    at = 12
    for _ in range(qd):
        _, at = _name(data, at)
        at += 4
    out = []
    for _ in range(an + ns + ar):
        name, at = _name(data, at)
        kind, _, _, size = struct.unpack(">HHIH", data[at:at + 10])
        at += 10
        out.append((name, kind, at, size))
        at += size
    return out


def browse(service="_sftp-ssh._tcp", seconds=2.0):
    want = service.strip(".") + ".local"
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
    s.bind(("", 0))
    s.settimeout(0.25)
    found, srv, txt, addr = set(), {}, {}, {}
    try:
        for _ in range(2):                                     # (asked twice: one lost packet shouldn't hide a phone)
            s.sendto(_query(service), (GROUP, PORT))
            end = time.monotonic() + seconds / 2
            while time.monotonic() < end:
                try:
                    data, (sender, _) = s.recvfrom(9000)
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    for name, kind, at, size in _records(data):
                        if kind == PTR and name.lower() == want.lower():
                            found.add(_name(data, at)[0])
                        elif kind == SRV:
                            _, _, port = struct.unpack(">HHH", data[at:at + 6])
                            srv[name] = (_name(data, at + 6)[0], port, sender)
                        elif kind == A and size == 4:
                            addr[name] = socket.inet_ntoa(data[at:at + 4])
                        elif kind == TXT:
                            d, i = {}, at
                            while i < at + size:
                                n = data[i]
                                k, _, v = data[i + 1:i + 1 + n].decode("utf-8", "replace").partition("=")
                                if k:
                                    d[k] = v
                                i += 1 + n
                            txt[name] = d
                except (ValueError, IndexError, struct.error):
                    continue
    finally:
        s.close()
    out = []
    for full in sorted(found):
        if full not in srv:
            continue
        target, port, sender = srv[full]
        label = full[:-(len(want) + 1)] if full.lower().endswith("." + want.lower()) else full
        out.append({"name": label, "host": addr.get(target) or sender, "port": port, "txt": txt.get(full, {})})
    return out
