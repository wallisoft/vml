"""Export as an Android app: an app's page inside a copy of the Visualised phone app, with its own name, picture,
version and identity, only the permissions it uses, and a signature. Checked here by taking the file apart again,
and with Android's own tools (zipalign, apksigner, aapt2) where they are installed."""
import base64, glob, hashlib, json, os, re, shutil, struct, subprocess, sys, tempfile, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HOME = tempfile.mkdtemp(prefix="vml-home-")
os.environ["HOME"] = os.environ["USERPROFILE"] = HOME
os.environ["VML_PREFS"] = os.path.join(HOME, ".vml", "prefs.json")
from pathlib import Path
try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
except ImportError:
    print("the cryptography package isn't installed: skipping\n0/0 passed")
    raise SystemExit(0)
from vml import apk, licence as L
from vml.html import export_html
L.PREFS_FILE = Path(HOME) / ".vml" / "prefs.json"

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="vml-apk-")
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

if not apk.TEMPLATE.exists():
    print(f"the Android template isn't here ({apk.TEMPLATE}): build it with android/make-template.sh. Skipping\n0/0 passed")
    raise SystemExit(0)

# ---- the small rules
check("a version as written becomes the number Android compares", [apk.version_code(v) for v in ("1.4.2", "2", "0.9", "", "beta", "1.2.3.4", "3.150.7")], [10402, 20000, 900, 1, 1, 10203, 39907])
cert = b"a certificate"
check("an app's package name is its own: the app's name and part of its maker's key",
      (apk.package_name("Morse Torch", cert), apk.package_name("3D Dice!", cert), apk.package_name("", cert), apk.package_name("Morse Torch", b"another") != apk.package_name("Morse Torch", cert)),
      ("io.visualised.made.morsetorch.k" + hashlib.sha256(cert).hexdigest()[:8], "io.visualised.made.a3ddice.k" + hashlib.sha256(cert).hexdigest()[:8], "io.visualised.made.app.k" + hashlib.sha256(cert).hexdigest()[:8], True))
check("what can and can't be a package name", [apk.good_package(p) for p in ("com.example.myapp", "io.visualised.made.x.k1", "myapp", "Com.Example.app", "com.1example.app", "com..app", "com.example.my-app")], [True, True, False, False, False, False, False])
check("the permissions asked for are those the scripts use, and no more",
      (apk.permissions_for('Vml("SetProperty", "a", "Text", "Torch")\nVml("InfoDialog", "hello")'), apk.permissions_for('Vml("ScanCode", "Got")\nVml("GetLocation", "Here")\nVml("Notify", "a", "b")'), apk.permissions_for("")),
      (["ACCESS_NETWORK_STATE", "CAMERA", "INTERNET", "VIBRATE"][0:0] or sorted({"ACCESS_NETWORK_STATE", "INTERNET", "CAMERA"}), sorted(["ACCESS_COARSE_LOCATION", "ACCESS_FINE_LOCATION", "ACCESS_NETWORK_STATE", "CAMERA", "INTERNET", "POST_NOTIFICATIONS"]), ["ACCESS_NETWORK_STATE", "INTERNET"]))

# ---- an app, exported
page = Path(export_html(os.path.join(HERE, "apps", "MorseTorch.vml"), os.path.join(WORK, "mt.html"))).read_bytes()
scripts = open(os.path.join(HERE, "apps", "MorseTorch.vml")).read()
icon = os.path.join(HERE, "apps", "MorseTorch.png")
KEYS = os.path.join(WORK, "keys")
out = os.path.join(WORK, "MorseTorch.apk")
made = apk.build(page, "Morse Torch", out, version="1.4.2", icon=icon if os.path.exists(icon) else None, permissions=apk.permissions_for(scripts), key_folder=KEYS, owner="Ann Maker")
z = zipfile.ZipFile(out)
names = z.namelist()
check("the .apk is a zip with the app's page inside, as it was exported, and none of the template's own signature or notes",
      (z.testzip(), z.read("assets/app/index.html") == page, [n for n in names if n.startswith("META-INF/")], "classes.dex" in names and "resources.arsc" in names), (None, True, [], True))
