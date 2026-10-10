"""Visualised Link: two apps talking to each other, wherever they are, with nobody else able to read it.

One app starts a link and gets a code. The other is given the code (a QR code, or copied across) and joins.
From the code both work out a channel name and a key. Messages are encrypted with the key before they leave,
and passed through a relay that sees only the channel name and what it cannot read. The relay keeps a message
for a day at most.

    code      "VL1" + 32 random bytes as base64url: the whole secret. Whoever has it can read and send.
    channel   HKDF-SHA256(secret, salt "visualised-link-v1", info "channel"), 16 bytes as hex
    key       the same with info "key", 32 bytes: AES-256-GCM
    message   base64(12 random bytes + AES-GCM(key, those bytes, JSON {"k": kind, "t": text, "n": count},
              additional data = channel + sender))

kind is "hello" (I am here), "ack" (so am I), "msg" or "bye". count goes up by one with each thing a side
sends, and a message whose count isn't higher than the last from that sender is dropped: an old message played
back by the relay, or by anyone in between, is not delivered twice. The same is done in the page (vml/html.py).
"""
import base64
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request

RELAY = "https://visualised.io/link/"
SALT = b"visualised-link-v1"


class LinkError(Exception):
    pass


def new_code():
    return "VL1" + base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


def keys(code):
    """A code -> (channel, key). Raises LinkError for something that isn't a code."""
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    except ImportError as exc:
        raise LinkError("Link needs the 'cryptography' package (pip install cryptography).") from exc
    code = str(code).strip()
    try:
        if not code.startswith("VL1"):
            raise ValueError
        secret = base64.urlsafe_b64decode(code[3:] + "=" * (-len(code[3:]) % 4))
        if len(secret) != 32:
            raise ValueError
    except Exception:
        raise LinkError("That isn't a link code.") from None
    derive = lambda info, n: HKDF(algorithm=hashes.SHA256(), length=n, salt=SALT, info=info).derive(secret)
    return derive(b"channel", 16).hex(), derive(b"key", 32)


def seal(key, channel, sender, kind, text, count):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    plain = json.dumps({"k": kind, "t": text, "n": count}, separators=(",", ":")).encode()
    return base64.b64encode(nonce + AESGCM(key).encrypt(nonce, plain, (channel + sender).encode())).decode()


def unseal(key, channel, sender, body):
    """-> (kind, text, count), or None for anything that wasn't sealed with this key for this channel by that sender."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        raw = base64.b64decode(body)
        m = json.loads(AESGCM(key).decrypt(raw[:12], raw[12:], (channel + sender).encode()))
        return str(m["k"]), str(m.get("t", "")), int(m["n"])
    except Exception:
        return None


class Link:
    """One end of a link. Events are put on .events as (what, text): "joined", "message", "left", "error".
    Whoever owns it takes them off from its own thread (the engine does, with a timer)."""

    def __init__(self, code="", relay=None, start=""):
        self.code = str(code).strip() or new_code()
        self.channel, self.key = keys(self.code)
        self.relay = (relay or os.environ.get("VML_LINK_URL") or RELAY)
        self.sender = os.urandom(8).hex()
        self.events = queue.Queue()
        self.count = 0
        self.seen = {}                  # sender -> the highest count had from them
        self.since = 0 if start == "start" else -1       # -1: only what comes after joining
        self.active = time.time()
        self.closed = False
        self.failing = 0
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    # ---- the relay
    def call(self, query, body=None):
        req = urllib.request.Request(f"{self.relay}?c={self.channel}{query}", data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "text/plain", "User-Agent": "Visualised-Link/1"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())

    def post(self, kind, text=""):
        with self.lock:
            self.count += 1
            body = seal(self.key, self.channel, self.sender, kind, text, self.count)
        if len(body) > 24000:
            raise LinkError("That is too much for one message (about 17,000 characters is the most).")
        try:
            answer = self.call("", {"s": self.sender, "b": body})
        except urllib.error.HTTPError as exc:
            try:
                why = json.loads(exc.read().decode()).get("error", "")
            except Exception:
                why = ""
            raise LinkError(f"The relay refused that: {why or exc.code}.") from None
        except Exception:
            raise LinkError("The relay couldn't be reached.") from None
        if not answer.get("ok"):
            raise LinkError(f"The relay refused that: {answer.get('error', '')}.")
        self.active = time.time()

    # ---- the thread
    def run(self):
        try:
            if self.since < 0:
                self.since = int(self.call("&since=-1").get("seq", 0))
            self.post("hello")
        except Exception as exc:
            self.events.put(("error", str(exc) if isinstance(exc, LinkError) else "The relay couldn't be reached."))
        while not self.closed:
            try:
                answer = self.call(f"&since={self.since}")
                if self.failing >= 5:
                    self.events.put(("online", ""))
                self.failing = 0
                for m in answer.get("m", []):
                    self.since = max(self.since, int(m["q"]))
                    self.take(str(m.get("s", "")), str(m.get("b", "")))
                # (the relay forgot the channel, or was started again: begin again from what it has now)
                if int(answer.get("seq", 0)) < self.since:
                    self.since = int(answer.get("seq", 0))
            except Exception:
                self.failing += 1
                if self.failing == 5:
                    self.events.put(("error", "The relay can't be reached. It will keep trying."))
            quiet = time.time() - self.active
            wait = 0.4 if quiet < 15 else 1.5 if quiet < 300 else 4.0
            if self.failing:
                wait = min(30.0, 2.0 * self.failing)
            end = time.time() + wait
            while not self.closed and time.time() < end:
                time.sleep(0.05)

    def take(self, sender, body):
        if sender == self.sender:
            return
        got = unseal(self.key, self.channel, sender, body)
        if got is None:
            return                                  # not ours to read: someone else's noise on the channel
        kind, text, count = got
        if count <= self.seen.get(sender, 0):
            return                                  # an old one, played back
        new = sender not in self.seen
        self.seen[sender] = count
        self.active = time.time()
        if kind == "hello":
            self.events.put(("joined", ""))
            try:
                self.post("ack")
            except LinkError:
                pass
        elif kind == "ack":
            if new:
                self.events.put(("joined", ""))
        elif kind == "msg":
            self.events.put(("message", text))
        elif kind == "bye":
            self.seen.pop(sender, None)
            self.events.put(("left", ""))

    # ---- for the app
    def send(self, text):
        self.post("msg", str(text))

    def close(self):
        if self.closed:
            return
        try:
            self.post("bye")
        except LinkError:
            pass
        self.closed = True
