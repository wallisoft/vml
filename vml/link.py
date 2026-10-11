"""Visualised Link: two apps talking to each other, wherever they are, with nobody else able to read it.

One app starts a link and gets a code. The other is given the code (a QR code, or copied across) and joins.
From the code both work out a channel name and a key. Messages are encrypted with the key before they leave,
and passed through a relay that sees only the channel name and what it cannot read. The relay keeps a message
for a day at most.

Link is free to the people who use an app, and part of Visualised Pro for whoever makes one. A Pro licence gets
its holder a pass from the relay (fetch_pass), which Visualised puts into the apps they save and export; an app
shows it with what it sends, and its links are carried in full. With no pass a link is on the free allowance
(100 messages an hour, kept an hour): enough to try Link and build with it. server/link/pass.php has the detail.

    code      "VL1" + 32 random bytes as base64url: the whole secret. Whoever has it can read and send.
    channel   HKDF-SHA256(secret, salt "visualised-link-v1", info "channel"), 16 bytes as hex
    key       the same with info "key", 32 bytes: AES-256-GCM
    message   base64(12 random bytes + AES-GCM(key, those bytes, JSON {"k": kind, "t": text, "n": count},
              additional data = channel + sender))

kind is "hello" (I am here), "ack" (so am I), "msg" or "bye". count goes up by one with each thing a side
sends, and a message whose count isn't higher than the last from that sender is dropped: an old message played
back by the relay, or by anyone in between, is not delivered twice. The same is done in the page (vml/html.py).

Two apps can also agree a code with nothing shown or scanned, by each pressing "pair" within a few seconds of
the other (Pairing, below). The relay finds the two that pressed together and passes each the other's public
key; the secret they work out from the keys never goes near it. Each then shows three words made from the
secret. If the words are the same on both, nobody stood in the middle, and the link opens.

    key       a P-256 key pair, made for this one pairing and thrown away after
    promise   SHA-256 of the public key, given to the relay first. A side shows its key only once it holds the
              other's promise, so a key can't be chosen to suit one already seen, and three words are enough.
    shared    ECDH of the two keys
    code      "VL1" + HKDF-SHA256(shared, salt "visualised-link-pair-v1", info = the two public keys, lower first),
              35 bytes: the first 32 are the code's secret, the last 3 choose the three words from WORDS
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
PAIR_SALT = b"visualised-link-pair-v1"
# The words two people compare after pairing by pressing together: 256 of them, so three say 24 bits. Plain
# things, easy to read out, none much like another. (The page has the same list, in the same order.)
WORDS = ("apple arrow badge baker beach berry bison blade bread brick bridge broom brush bucket butter button cabin camel "
         "candle canoe carpet carrot castle chair chalk cheese cherry circus clock cloud clover coast cobra comet coral "
         "cotton cradle crane crayon cricket crown daisy dancer desert diamond dinner dolphin donkey dragon drum eagle "
         "elbow engine falcon farmer feather fence ferry fiddle finger forest fossil fountain fox garden garlic ginger "
         "giraffe glove goblin goose grape guitar hammer harbour hazel hedge helmet heron honey hornet house island ivory "
         "jacket jelly jigsaw jungle kettle kitten ladder lagoon lantern lemon lentil lilac lizard lobster locket magnet "
         "mango maple marble market meadow melon mirror monkey moon mountain muffin mustard napkin needle nettle noodle "
         "nutmeg oak ocean olive onion orange orchid otter owl oyster paddle panda parrot pasta peach pebble pencil pepper "
         "piano pickle pigeon pillow pirate planet plum pocket pony poppy potato puddle puffin pumpkin puppet quilt rabbit "
         "radio raven ribbon river robin rocket saddle sailor salmon sandal satin scarf shadow shell shovel silver skate "
         "sled snail sofa spider spoon sprout squid stable statue stone storm sugar summer sunset swan table teapot "
         "thimble thunder ticket tiger timber toast tomato torch tower tractor trumpet tulip tunnel turkey turtle umbrella "
         "valley velvet violin wagon walnut walrus water whale wheat whistle willow window winter wizard wolf yogurt zebra "
         "anchor acorn badger banjo basket beetle biscuit blanket bottle cactus candy copper dagger emerald flute gravel "
         "hamster igloo jaguar kayak koala lemur mitten nugget ostrich parsnip quiver radish sparrow tadpole unicorn "
         "vulture waffle yacht zipper pelican compass lighthouse").split()


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


def _ask(url, body=None):
    """Ask the relay something and give back its answer. LinkError, in words, when it refuses or can't be reached."""
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "text/plain", "User-Agent": "Visualised-Link/1"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            answer = json.loads(r.read().decode())
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
    return answer