check("what it reports: where, its name, version and size", (made["path"], made["version"], made["code"], made["size"] == os.path.getsize(out), made["package"].startswith("io.visualised.made.morsetorch.k")), (out, "1.4.2", 10402, True, True))

m = apk.Manifest(z.read("AndroidManifest.xml"))
els = list(m.elements())
val = lambda name, attr: [m.value(a[attr]) for p, n, d, a in els if n == name and attr in a]
top = next(a for p, n, d, a in els if n == "manifest")
check("the manifest: its own package, version and name", (m.value(top["package"]), m.value(top["versionName"]), top["versionCode"][1:], val("application", "label")), (made["package"], "1.4.2", (0x10, 10402), ["Morse Torch"]))
check("it asks for the camera, the microphone and to vibrate, as Morse Torch uses, and not for location, Bluetooth or notifications",
      sorted(v.replace("android.permission.", "") for v in val("uses-permission", "name")), ["ACCESS_NETWORK_STATE", "CAMERA", "INTERNET", "MODIFY_AUDIO_SETTINGS", "RECORD_AUDIO", "VIBRATE", "WAKE_LOCK"])
actions = val("action", "name")
check("it opens from its own icon, and doesn't offer itself for web links or files as Visualised does",
      ("android.intent.action.MAIN" in actions, [a for a in actions if a in ("android.intent.action.VIEW", "android.intent.action.SEND")], val("data", "scheme")), (True, [], []))
check("what it hands to other apps is under its own name, so it can sit beside Visualised and other exported apps", val("provider", "authorities"), [made["package"] + ".given"])
check("the rest of the app is untouched: its screen, its service and its receiver are still named", (len(val("activity", "name")), len(val("service", "name")), len(val("receiver", "name"))), (1, 1, 1))

t = zipfile.ZipFile(apk.TEMPLATE)
tm = apk.Manifest(t.read("AndroidManifest.xml"))
check("the manifest, read and written back unchanged, says exactly what it said", [(n, d, sorted((k, v[1], tm.value(v) or v[2]) for k, v in a.items())) for p, n, d, a in apk.Manifest(tm.bytes()).elements()],
      [(n, d, sorted((k, v[1], tm.value(v) or v[2]) for k, v in a.items())) for p, n, d, a in tm.elements()])
pictures = lambda zf: {apk._png_size(zf.read(n))[0]: zf.read(n) for n in zf.namelist() if n.startswith("res/") and n.endswith(".png") and apk._png_size(zf.read(n))}
if os.path.exists(icon):
    mine, theirs = pictures(z), pictures(t)
    check("the launcher pictures are the app's own, at each of the five sizes", (sorted(mine), [mine[s] != theirs[s] for s in sorted(mine)], [apk._png_size(mine[s]) for s in sorted(mine)]),
          ([48, 72, 96, 144, 192], [True] * 5, [(s, s) for s in (48, 72, 96, 144, 192)]))

def data_offsets(path):
    """Where each stored entry's bytes begin in the file."""
    raw, out_ = open(path, "rb").read(), {}
    for info in zipfile.ZipFile(path).infolist():
        n, e = struct.unpack_from("<HH", raw, info.header_offset + 26)
        if info.compress_type == zipfile.ZIP_STORED:
            out_[info.filename] = info.header_offset + 30 + n + e
    return out_
stored = data_offsets(out)
check("what Android reads in place (resources.arsc, and anything else not compressed) starts on a 4-byte line", ("resources.arsc" in stored, [n for n, at in stored.items() if at % 4]), (True, []))

