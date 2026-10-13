"""An app made with Visualised, as an Android app of its own: one .apk to hand to anyone with an Android phone.

Nothing from Android's tools is needed to make it. Visualised carries a ready-built copy of its own phone app (the
template: vml/web/android-template.apk, built from android/ by android/make-template.sh), and this puts the app's page inside a copy of that,
gives it the app's own name, picture, version and identity, takes out what the app doesn't use, and signs it:

    assets/app/index.html   the app, as the page export makes (the phone app, finding it there, shows only it)
    AndroidManifest.xml     rewritten: its own package name and label, its version, only the permissions its
                            scripts need, and none of what belongs to Visualised's own app (opening files and links)
    the launcher pictures   replaced with the app's Icon, at each size
    the signature           APK Signature Scheme v2, with a key made for this developer and kept on this computer

The key matters: Android takes an update to an app only if it is signed with the key the app was first signed
with. It is made once, kept beside the user's Visualised settings, and has to be backed up by whoever owns it.

Google Play asks for a different packaging (an app bundle), so this is for handing over directly: a download, a
message, another store.
"""
import hashlib
import io
import os
import re
import struct
import zipfile
import zlib
from pathlib import Path

# Beside Visualised's other web files, from source and in a compiled build alike (see WEB_DIR in vml/html.py).
TEMPLATE = next((d / "android-template.apk" for d in (Path(__file__).resolve().parent / "web", Path(__file__).resolve().parent.parent / "web")
                 if (d / "android-template.apk").is_file()), Path(__file__).resolve().parent / "web" / "android-template.apk")
# The push template: the same app with Firebase Cloud Messaging, for apps whose scripts use OnPush.
PUSH_TEMPLATE = TEMPLATE.with_name("android-template-push.apk")
PUSH = "com.google.android.c2dm.permission.RECEIVE"   # what an app that hears pushes must declare (and the sign of one)
LISTEN = "visualised.LISTEN_NOTIFICATIONS"   # not a permission: says the app keeps Heard (reading messaging apps' notices)
# Parts of the template only some apps keep: (the component's class, what the app must keep for it).
OPTIONAL_PARTS = {"io.visualised.app.Arriving": "android.permission.RECEIVE_SMS", "io.visualised.app.Heard": LISTEN,
                  "io.visualised.app.Booted": "android.permission.RECEIVE_BOOT_COMPLETED"}
ANDROID = "http://schemas.android.com/apk/res/android"

# What each thing a script can ask of a phone needs the app to declare (a name with no dots is android.permission.NAME). (Commands are named in scripts as
# Vml("Torch", ...); see the commands in vml/html.py.) INTERNET and the network's state are always kept.
NEEDS = {
    "CAMERA": ("Torch", "ScanCode", "Flash", "WatchLight"),
    "ACCESS_FINE_LOCATION": ("GetLocation",),
    "ACCESS_COARSE_LOCATION": ("GetLocation",),
    "RECORD_AUDIO": ("Listen",),
    "MODIFY_AUDIO_SETTINGS": ("Listen",),
    "POST_NOTIFICATIONS": ("Notify", "RunInBackground", "WatchBluetooth", "OnPush"),
    "VIBRATE": ("Vibrate", "Flash"),
    "FOREGROUND_SERVICE": ("RunInBackground",),
    "FOREGROUND_SERVICE_SPECIAL_USE": ("RunInBackground",),
    "WAKE_LOCK": ("RunInBackground", "KeepAwake", "OnPush"),
    "BLUETOOTH": ("BluetoothDevices", "WatchBluetooth", "BluetoothLog"),
    "BLUETOOTH_CONNECT": ("BluetoothDevices", "WatchBluetooth", "BluetoothLog"),
    "ACCESS_BACKGROUND_LOCATION": ("WatchBluetooth",),
    "SEND_SMS": ("SmsSend",),
    "RECEIVE_SMS": ("OnSms",),
    "READ_CONTACTS": ("ReadContacts", "LookupNames", "LookupNumber", "SaveContact"),
    "WRITE_CONTACTS": ("SaveContact",),
    "RECEIVE_BOOT_COMPLETED": ("RunInBackground",),
    PUSH: ("OnPush",),
    LISTEN: ("OnMessages",),
}
ALWAYS = ("INTERNET", "ACCESS_NETWORK_STATE")