def fetch_pass(licence_key, relay=None):
    """The pass that goes with a Pro licence key: what an app shows the relay to have its links carried in full.
    LinkError, in words, if the relay won't give one or can't be reached."""
    return str(_ask(f"{relay or os.environ.get('VML_LINK_URL') or RELAY}?pass", {"key": str(licence_key)}).get("pass", ""))


def pair_secret(private, mine, theirs):
    """Our private key and the two public keys (as bytes) -> (code, "three words here"). Both sides get the same."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    shared = private.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), theirs))
    out = HKDF(algorithm=hashes.SHA256(), length=35, salt=PAIR_SALT, info=min(mine, theirs) + max(mine, theirs)).derive(shared)
    return "VL1" + base64.urlsafe_b64encode(out[:32]).decode().rstrip("="), " ".join(WORDS[b] for b in out[32:])


class Pairing:
    """Agreeing a link's code with another app by both pressing at about the same time. One event is put on
    .events: ("words", the three words), with .code then set, or ("error", why not)."""

    def __init__(self, relay=None):
        self.relay = (relay or os.environ.get("VML_LINK_URL") or RELAY)
        self.events = queue.Queue()
        self.code, self.words, self.closed = "", "", False
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            self.agree()
        except LinkError as exc:
            if not self.closed:
                self.events.put(("error", str(exc)))
        except ImportError:
            self.events.put(("error", "Link needs the 'cryptography' package (pip install cryptography)."))
        except Exception:
            if not self.closed:
                self.events.put(("error", "The pairing went wrong. Press together again."))

    def agree(self):
        import hashlib
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        private = ec.generate_private_key(ec.SECP256R1())
        mine = private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        promise = hashlib.sha256(mine).hexdigest()
        me = str(_ask(f"{self.relay}?p=go", {"c": promise})["id"])
        shown = False
        end = time.time() + 40
        while not self.closed and time.time() < end:
            answer = _ask(f"{self.relay}?p=wait&id={me}")
            state = answer.get("state")
            if state == "busy":
                raise LinkError("Someone else was pairing at the same moment. Press together again.")
            if state == "gone":
                raise LinkError("Nobody else pressed in time. Press together, within a few seconds of each other.")
            if state == "paired":
                theirs = str(answer.get("c", ""))
                if len(theirs) != 64 or theirs == promise:
                    raise LinkError("The pairing went wrong. Press together again.")
                if not shown:                       # we hold their promise: now ours may be seen
                    _ask(f"{self.relay}?p=key&id={me}", {"k": base64.urlsafe_b64encode(mine).decode().rstrip("=")})
                    shown = True
                if answer.get("k"):
                    key = str(answer["k"])
                    raw = base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))
                    if hashlib.sha256(raw).hexdigest() != theirs:
                        raise LinkError("The pairing was interfered with. Don't go on.")
                    try:
                        self.code, self.words = pair_secret(private, mine, raw)
                    except ValueError:
                        raise LinkError("The pairing was interfered with. Don't go on.") from None
                    self.events.put(("words", self.words))
                    return
            time.sleep(0.4)
        if not self.closed:
            raise LinkError("Nobody else pressed in time. Press together, within a few seconds of each other.")

    def send(self, text):
        raise LinkError("There is no link yet: the pairing hasn't been agreed.")

    def close(self):
        self.closed = True


class Link:
    """One end of a link. Events are put on .events as (what, text): "joined", "message", "left", "error".
    Whoever owns it takes them off from its own thread (the engine does, with a timer)."""

    def __init__(self, code="", relay=None, start="", carry=""):
        self.carry = str(carry or "")   # the pass of whoever made this app, if they have one: the link is then carried in full
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
            answer = self.call(f"&v={self.carry}" if self.carry else "", {"s": self.sender, "b": body})
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
            # (a link nobody is using asks less and less often: a chat left open overnight is one question a minute)
            wait = 0.4 if quiet < 15 else 1.5 if quiet < 120 else 5.0 if quiet < 600 else 15.0 if quiet < 3600 else 60.0
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
