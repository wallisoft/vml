"""A stand-in for the Link relay (server/link/link.php), for the tests: the same questions and answers, kept in
memory, on this machine. It remembers everything it was sent, so a test can show that none of it was readable."""
import json, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class Relay:
    def __init__(self):
        self.messages, self.seq, self.lock, self.down = [], 0, threading.Lock(), False
        relay = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def answer(self, code, what):
                data = json.dumps(what).encode()
                self.send_response(code)
                for k, v in (("Content-Type", "application/json"), ("Access-Control-Allow-Origin", "*"),
                             ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"), ("Access-Control-Allow-Headers", "Content-Type"),
                             ("Content-Length", str(len(data)))):
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            def do_OPTIONS(self):
                self.answer(204, {})

            def channel(self):
                c = parse_qs(urlparse(self.path).query).get("c", [""])[0]
                if relay.down:
                    self.answer(503, {"ok": False, "error": "the relay is not available"})
                    return None
                if len(c) != 32 or any(ch not in "0123456789abcdef" for ch in c):
                    self.answer(400, {"ok": False, "error": "no such channel"})
                    return None
                return c

            def do_GET(self):
                c = self.channel()
                if c is None:
                    return
                since = int(parse_qs(urlparse(self.path).query).get("since", ["0"])[0])
                with relay.lock:
                    mine = [m for m in relay.messages if m["c"] == c]
                    latest = mine[-1]["q"] if mine else 0
                    out = [] if since < 0 else [{"q": m["q"], "s": m["s"], "b": m["b"], "t": m["t"]} for m in mine if m["q"] > since]
                self.answer(200, {"ok": True, "seq": latest, "m": out})

            def do_POST(self):
                c = self.channel()
                if c is None:
                    return
                try:
                    m = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                    s, b = m["s"], m["b"]
                    assert len(s) == 16 and 0 < len(b) <= 24000
                except Exception:
                    self.answer(400, {"ok": False, "error": "that is not a message"})
                    return
                with relay.lock:
                    relay.seq += 1
                    relay.messages.append({"q": relay.seq, "c": c, "s": s, "b": b, "t": int(time.time())})
                    seq = relay.seq
                self.answer(200, {"ok": True, "seq": seq})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