def verify(path):
    """Check an APK's v2 signature as a phone does: the file's digest, and the signature over it. The signer's certificate, or why not."""
    raw = open(path, "rb").read()
    end = raw.rfind(b"PK\x05\x06")
    cd_size, cd_at = struct.unpack_from("<II", raw, end + 12)
    if raw[cd_at - 16:cd_at] != b"APK Sig Block 42":
        return "no signing block"
    size = struct.unpack_from("<Q", raw, cd_at - 24)[0]
    start = cd_at - size - 8
    block, at, value = raw[start + 8:cd_at - 24], 0, None
    while at < len(block):
        n, key = struct.unpack_from("<QI", block, at)
        if key == 0x7109871A:
            value = block[at + 12:at + 8 + n]
        at += 8 + n
    if value is None:
        return "no v2 signature"
    def lp(b, at=0):
        n = struct.unpack_from("<I", b, at)[0]
        return b[at + 4:at + 4 + n], at + 4 + n
    signer, _ = lp(lp(value)[0])
    signed, at = lp(signer); sigs, at = lp(signer, at); public, _ = lp(signer, at)
    sig_entry, _ = lp(sigs); signature, _ = lp(sig_entry, 4)
    digests, at = lp(signed); certs, _ = lp(signed, at)
    digest, _ = lp(lp(digests)[0], 4)
    der, _ = lp(certs)
    certificate = x509.load_der_x509_certificate(der)
    if certificate.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo) != public:
        return "the key doesn't match the certificate"
    try:
        certificate.public_key().verify(signature, signed, padding.PKCS1v15(), hashes.SHA256())
    except Exception:
        return "the signature is wrong"
    tail = bytearray(raw[end:]); struct.pack_into("<I", tail, 16, start)
    if apk._digest([raw[:start], raw[cd_at:end], bytes(tail)]) != digest:
        return "the file has been changed since it was signed"
    return der
signer = verify(out)
check("it is signed (APK Signature Scheme v2), and the signature holds", (isinstance(signer, bytes), x509.load_der_x509_certificate(signer).subject.rfc4514_string() if isinstance(signer, bytes) else signer), (True, "CN=Ann Maker"))
raw = bytearray(open(out, "rb").read()); raw[2000] ^= 1
open(os.path.join(WORK, "bent.apk"), "wb").write(raw)
check("one bit changed anywhere and it no longer verifies", verify(os.path.join(WORK, "bent.apk")), "the file has been changed since it was signed")

# ---- the key
key_file, cert_file = apk.key_files(KEYS)
check("the first export makes the signing key and says so; it is this user's to read alone", (made["new_key"], made["key"] == str(key_file), oct(os.stat(key_file).st_mode & 0o777), cert_file.exists()), (True, True, "0o600", True))
again = apk.build(page, "Morse Torch", os.path.join(WORK, "again.apk"), version="1.5", key_folder=KEYS)
check("the next export uses the same key, so it is an update to the same app: same package, same signer, a higher version",
      (again["new_key"], again["package"] == made["package"], verify(again["path"]) == signer, again["code"] > made["code"]), (False, True, True, True))
other = apk.build(page, "Morse Torch", os.path.join(WORK, "other.apk"), key_folder=os.path.join(WORK, "someone-else"))
check("somebody else's Morse Torch is a different app: another key, another package", (other["package"] != made["package"], verify(other["path"]) != signer), (True, True))
chosen = apk.build(page, "Morse Torch", os.path.join(WORK, "chosen.apk"), package="com.example.morse", key_folder=KEYS)
check("a package name can be chosen", (chosen["package"], apk.Manifest(zipfile.ZipFile(chosen["path"]).read("AndroidManifest.xml")).strings[-4:].count("com.example.morse") >= 1), ("com.example.morse", True))
def refused(**more):
    try:
        apk.build(page, "X", os.path.join(WORK, "no.apk"), **dict(dict(key_folder=KEYS), **more))
        return ""
    except apk.ApkError as exc:
        return str(exc)
check("a package name that can't be one is refused, in words", refused(package="My App")[:42], "'My App' can't be an Android app's package")
check("no template: says where it should be and how to make it", "android/make-template.sh" in refused(template=os.path.join(WORK, "nowhere.apk")), True)
open(os.path.join(WORK, "junk.apk"), "wb").write(b"not a zip")
check("a damaged template says so", refused(template=os.path.join(WORK, "junk.apk"))[-11:], "is damaged.")
half = os.path.join(WORK, "half"); os.makedirs(half); shutil.copy(key_file, half)
check("half a key is not quietly replaced with a new one: that would orphan apps already given out", "Put back your copy of both" in refused(key_folder=half), True)
check("and nothing was written when it was refused", os.path.exists(os.path.join(WORK, "no.apk")), False)

