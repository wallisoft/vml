"""
Finding things on the local network that say they're there (mDNS / DNS-SD, as printers and phones do): plain Python,
nothing to install. Used for Mountie's phones nearby: a phone sharing itself says "_sftp-ssh._tcp".

    browse("_sftp-ssh._tcp", seconds=2)  ->  [{"name", "host", "port", "txt": {...}}]

Asks once on the network's multicast address and gathers what answers in the time given; a service that answers
with its name, port (SRV) and address (A) is listed.
"""
import re
import shutil
import socket
import struct
import subprocess
import sys
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
    return q + b"\x00" + struct.pack(">HH", PTR, 1)            # (PTR, class IN: answered to the group)


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


def _avahi(service, seconds):
    """Linux: avahi-browse, which the desktop's own mDNS daemon answers (it hears phones that ignore a plain query)."""
    try:
        out = subprocess.run(["avahi-browse", "-rpt", "-k", service], capture_output=True, text=True,
                             timeout=max(2.0, seconds + 1)).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    found = {}
    for line in out.splitlines():
        f = line.split(";")
        if len(f) < 10 or f[0] != "=" or f[2] != "IPv4":
            continue
        name = re.sub(r"\\(\d{3})", lambda m: chr(int(m.group(1))), f[3])
        txt = {}
        for part in re.findall(r'"([^"]*)"', ";".join(f[9:])):
            k, _, v = part.partition("=")
            txt[k] = v
        found.setdefault(name, {"name": name, "host": f[7], "port": int(f[8] or 0), "txt": txt})
    return list(found.values())


def browse(service="_sftp-ssh._tcp", seconds=2.0):
    """What answers for service: avahi on Linux when it's there, otherwise our own query on the mDNS port."""
    if sys.platform.startswith("linux") and shutil.which("avahi-browse"):
        got = _avahi(service, seconds)
        if got is not None:
            return got
    return _browse(service, seconds)


def _browse(service="_sftp-ssh._tcp", seconds=2.0):
    want = service.strip(".") + ".local"
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
    try:                                                       # on the mDNS port, in its group: answers sent to the group
        s.bind(("", PORT))                                     # are heard (some phones answer only there)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(GROUP) + socket.inet_aton("0.0.0.0"))
    except OSError:
        s.bind(("", 0))                                        # (taken: answers come back to us directly instead)
    s.settimeout(0.2)
    found, srv, txt, addr = set(), {}, {}, {}
    try:
        for _ in range(2):                                     # (asked twice: one lost packet shouldn't hide a phone)
            s.sendto(_query(service), (GROUP, PORT))
            end = time.monotonic() + seconds / 2
            while time.monotonic() < end:
                if found and all(f in srv for f in found) and time.monotonic() > end - seconds / 2 + 0.4:
                    break                                      # (every phone heard from in full: no need to wait on)
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


def _local_networks():
    """This computer's IPv4 addresses on its networks (not loopback), as the /24 each is in."""
    ips = set()
    for probe in ("192.168.1.1", "10.0.0.1", "172.16.0.1", "8.8.8.8"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((probe, 9))                              # (no packet is sent: it picks the address it would use)
            ips.add(s.getsockname()[0])
            s.close()
        except OSError:
            pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted({ip.rsplit(".", 1)[0] for ip in ips if not ip.startswith(("127.", "169.254."))}), ips


def scan_for_phones(port=2222, timeout=0.5):
    """Phones sharing themselves, found by asking each address on this computer's networks (a /24 each) for port 2222
    and reading its SSH greeting ("SSH-2.0-Mountie_<phone>"): for when the announcement isn't heard. About a second."""
    from concurrent.futures import ThreadPoolExecutor
    nets, mine = _local_networks()
    hosts = [f"{n}.{i}" for n in nets for i in range(1, 255) if f"{n}.{i}" not in mine]

    def ask(host):
        try:
            with socket.create_connection((host, port), timeout=timeout) as c:
                c.settimeout(timeout * 2)
                hello = c.recv(256).decode("ascii", "replace").strip()
        except OSError:
            return None
        if not hello.startswith("SSH-"):
            return None
        soft = hello.split("-", 2)[2] if hello.count("-") >= 2 else ""
        if soft.startswith("Mountie_"):
            name = soft[8:].replace("_", " ").strip() or "Phone"
        elif "APACHE-SSHD" in soft.upper():
            name = f"Phone ({host})"                           # (an older Mountie on the phone: no name in its greeting)
        else:
            return None                                        # some other SSH server on 2222, not a phone
        return {"name": name, "host": host, "port": port, "user": "phone"}

    with ThreadPoolExecutor(max_workers=128) as pool:
        return [r for r in pool.map(ask, hosts) if r]