class ApkError(Exception):
    pass


def permissions_for(code):
    """The permissions an app whose scripts are `code` needs, by what its scripts ask of the phone."""
    used = set(re.findall(r"""["']([A-Z][A-Za-z]+)["']""", code))
    return sorted(set(ALWAYS) | {p for p, commands in NEEDS.items() if used & set(commands)})


def package_name(app_name, certificate):
    """A name for the app that is its own everywhere: io.visualised.made.<the app>.k<part of its maker's key>.
    Two people's apps of the same name don't collide, and the same person's app keeps its name between versions."""
    safe = re.sub(r"[^a-z0-9]+", "", app_name.lower()) or "app"
    if not safe[0].isalpha():
        safe = "a" + safe
    return f"io.visualised.made.{safe[:40]}.k{key_id(certificate)}"


def good_package(name):
    return bool(re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+", name)) and len(name) <= 150


def version_code(version):
    """A version as people write it -> the whole number Android compares: 1.2.3 -> 10203; anything else -> 1."""
    parts = [int(p) for p in re.findall(r"\d+", str(version))[:3]]
    if not parts:
        return 1
    parts += [0] * (3 - len(parts))
    return max(1, min(parts[0], 2000) * 10000 + min(parts[1], 99) * 100 + min(parts[2], 99))


# ---------------------------------------------------------------- the manifest, in Android's binary form
class Manifest:
    """AndroidManifest.xml as it is inside an APK: a table of strings, then the elements in order, each naming
    its strings by number. Read, changed in place, and written back. Strings are only ever added (at the end):
    the first few stand for Android's own attribute names by position, so none may move."""
    XML, STRINGS, RESOURCES, START, END = 0x0003, 0x0001, 0x0180, 0x0102, 0x0103

    def __init__(self, data):
        kind, head, size = struct.unpack_from("<HHI", data, 0)
        if kind != self.XML or size != len(data):
            raise ApkError("the template's manifest isn't in the form expected")
        self.chunks, at = [], head
        while at < len(data):
            kind, head, size = struct.unpack_from("<HHI", data, at)
            if size < 8 or at + size > len(data):
                raise ApkError("the template's manifest isn't in the form expected")
            self.chunks.append([kind, bytearray(data[at:at + size])])
            at += size
        pool = next((c for c in self.chunks if c[0] == self.STRINGS), None)
        if pool is None:
            raise ApkError("the template's manifest has no strings")
        self.strings = self._read_strings(bytes(pool[1]))

    @staticmethod
    def _read_strings(chunk):
        _, _, _, count, styles, flags, start, _ = struct.unpack_from("<HHIIIIII", chunk, 0)
        if styles:
            raise ApkError("the template's manifest has styled strings, which isn't expected")
        out = []
        for i in range(count):
            at = start + struct.unpack_from("<I", chunk, 28 + 4 * i)[0]
            if flags & 0x100:                                       # UTF-8: a length in characters, then one in bytes
                at += 2 if chunk[at] & 0x80 else 1
                n = chunk[at]
                if n & 0x80:
                    n, at = ((n & 0x7F) << 8) | chunk[at + 1], at + 1
                out.append(chunk[at + 1:at + 1 + n].decode("utf-8", "replace"))
            else:                                                   # UTF-16
                n = struct.unpack_from("<H", chunk, at)[0]
                at += 2
                if n & 0x8000:
                    n, at = ((n & 0x7FFF) << 16) | struct.unpack_from("<H", chunk, at)[0], at + 2
                out.append(chunk[at:at + 2 * n].decode("utf-16-le", "replace"))
        return out

    def _write_strings(self):
        body, offsets = bytearray(), []
        for text in self.strings:
            offsets.append(len(body))
            raw = text.encode("utf-16-le")
            n = len(raw) // 2
            body += struct.pack("<HH", 0x8000 | (n >> 16), n & 0xFFFF) if n > 0x7FFF else struct.pack("<H", n)
            body += raw + b"\0\0"
        body += b"\0" * (-len(body) % 4)
        start = 28 + 4 * len(offsets)
        return struct.pack("<HHIIIIII", self.STRINGS, 28, start + len(body), len(offsets), 0, 0, start, 0) \
            + b"".join(struct.pack("<I", o) for o in offsets) + bytes(body)

    def string(self, text):
        """The number of a string, added if it isn't there. (Never one of the first, which stand for attributes.)"""
        self.strings.append(str(text))
        return len(self.strings) - 1

    def elements(self):
        """Each element as it starts: (place in the chunks, name, depth, {attribute name: (offset in its chunk, type, data)})."""
        depth = 0
        for i, (kind, raw) in enumerate(self.chunks):
            if kind == self.START:
                name, a_start, a_size, a_count = struct.unpack_from("<IHHH", raw, 20)
                attrs = {}
                for n in range(a_count):
                    at = 16 + a_start + n * a_size
                    _, a_name, _, _, _, a_type, a_data = struct.unpack_from("<IIIHBBI", raw, at)
                    attrs[self.strings[a_name]] = (at, a_type, a_data)
                yield i, self.strings[name], depth, attrs
                depth += 1
            elif kind == self.END:
                depth -= 1

    def value(self, attr):
        """What an attribute says, when it is a string; None otherwise."""
        return self.strings[attr[2]] if attr[1] == 0x03 else None

    def set_string(self, place, attr, text):
        n = self.string(text)
        struct.pack_into("<I", self.chunks[place][1], attr[0] + 8, n)           # the value as written
        struct.pack_into("<HBBI", self.chunks[place][1], attr[0] + 12, 8, 0, 0x03, n)   # and as typed: a string

    def set_number(self, place, attr, number):
        struct.pack_into("<I", self.chunks[place][1], attr[0] + 8, 0xFFFFFFFF)
        struct.pack_into("<HBBI", self.chunks[place][1], attr[0] + 12, 8, 0, 0x10, int(number))

    def remove(self, place):
        """Take out the element that starts at this place, with everything inside it."""
        depth, end = 0, place
        for end in range(place, len(self.chunks)):
            kind = self.chunks[end][0]
            depth += 1 if kind == self.START else -1 if kind == self.END else 0
            if depth == 0:
                break
        del self.chunks[place:end + 1]

    def bytes(self):
        parts = [self._write_strings() if kind == self.STRINGS else bytes(raw) for kind, raw in self.chunks]
        return struct.pack("<HHI", self.XML, 8, 8 + sum(len(p) for p in parts)) + b"".join(parts)


def rewrite_manifest(data, package, label, version, code, permissions):
    """The template's manifest, made the app's own."""
    m = Manifest(data)
    keep = {p if "." in p else "android.permission." + p for p in permissions}
    done = set()
    while True:                                     # (removing moves what follows, so look again after each)
        for place, name, depth, attrs in m.elements():
            if name == "uses-permission" and (m.value(attrs.get("name", (0, 0, 0))) or "") not in keep:
                m.remove(place)
                break
            if name in ("receiver", "service") and OPTIONAL_PARTS.get(m.value(attrs.get("name", (0, 0, 0))) or "", "") not in ("", *keep):
                m.remove(place)                     # a part of the template this app doesn't use (texts, notices)
                break
            if name == "intent-filter":             # what belongs to Visualised's own app: opening links and files sent to it
                inside = [m.value(a.get("name", (0, 0, 0))) for p, n, d, a in m.elements() if p > place and n == "action" and d == depth + 1
                          and p < _end_of(m, place)]
                if any(i in ("android.intent.action.VIEW", "android.intent.action.SEND") for i in inside):
                    m.remove(place)
                    break
        else:
            break
    for place, name, depth, attrs in m.elements():
        if name == "manifest":
            m.set_string(place, attrs["package"], package)
            m.set_string(place, attrs["versionName"], version or "1.0")
            m.set_number(place, attrs["versionCode"], code)
            done.add("manifest")
        elif name == "application":
            m.set_string(place, attrs["label"], label)
            done.add("application")
        elif name == "provider" and (m.value(attrs.get("authorities", (0, 0, 0))) or "").endswith(".given"):
            m.set_string(place, attrs["authorities"], package + ".given")
            done.add("provider")
    if done != {"manifest", "application", "provider"}:
        raise ApkError("the template's manifest isn't laid out as expected (is the template the Visualised app?)")
    return m.bytes()


def _end_of(m, place):
    depth = 0
    for end in range(place, len(m.chunks)):
        kind = m.chunks[end][0]
        depth += 1 if kind == Manifest.START else -1 if kind == Manifest.END else 0
        if depth == 0:
            return end
    return len(m.chunks)


# ---------------------------------------------------------------- the developer's signing key
def key_files(folder=None):
    from . import licence
    folder = Path(folder) if folder else licence.PREFS_FILE.parent
    return folder / "android-key.pem", folder / "android-key.cert"


def signing_key(folder=None, name="", make=True):
    """This developer's key for signing Android apps, and its certificate (as DER): (private key, certificate, made).
    Made the first time one is wanted, and then always the same one. `made` is True when it has just been made:
    the moment to tell its owner to keep a copy."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError as exc:
        raise ApkError("Making an Android app needs the 'cryptography' package (pip install cryptography).") from exc
    import datetime
    key_file, cert_file = key_files(folder)
    if key_file.exists() and cert_file.exists():
        try:
            key = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
            return key, x509.load_pem_x509_certificate(cert_file.read_bytes()).public_bytes(serialization.Encoding.DER), False
        except Exception:
            raise ApkError(f"The signing key at {key_file} can't be read. If it is damaged, put back your copy of it: "
                           "apps already given out can only be updated with that key.") from None
    if key_file.exists() or cert_file.exists():
        raise ApkError(f"Half of the signing key is missing ({key_file} and {cert_file} go together). Put back your copy of both.")
    if not make:
        return None, None, False
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    who = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, (name or "Made with Visualised")[:60])])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = x509.CertificateBuilder().subject_name(who).issuer_name(who).public_key(key.public_key()) \
        .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1)) \
        .not_valid_after(now + datetime.timedelta(days=365 * 40)).sign(key, hashes.SHA256())
    key_file.parent.mkdir(parents=True, exist_ok=True)
    old = os.umask(0o077)
    try:
        key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    finally:
        os.umask(old)
    return key, cert.public_bytes(serialization.Encoding.DER), True


def key_id(certificate):
    """A short name for a key, from its certificate: the eight characters that also end the package names of the
    apps signed with it. A form remembers which key it was last exported with by this."""
    return hashlib.sha256(certificate).hexdigest()[:8]


def key_info(folder=None):
    """About this developer's signing key, for showing: exists, id, path, made (YYYY-MM-DD), saved (the day a copy
    was last saved with save_key, or "")."""
    from . import licence
    key_file, _ = key_files(folder)
    try:
        key, certificate, _ = signing_key(folder, make=False)
    except ApkError as exc:
        return {"exists": False, "id": "", "path": str(key_file), "made": "", "saved": "", "problem": str(exc)}
    if key is None:
        return {"exists": False, "id": "", "path": str(key_file), "made": "", "saved": "", "problem": ""}
    from cryptography import x509
    import datetime
    # (the certificate is dated a day before it was made, to allow for clocks that disagree; and the first name
    # below is newer than some installed copies of cryptography)
    starts = (lambda c: getattr(c, "not_valid_before_utc", None) or c.not_valid_before)(x509.load_der_x509_certificate(certificate))
    made = (starts + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    kept = licence.load_prefs().get("android_key_saved", "")
    saved = kept.split(" ", 1)[1] if isinstance(kept, str) and kept.startswith(key_id(certificate) + " ") else ""
    return {"exists": True, "id": key_id(certificate), "path": str(key_file), "made": made, "saved": saved, "problem": ""}


def save_key(to, folder=None):
    """Write a copy of the signing key as one file (the key and its certificate together), for its owner to keep
    somewhere safe. Notes that a copy was made, so Visualised can stop reminding."""
    import time
    from . import licence
    key_file, cert_file = key_files(folder)
    key, certificate, _ = signing_key(folder, make=False)
    if key is None:
        raise ApkError("There is no signing key on this computer yet. One is made the first time you export an Android app.")
    to = Path(os.path.expanduser(str(to)))
    old = os.umask(0o077)
    try:
        to.write_bytes(b"# Visualised: the key your Android apps are signed with. Keep this file safe and private.\n"
                       b"# To use it on another computer: Settings, Android Signing Key, Restore from a copy.\n"
                       + key_file.read_bytes() + cert_file.read_bytes())
    except OSError:
        raise ApkError(f"The copy couldn't be written to {to}.") from None
    finally:
        os.umask(old)
    if folder is None:
        prefs = licence.load_prefs()
        prefs["android_key_saved"] = f"{key_id(certificate)} {time.strftime('%Y-%m-%d')}"
        licence.save_prefs(prefs)
    return str(to)


def restore_key(copy, folder=None, replace=False):
    """Put a signing key back from a copy made by save_key. With a different key already here it refuses, unless
    replace is true (the key that was here is then kept beside it, renamed, not thrown away). Returns the key's id."""
    import time
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    from . import licence
    try:
        text = Path(os.path.expanduser(str(copy))).read_bytes()
    except OSError:
        raise ApkError("That file couldn't be read.") from None
    key_pem = re.search(rb"-----BEGIN PRIVATE KEY-----.*?-----END PRIVATE KEY-----\n?", text, re.S)
    cert_pem = re.search(rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----\n?", text, re.S)
    try:
        key = serialization.load_pem_private_key(key_pem.group(0), password=None)
        cert = x509.load_pem_x509_certificate(cert_pem.group(0))
        same = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo) == \
            cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    except Exception:
        same = False
    if not same:
        raise ApkError("That file isn't a copy of a Visualised signing key.")
    certificate = cert.public_bytes(serialization.Encoding.DER)
    key_file, cert_file = key_files(folder)
    try:
        _, here, _ = signing_key(folder, make=False)
    except ApkError:
        here = b"damaged"
    if here is not None and here != certificate:
        if not replace:
            raise ApkError("There is already a different signing key on this computer. Replacing it means apps signed with it "
                           "can no longer be updated from here.")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        for f in (key_file, cert_file):
            if f.exists():
                f.rename(f.with_name(f.name + ".replaced-" + stamp))
    key_file.parent.mkdir(parents=True, exist_ok=True)
    old = os.umask(0o077)
    try:
        key_file.write_bytes(key_pem.group(0).rstrip(b"\n") + b"\n")
        cert_file.write_bytes(cert_pem.group(0).rstrip(b"\n") + b"\n")
    finally:
        os.umask(old)
    if folder is None:                                  # it came from a copy, so a copy exists
        prefs = licence.load_prefs()
        prefs["android_key_saved"] = f"{key_id(certificate)} {time.strftime('%Y-%m-%d')}"
        licence.save_prefs(prefs)
    return key_id(certificate)