# ---- Android's own tools, where they are
tools = sorted(glob.glob(os.path.join(os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or os.path.expanduser("~/Android/Sdk"), "build-tools", "*")))
if not tools and os.path.isdir("/home/claude/android-sdk/build-tools"):
    tools = sorted(glob.glob("/home/claude/android-sdk/build-tools/*"))
if tools:
    run = lambda *cmd: subprocess.run(cmd, capture_output=True, text=True)
    check("Android's zipalign agrees it is aligned", run(os.path.join(tools[-1], "zipalign"), "-c", "4", out).returncode, 0)
    said = run(os.path.join(tools[-1], "apksigner"), "verify", "--verbose", "--min-sdk-version", "29", out)
    check("Android's apksigner verifies the signature", (said.returncode, "Verified using v2 scheme (APK Signature Scheme v2): true" in said.stdout), (0, True))
    badge = run(os.path.join(tools[-1], "aapt2"), "dump", "badging", out).stdout
    check("Android's aapt2 reads it as the app it should be",
          (f"package: name='{made['package']}' versionCode='10402' versionName='1.4.2'" in badge, "application-label:'Morse Torch'" in badge, "launchable-activity: name='io.visualised.app.MainActivity'" in badge, "sdkVersion:'29'" in badge),
          (True, True, True, True))
else:
    print("      (Android's build tools aren't installed here, so zipalign, apksigner and aapt2 were not asked)")

# ---- from the designer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine
said = []
eng = Engine()
eng.cmd_InfoDialog = lambda msg, title="", picture="": said.append((str(title), str(msg)))
eng.load(os.path.join(HERE, "designer", "designer.vml"))
for _ in range(4):
    QApplication.instance().processEvents()
form = os.path.join(WORK, "Hello.vml")
open(form, "w").write("""@Window Hello
Title=Hello There
Width=320
Height=480

@Canvas c
Parent=Hello

@Button btnGo
Parent=c
Canvas.Left=20
Canvas.Top=20
Width=120
Height=40
Content=Buzz
OnClick=Buzz

@Script Buzz
Interpreter=lua
<<LUA
Vml("Vibrate", "80")
LUA
""")
eng.cmd_ImportVml(form, "Surface")
for _ in range(4):
    QApplication.instance().processEvents()
target = os.path.join(WORK, "Hello.apk")
eng.cmd_FileSaveDialog = lambda title="", default="", ext="": target
check("Community: the designer refuses, and says it is part of Pro", (eng.vml("ExportApk", "Surface", target), "Visualised Pro" in said[-1][1], os.path.exists(target)), ("", True, False))
eng.licence_override = "pro"
said.clear()
eng.run_script("ExportAndroid")
print("      said:", [(t, m[:160]) for t, m in said]) if not os.path.exists(target) else None
got = apk.Manifest(zipfile.ZipFile(target).read("AndroidManifest.xml"))
gels = list(got.elements())
check("Pro: File, Export, Android app writes the app, named from the form's title, asking only to vibrate",
      ([got.value(a["label"]) for p, n, d, a in gels if n == "application"], sorted(got.value(a["name"]).split(".")[-1] for p, n, d, a in gels if n == "uses-permission"), isinstance(verify(target), bytes)),
      (["Hello There"], ["ACCESS_NETWORK_STATE", "INTERNET", "VIBRATE"], True))
check("it says what was made and what the phone will be asked for", (said[0][0], "Hello.apk" in said[0][1], "It will ask the phone for: vibrate." in said[0][1], "Google Play" in said[0][1]), ("Export", True, True, True))
check("and, the first time, that the signing key must be kept safe, and where it is", (len(said), said[1][0], "android-key.pem" in said[1][1] and "android-key.cert" in said[1][1], os.path.exists(os.path.join(HOME, ".vml", "android-key.pem"))), (2, "Your signing key", True, True))
said.clear()
eng.run_script("ExportAndroid")
check("the second time it doesn't say that again", [t for t, _ in said], ["Export"])

print(f"\n{sum(ok)}/{len(ok)} passed")
sys.exit(0 if all(ok) else 1)
