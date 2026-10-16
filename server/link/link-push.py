#!/usr/bin/env python3
"""
Visualised Link: push. Apps hold one connection open here and are sent each message the moment the relay stores
it, instead of asking the relay every few seconds. (Sending is unchanged: a POST to link.php, with all its limits.)

    GET /link/push?c=CHANNEL[,CHANNEL...]    a Server-Sent Events stream: "data: {"c","q","s","b","t"}" per message,
                                             and a comment every 20 seconds so the connection stays up
    GET /link/push/health                    {"ok": true, "connections": N, "channels": N}

link.php tells it about each stored message with one UDP datagram to 127.0.0.1:8791 (fire-and-forget: a send
never waits on this). What passes through is what the relay already holds: channel names and sealed messages
that only the two apps can open. Nothing is kept here.

Standard library only. Run by systemd as www-data (vml-link-push.service).
"""
import asyncio
import json
import os
import re
import time
from urllib.parse import parse_qs, urlsplit

HTTP_PORT = int(os.environ.get("LINK_PUSH_PORT", "8790"))
UDP_PORT = int(os.environ.get("LINK_PUSH_UDP", "8791"))
MAX_CONNECTIONS = int(os.environ.get("LINK_PUSH_MAX", "20000"))
PER_ADDRESS = int(os.environ.get("LINK_PUSH_PER_ADDRESS", "200"))   # (an office or school can share one address)
CHANNELS_EACH = 16
HEARTBEAT = 20
CHANNEL = re.compile(r"^[0-9a-f]{32}$")

listeners = {}       # channel -> set of Subscriber
by_address = {}      # address -> count
connections = 0


class Subscriber:
    __slots__ = ("writer", "channels", "address", "dead")

    def __init__(self, writer, channels, address):
        self.writer, self.channels, self.address, self.dead = writer, channels, address, False

    def send(self, text):
        if self.dead:
            return
        try:
            if self.writer.transport.get_write_buffer_size() > 1_000_000:      # a reader that has stopped reading
                raise ConnectionError
            self.writer.write(text.encode())
        except Exception:
            self.dead = True
            try:
                self.writer.close()
            except Exception:
                pass


def plain(writer, status, body, kind="application/json"):
    data = body.encode()
    writer.write((f"HTTP/1.1 {status}\r\nContent-Type: {kind}\r\nContent-Length: {len(data)}\r\n"
                  "Cache-Control: no-store\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n").encode() + data)


async def handle(reader, writer):
    global connections
    sub = None
    try:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
        lines = head.decode("latin-1").split("\r\n")
        method, target = (lines[0].split(" ") + ["", ""])[:2]
        headers = {k.strip().lower(): v.strip() for k, _, v in (l.partition(":") for l in lines[1:] if ":" in l)}
        address = headers.get("x-real-ip") or (writer.get_extra_info("peername") or ("?",))[0]
        url = urlsplit(target)
        if method == "OPTIONS":
            writer.write(b"HTTP/1.1 204 No Content\r\nAccess-Control-Allow-Origin: *\r\nAccess-Control-Allow-Methods: GET\r\n"
                         b"Access-Control-Max-Age: 86400\r\nConnection: close\r\n\r\n")
            return
        if url.path.endswith("/health"):
            plain(writer, "200 OK", json.dumps({"ok": True, "connections": connections, "channels": len(listeners)}))
            return
        if method != "GET" or not url.path.endswith("/push"):
            plain(writer, "404 Not Found", '{"ok":false,"error":"no such thing"}')
            return
        chans = [c for c in parse_qs(url.query).get("c", [""])[0].split(",") if CHANNEL.match(c)][:CHANNELS_EACH]
        if not chans:
            plain(writer, "400 Bad Request", '{"ok":false,"error":"no such channel"}')
            return
        if connections >= MAX_CONNECTIONS or by_address.get(address, 0) >= PER_ADDRESS:
            plain(writer, "429 Too Many Requests", '{"ok":false,"error":"too many connections: poll instead for now"}')
            return
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-store\r\n"
                     b"Access-Control-Allow-Origin: *\r\nX-Accel-Buffering: no\r\nConnection: keep-alive\r\n\r\n"
                     b"retry: 3000\n: open\n\n")
        sub = Subscriber(writer, chans, address)
        connections += 1
        by_address[address] = by_address.get(address, 0) + 1
        for c in chans:
            listeners.setdefault(c, set()).add(sub)
        while not sub.dead:                      # until the app goes: anything it sends is ignored
            try:
                if not await asyncio.wait_for(reader.read(1024), HEARTBEAT):
                    break
            except asyncio.TimeoutError:
                sub.send(": ping\n\n")
                await writer.drain()
    except Exception:
        pass
    finally:
        if sub:
            sub.dead = True
            connections -= 1
            by_address[sub.address] = by_address.get(sub.address, 1) - 1
            if by_address[sub.address] <= 0:
                by_address.pop(sub.address, None)
            for c in sub.channels:
                s = listeners.get(c)
                if s:
                    s.discard(sub)
                    if not s:
                        listeners.pop(c, None)
        try:
            await writer.drain()
            writer.close()
        except Exception:
            pass


class Nudges(asyncio.DatagramProtocol):
    """One datagram from link.php per stored message: {"c","q","s","b","t"}."""

    def datagram_received(self, data, addr):
        if addr[0] not in ("127.0.0.1", "::1"):
            return
        try:
            m = json.loads(data.decode())
            subs = listeners.get(str(m.get("c", "")))
            if not subs:
                return
            line = "data: " + json.dumps({k: m[k] for k in ("c", "q", "s", "b", "t") if k in m}, separators=(",", ":")) + "\n\n"
            for sub in list(subs):
                sub.send(line)
        except Exception:
            pass


async def main():
    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(Nudges, local_addr=("127.0.0.1", UDP_PORT))
    server = await asyncio.start_server(handle, "127.0.0.1", HTTP_PORT, limit=16384, backlog=1024)
    print(f"link-push: http 127.0.0.1:{HTTP_PORT}, nudges udp 127.0.0.1:{UDP_PORT}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