# ---------------------------------------------------------------- the zip, and its signature
def _lp(data):
    return struct.pack("<I", len(data)) + data


def _digest(parts):
    """APK Signature Scheme v2's digest of the file: each part cut into megabytes, each megabyte hashed, then those."""
    pieces = []
    for part in parts:
        for at in range(0, len(part), 1 << 20):
            chunk = part[at:at + (1 << 20)]
            pieces.append(hashlib.sha256(b"\xa5" + struct.pack("<I", len(chunk)) + chunk).digest())
    return hashlib.sha256(b"\x5a" + struct.pack("<I", len(pieces)) + b"".join(pieces)).digest()


def sign(apk, key, certificate):
    """An unsigned APK (bytes) -> the same, signed with APK Signature Scheme v2 (RSA, SHA-256)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    end = apk.rfind(b"PK\x05\x06")
    if end < 0 or len(apk) - end < 22 or struct.unpack_from("<H", apk, end + 20)[0] != len(apk) - end - 22:
        raise ApkError("the app's file isn't a zip that can be signed")
    cd_size, cd_at = struct.unpack_from("<II", apk, end + 12)
    if cd_at + cd_size != end:
        raise ApkError("the app's file isn't a zip that can be signed")
    contents, directory, tail = apk[:cd_at], apk[cd_at:end], apk[end:]
    algorithm = 0x0103                                              # RSASSA-PKCS1-v1_5 with SHA2-256
    digest = _digest([contents, directory, tail])                   # (the tail still says the directory starts where the signature will)
    signed = _lp(_lp(struct.pack("<I", algorithm) + _lp(digest))) + _lp(_lp(certificate)) + _lp(b"")
    signature = key.sign(signed, padding.PKCS1v15(), hashes.SHA256())
    public = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    signer = _lp(signed) + _lp(_lp(struct.pack("<I", algorithm) + _lp(signature))) + _lp(public)
    value = _lp(_lp(signer))
    pair = struct.pack("<QI", 4 + len(value), 0x7109871A) + value
    size = len(pair) + 8 + 16
    block = struct.pack("<Q", size) + pair + struct.pack("<Q", size) + b"APK Sig Block 42"
    tail = bytearray(tail)
    struct.pack_into("<I", tail, 16, cd_at + len(block))
    return contents + block + directory + bytes(tail)


def _png_size(data):
    return struct.unpack(">II", data[16:24]) if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR" else None


def _icon_at(picture, size):
    """The app's picture as a square PNG of a size, or None if it can't be made (then Visualised's own stays)."""
    try:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
        from PySide6.QtGui import QImage
    except ImportError:
        return None
    image = QImage()
    if isinstance(picture, (bytes, bytearray)):
        image.loadFromData(bytes(picture))
    else:
        image.load(str(picture))
    if image.isNull():
        return None
    image = image.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    if image.width() != size or image.height() != size:            # not square: centred on a clear square
        from PySide6.QtGui import QPainter
        square = QImage(size, size, QImage.Format_ARGB32)
        square.fill(0)
        p = QPainter(square)
        p.drawImage((size - image.width()) // 2, (size - image.height()) // 2, image)
        p.end()
        image = square
    raw = QByteArray()
    buf = QBuffer(raw)
    buf.open(QIODevice.WriteOnly)
    image.save(buf, "PNG")
    return bytes(raw)


class OtherKey(ApkError):
    """The app was last exported with a different signing key from the one on this computer."""


def build(page, name, out, version="", package="", icon=None, permissions=None, template=None, key_folder=None, owner="", signed_with=""):
    """Make the Android app. page: the app as a web page (bytes, as export makes). name: what it is called on the
    phone. out: where to write the .apk. signed_with: the id of the key the app was last exported with, if it has
    been before: with a different key here, nothing is made (OtherKey), since phones would refuse it as an update.
    Returns {"path", "package", "version", "code", "permissions", "size", "key", "key_id", "new_key"}: new_key is
    True when the signing key was made just now and its owner has yet to be told."""
    permissions = sorted(set(permissions if permissions is not None else ALWAYS) | set(ALWAYS))
    push = PUSH in permissions
    template = Path(template or os.environ.get("VML_APK_TEMPLATE" + ("_PUSH" if push else "")) or (PUSH_TEMPLATE if push else TEMPLATE))
    if push and not template.exists():
        raise ApkError(f"This app hears pushes (OnPush), which needs the push template ({template}). It comes with Visualised; "
                       "if you run from the source, build it with android/make-template.sh.")
    if not template.exists():
        raise ApkError(f"The Android template isn't here ({template}). It comes with Visualised; if you run from the source, "
                       "build it with android/make-template.sh.")
    name = str(name).strip() or "App"
    signed_with = str(signed_with or "").strip()
    if signed_with:
        _, has, _ = signing_key(key_folder, make=False)
        if has is None or key_id(has) != signed_with:
            raise OtherKey("This app was last exported with a different signing key (" + signed_with + ") from the one on this computer"
                           + (" (" + key_id(has) + ")" if has is not None else ": there is none here yet")
                           + ". Phones that have the app would refuse this as an update. Restore your key from its copy "
                           "(Settings, Android Signing Key), or export this as a new app.")
    key, certificate, new_key = signing_key(key_folder, owner)
    package = str(package or "").strip() or package_name(name, certificate)
    if not good_package(package):
        raise ApkError(f"'{package}' can't be an Android app's package name. It is lower-case words joined by dots, each "
                       "starting with a letter: com.example.myapp.")
    code = version_code(version)
    made = io.BytesIO()
    try:
        source = zipfile.ZipFile(template)
    except zipfile.BadZipFile:
        raise ApkError(f"The Android template at {template} is damaged.") from None
    with source, zipfile.ZipFile(made, "w") as target:
        names = source.namelist()
        if "AndroidManifest.xml" not in names or "classes.dex" not in names:
            raise ApkError(f"The Android template at {template} isn't the Visualised app.")

        def put(entry, data, method):
            info = zipfile.ZipInfo(entry, (1981, 1, 1, 1, 1, 2))
            info.compress_type, info.external_attr, info.create_system = method, 0, 0
            if method == zipfile.ZIP_STORED:                        # what Android reads in place must start on a 4-byte line
                gap = (-(target.fp.tell() + 30 + len(entry.encode()) + 6)) % 4
                info.extra = struct.pack("<HHH", 0xD935, 2 + gap, 4) + b"\0" * gap
            target.writestr(info, data, compresslevel=9 if method == zipfile.ZIP_DEFLATED else None)

        for item in source.infolist():
            if item.filename.startswith("META-INF/") or item.filename.startswith("assets/app/"):
                continue                                            # the old signature, and build notes: not ours
            data = source.read(item)
            if item.filename == "AndroidManifest.xml":
                data = rewrite_manifest(data, package, name, str(version or "1.0"), code, permissions)
            elif icon is not None and item.filename.startswith("res/") and item.filename.endswith(".png"):
                size = _png_size(data)
                if size and size[0] == size[1] and size[0] in (48, 72, 96, 144, 192):       # the launcher pictures
                    data = _icon_at(icon, size[0]) or data
            put(item.filename, data, item.compress_type)
        put("assets/app/index.html", page if isinstance(page, bytes) else str(page).encode("utf-8"), zipfile.ZIP_DEFLATED)
    out = Path(os.path.expanduser(str(out)))
    out.write_bytes(sign(made.getvalue(), key, certificate))
    return {"path": str(out), "package": package, "version": str(version or "1.0"), "code": code, "permissions": permissions,
            "size": out.stat().st_size, "key": str(key_files(key_folder)[0]), "key_id": key_id(certificate), "new_key": new_key}


def from_page(page, out, owner="", **more):
    """Make the Android app from an app's exported page (a file): its name, version, picture and package are read
    from the page itself, and its permissions worked out from its scripts. Returns what build returns."""
    import base64
    import json
    from html import unescape
    page = Path(page)
    text = page.read_text(encoding="utf-8")
    head = lambda pattern: (lambda m: unescape(m.group(1)).strip() if m else "")(re.search(pattern, text, re.S))

    def words(thing):                                    # every piece of script in the page, wherever it is kept
        if isinstance(thing, str):
            yield thing
        elif isinstance(thing, dict):
            for v in thing.values():
                yield from words(v)
        elif isinstance(thing, list):
            for v in thing:
                yield from words(v)
    data = re.search(r"const VML = (\{.*?\});\n", text, re.S)
    carried = json.loads(data.group(1)) if data else {}
    code = "\n".join(words([carried.get("scripts", {}), carried.get("modules", [])]))
    icon = head(r'<link rel="icon" href="([^"]*)"')
    if icon.startswith("data:") and "," in icon:
        picture = base64.b64decode(icon.split(",", 1)[1]) if ";base64" in icon.split(",", 1)[0] else None
    else:
        picture = str(page.parent / icon) if icon and (page.parent / icon).is_file() else None
    how = {"version": head(r'<meta name="app-version" content="([^"]*)"'), "icon": picture, "permissions": permissions_for(code),
           "package": head(r'<meta name="android-package" content="([^"]*)"'), "owner": owner,
           "signed_with": head(r'<meta name="android-key" content="([^"]*)"')}
    how.update(more)                                     # (to export as a new app: package="" and signed_with="")
    return build(text.encode("utf-8"), head(r"<title>(.*?)</title>") or "App", out, **how)


def remember(form, package, key):
    """Write into a form's file (its @Window) the package name and key it has just been exported with, so that the
    next export, here or on another computer, makes an update to the same app or says why it can't."""
    path = Path(form)
    lines = path.read_text(encoding="utf-8").split("\n")
    start = next((i for i, line in enumerate(lines) if line.startswith("@Window ")), None)
    if start is None:
        return False
    end = next((i for i in range(start + 1, len(lines)) if not lines[i].strip() or lines[i].startswith("@")), len(lines))
    block = [l for l in lines[start + 1:end] if not re.match(r"Android(Package|Key)=", l)]
    new = lines[:start + 1] + block + [f"AndroidPackage={package}", f"AndroidKey={key}"] + lines[end:]
    if new != lines:
        path.write_text("\n".join(new), encoding="utf-8")
    return True
