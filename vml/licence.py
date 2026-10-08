"""Visualised licences: Community (free), Pro and Enterprise.

A licence key is a short signed statement issued by tiny-web.uk when someone buys Visualised Pro or Enterprise:

    VSL1-<payload, base64url>.<signature, base64url>        payload:  tier|seats|id|issued|expires|name

It is checked here with the public half of the signing key, so it needs no account and no internet, and nobody can
make one without the private half, which never leaves the server. `expires` (YYYYMMDD) is empty for a licence that
does not run out. The check is plain Python (Ed25519 as published in RFC 8032), so Visualised needs nothing extra
installed to do it.
"""
import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path

PUBLIC_KEY = "f8adda3be6d239d1b78bd0599d1b2924b0e02cfea2f1f63b69e3c256f4207ae5"      # the public half of the signing key on tiny-web.uk
BUY_URL = "https://tiny-web.uk/api/visualised-buy.php"
# VML_PREFS moves the file (the tests use it, so they never read or change the real one)
PREFS_FILE = Path(os.environ.get("VML_PREFS") or Path.home() / ".vml" / "prefs.json")

TIERS = ("community", "pro", "enterprise")
TIER_NAMES = {"community": "Community", "pro": "Pro", "enterprise": "Enterprise"}
# What each feature needs. Community designs, runs, saves and shares VML; everything that turns a form into
# something else, or brings one in from elsewhere, is Pro.
FEATURES = {"export": "pro", "import": "pro"}

# ---------------------------------------------------------------- Ed25519 signature check (RFC 8032), nothing else
_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _recover_x(y, sign):
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P:
        x = x * _I % _P
    if (x * x - xx) % _P:
        raise ValueError("not a point on the curve")
    if x == 0 and sign:
        raise ValueError("not a point on the curve")
    return _P - x if (x & 1) != sign else x


def _point(raw):
    y = int.from_bytes(raw, "little")
    sign, y = y >> 255, y & ((1 << 255) - 1)
    if y >= _P:
        raise ValueError("not a point on the curve")
    x = _recover_x(y, sign)
    return (x, y, 1, x * y % _P)


def _add(a, b):
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    e = (y1 + x1) * (y2 + x2) - (y1 - x1) * (y2 - x2)
    c, d = t1 * 2 * _D * t2 % _P, z1 * 2 * z2 % _P
    f, g, h = d - c, d + c, (y1 + x1) * (y2 + x2) + (y1 - x1) * (y2 - x2)
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _times(n, point):
    out = (0, 1, 1, 0)
    while n:
        if n & 1:
            out = _add(out, point)
        point = _add(point, point)
        n >>= 1
    return out


_BASE = _point((4 * pow(5, _P - 2, _P) % _P).to_bytes(32, "little"))


def verify(public, message, signature):
    """True if `signature` (64 bytes) is `public`'s (32 bytes) Ed25519 signature of `message`."""
    if len(public) != 32 or len(signature) != 64:
        return False
    try:
        a, r = _point(public), _point(signature[:32])
    except ValueError:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False
    h = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), "little") % _L
    left, right = _times(s, _BASE), _add(r, _times(h, a))
    return (left[0] * right[2] - right[0] * left[2]) % _P == 0 and (left[1] * right[2] - right[1] * left[2]) % _P == 0


# ---------------------------------------------------------------- keys
def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def tidy(key):
    """A key as pasted from an email: wrapped over lines, with spaces, perhaps in quotes or angle brackets."""
    return re.sub(r"[\s\"'<>]+", "", str(key or ""))


def read_licence(key, public_key=None):
    """What a genuine key says, or None if it isn't genuine. An out-of-date one is returned with expired=True."""
    key, public_key = tidy(key), PUBLIC_KEY if public_key is None else public_key
    if not key.startswith("VSL1-") or key.count(".") != 1 or len(public_key) != 64:
        return None
    try:
        payload, signature = (_unb64(part) for part in key[5:].split("."))
        if not verify(bytes.fromhex(public_key), payload, signature):
            return None
        fields = payload.decode("utf-8").split("|") + ["", ""]
        tier, seats, licence_id, issued, expires, name = fields[:6]
        if tier not in ("pro", "enterprise"):
            return None
        return {"tier": tier, "seats": int(seats or 1), "id": licence_id, "issued": issued, "expires": expires,
                "name": name, "key": key, "expired": bool(expires) and expires < time.strftime("%Y%m%d")}
    except Exception:
        return None


# ---------------------------------------------------------------- this user's settings (kept between runs)
def load_prefs():
    try:
        prefs = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
        return prefs if isinstance(prefs, dict) else {}
    except (OSError, ValueError):
        return {}


def save_prefs(prefs):
    try:
        PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PREFS_FILE.write_text(json.dumps(prefs, indent=1, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def current():
    """The licence in force: {'tier': 'community' | 'pro' | 'enterprise', ...}. No key, a bad key or an expired
    one all mean Community."""
    info = read_licence(load_prefs().get("licence_key", ""))
    if not info:
        return {"tier": "community", "name": "", "id": "", "issued": "", "expires": "", "expired": False, "key": ""}
    if info["expired"]:
        return dict(info, tier="community", was=info["tier"])
    return info


def allows(feature, tier=None):
    tier = tier or current()["tier"]
    return TIERS.index(tier) >= TIERS.index(FEATURES.get(feature, "community"))
