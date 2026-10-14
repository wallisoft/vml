"""
Disk images and partitions, mounted where the user can open them: an ISO, IMG, VHD, VHDX, VMDK or QCOW2 file, or a
partition on one of the computer's disks. Mountie's other half (vml/sshdrive.py is the SSH half).

    Linux     through udisks (what the desktop itself uses: no root needed, and it shows in Files), so
                  an ISO or IMG, or a fixed VHD (which is a plain disk with a footer), becomes a loop device and its
                  partitions are mounted under /media/<you>/...; a VHDX, a dynamic VHD, VMDK or QCOW2 goes through
                  guestmount (libguestfs-tools) when it's installed;
              as root, without udisks: losetup and mount (and qemu-nbd for the others);
              an ISO with neither: fuseiso.
    Windows   Mount-DiskImage for ISO, VHD and VHDX (a drive letter each; a VHD asks Windows for admin, as Windows
              itself does), and a drive letter given to, or taken from, a partition.
    macOS     hdiutil for ISO, IMG and DMG; diskutil for partitions.

An item is a plain dict: {"name", "kind": "iso" | "vhd" | "part", "path": the file or the partition (/dev/sdb1, or
"disk:part" numbers on Windows), "readonly"}. Mounting answers what it reached; the Disks manager remembers what it
mounted so it can undo it, and tells on_change(name, state, detail) like the SSH drives do.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading

WINDOWS = sys.platform.startswith("win")
MAC = sys.platform == "darwin"
IMAGE_KINDS = {".iso": "iso", ".img": "iso", ".raw": "iso", ".dmg": "iso",
               ".vhd": "vhd", ".vhdx": "vhd", ".vmdk": "vhd", ".qcow2": "vhd", ".vdi": "vhd"}
SYSTEM_MOUNTS = ("/", "/boot", "/boot/efi", "/efi", "/home", "/usr", "/var", "[SWAP]")


class DiskError(Exception):
    pass


def kind_of(path):
    """"iso" for plain images (ISO, IMG, DMG), "vhd" for virtual disks, "part" for a device; by name, then by look."""
    if str(path).startswith("/dev/") or re.fullmatch(r"\d+:\d+", str(path)):
        return "part"
    return IMAGE_KINDS.get(os.path.splitext(str(path))[1].lower(), "iso")


def vhd_type(path):
    """For a .vhd: "fixed" (a plain disk with a 512-byte footer), "dynamic", "differencing", or "" if it isn't one.
    For anything else: its format from its first bytes (vhdx, qcow2, vmdk, vdi), or ""."""
    try:
        with open(path, "rb") as f:
            head = f.read(512)
            f.seek(-512, os.SEEK_END)
            foot = f.read(512)
    except OSError:
        return ""
    if head.startswith(b"vhdxfile"):
        return "vhdx"
    if head.startswith(b"QFI\xfb"):
        return "qcow2"
    if head.startswith(b"KDMV") or b"# Disk DescriptorFile" in head:
        return "vmdk"
    if b"<<< Oracle VM VirtualBox Disk Image >>>" in head[:64]:
        return "vdi"
    if foot.startswith(b"conectix"):
        return {2: "fixed", 3: "dynamic", 4: "differencing"}.get(int.from_bytes(foot[60:64], "big"), "dynamic")
    return ""


FORMAT_NAMES = {"fixed": "fixed VHD", "dynamic": "dynamic VHD", "differencing": "differencing VHD", "vhdx": "VHDX",
                "qcow2": "QCOW2", "vmdk": "VMDK", "vdi": "VDI"}


def info(path):
    """What a disk image is, read from the file itself (so it works the same everywhere, and quickly):
    {size, size_text, format, label, partitions, folder}. format: "ISO 9660", "raw disk", "fixed VHD", "VHDX"..."""
    out = {"size": 0, "size_text": "", "format": "", "label": "", "partitions": 0, "folder": os.path.dirname(str(path))}
    try:
        out["size"] = os.path.getsize(path)
        out["size_text"] = _size(out["size"])
        fmt = vhd_type(path)
        with open(path, "rb") as f:
            f.seek(0x8000)
            pvd = f.read(64)
            if pvd[1:6] == b"CD001":                           # an ISO 9660 volume: its name is in the descriptor
                out["format"] = "ISO 9660"
                out["label"] = pvd[40:72].decode("ascii", "replace").strip()
            if fmt and fmt != "fixed":
                out["format"] = FORMAT_NAMES.get(fmt, fmt.upper())
                return out                                     # (its partitions are inside its own layout)
            f.seek(0)
            mbr = f.read(512)
            if mbr[510:512] == b"\x55\xaa":
                types = [mbr[446 + 16 * i + 4] for i in range(4)]
                if 0xEE in types:                              # GPT: count its used entries
                    f.seek(512)
                    hdr = f.read(92)
                    if hdr[:8] == b"EFI PART":
                        start = int.from_bytes(hdr[72:80], "little") * 512
                        count = int.from_bytes(hdr[80:84], "little")
                        size = int.from_bytes(hdr[84:88], "little") or 128
                        f.seek(start)
                        table = f.read(min(count, 256) * size)
                        out["partitions"] = sum(1 for i in range(0, len(table), size) if any(table[i:i + 16]))
                elif not out["format"]:
                    out["partitions"] = sum(1 for t in types if t)
            if not out["format"]:
                out["format"] = FORMAT_NAMES["fixed"] if fmt == "fixed" else "raw disk"
    except OSError as e:
        out["error"] = str(e)
    return out


def _run(cmd, timeout=60, input=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input)
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} isn't installed"
    except subprocess.TimeoutExpired:
        return 124, "", f"{cmd[0]} took too long"


def _root():
    return hasattr(os, "geteuid") and os.geteuid() == 0


# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
#  What's there: the computer's partitions
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════

def _size(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1000 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") or n >= 100 else f"{n:.1f} {unit}"
        n /= 1000


def partitions():
    """The partitions a user might want to open: [{path, name, label, fstype, size, mounted, removable, system}].
    The ones the computer itself runs from are marked system (shown, never unmounted)."""
    if WINDOWS:
        return _win_partitions()
    if MAC:
        return _mac_partitions()
    code, out, err = _run(["lsblk", "-J", "-b", "-o", "NAME,PATH,SIZE,FSTYPE,LABEL,TYPE,MOUNTPOINTS,RM,HOTPLUG,MODEL"])
    if code:
        raise DiskError(err.strip() or "lsblk failed")
    found = []

    def walk(devs, model=""):
        for d in devs:
            kids = d.get("children") or []
            mounts = [m for m in (d.get("mountpoints") or []) if m]
            if d.get("type") in ("part", "crypt", "lvm") or (d.get("type") == "disk" and not kids and d.get("fstype")):
                if d.get("fstype") and d.get("fstype") not in ("swap", "LVM2_member", "crypto_LUKS", "linux_raid_member"):
                    found.append({"path": d["path"], "name": d["name"], "label": d.get("label") or "",
                                  "fstype": d.get("fstype") or "", "size": _size(d.get("size")),
                                  "mounted": mounts[0] if mounts else "",
                                  "removable": bool(d.get("rm") or d.get("hotplug")),
                                  "system": any(m in SYSTEM_MOUNTS or m.startswith("/snap/") for m in mounts)})
            if d.get("type") != "loop" or kids:
                walk(kids, d.get("model") or model)
    walk([d for d in json.loads(out).get("blockdevices", []) if not (d.get("type") == "loop" and d.get("size") in (None, 0))])
    return [p for p in found if not (p["path"].startswith("/dev/loop") and p["system"])]


def _win_partitions():
    script = r"""
$ErrorActionPreference = 'SilentlyContinue'
Get-Partition | Where-Object { $_.Type -notin @('Reserved','System','Recovery','Unknown') } | ForEach-Object {
  $v = Get-Volume -Partition $_
  [pscustomobject]@{ path = "$($_.DiskNumber):$($_.PartitionNumber)"; label = "$($v.FileSystemLabel)";
    fstype = "$($v.FileSystem)"; size = [int64]$_.Size; letter = "$($_.DriveLetter)".Trim([char]0);
    boot = [bool]($_.IsBoot -or $_.IsSystem) }
} | ConvertTo-Json -Compress
"""
    code, out, err = _ps(script)
    rows = json.loads(out) if out.strip() else []
    rows = rows if isinstance(rows, list) else [rows]
    return [{"path": r["path"], "name": f"Disk {r['path'].replace(':', ' part ')}", "label": r.get("label") or "",
             "fstype": r.get("fstype") or "", "size": _size(r.get("size")),
             "mounted": (r["letter"] + ":") if r.get("letter") else "", "removable": False, "system": bool(r.get("boot"))}
            for r in rows]


def _mac_partitions():
    code, out, _ = _run(["diskutil", "list", "-plist"])
    import plistlib
    found = []
    try:
        data = plistlib.loads(out.encode())
    except Exception:
        return found
    for disk in data.get("AllDisksAndPartitions", []):
        for p in disk.get("Partitions", []) + disk.get("APFSVolumes", []):
            mp = p.get("MountPoint", "")
            found.append({"path": "/dev/" + p.get("DeviceIdentifier", ""), "name": p.get("DeviceIdentifier", ""),
                          "label": p.get("VolumeName", ""), "fstype": p.get("Content", ""), "size": _size(p.get("Size")),
                          "mounted": mp, "removable": False, "system": mp in ("/", "/System/Volumes/Data")})
    return found


# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
#  Mounting
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════

class Mounted:
    """One thing mounted, and how to undo it. .places: where its contents are (folders, or drive letters)."""

    def __init__(self, item, how, places, undo):
        self.item, self.how, self.places, self._undo = item, how, places, undo

    def stop(self):
        self._undo()


def _local(item):
    """A folder seen through an ignore list, or a RAM disk (vml/localdrives.py)."""
    from . import localdrives
    from .sshdrive import RemoteError
    try:
        d = localdrives.start(item)
    except RemoteError as e:
        raise DiskError(str(e))
    how = "RAM" if item.get("kind") == "ram" else "filtered"
    return Mounted(item, how, [d.mountpoint], d.stop)


def mount(item):
    path = str(item.get("path") or "")
    kind = item.get("kind") or kind_of(path)
    if kind in ("folder", "ram"):
        return _local(item)
    ro = bool(item.get("readonly", kind == "iso"))
    if kind != "part" and not os.path.isfile(path):
        raise DiskError(f"There's no file at {path}.")
    if WINDOWS:
        return _win_partition(item) if kind == "part" else _win_image(path, ro)
    if MAC:
        return _mac_partition(path) if kind == "part" else _mac_image(path, ro)
    if kind == "part":
        return _linux_partition(path, ro)
    fmt = vhd_type(path)
    plain = fmt in ("", "fixed")                               # a raw disk (no-stick's .img), an ISO, or a fixed VHD:
                                                               # a loop device shows these as they are
    if plain:
        if shutil.which("udisksctl") and not _root():
            return _udisks_image(path, ro)
        if _root():
            try:
                return _loop_image(path, ro)
            except DiskError:
                if not (path.lower().endswith(".iso") and shutil.which("fuseiso")):
                    raise                                       # (a kernel without ISO 9660: fuseiso reads it itself)
                return _fuseiso(path, item.get("name"))
        if path.lower().endswith(".iso") and shutil.which("fuseiso"):
            return _fuseiso(path, item.get("name"))
        raise DiskError("Opening disk images needs udisks (it comes with Ubuntu's desktop: sudo apt install udisks2).")
    if shutil.which("guestmount"):
        return _guestmount(path, ro, item.get("name"))
    if _root() and shutil.which("qemu-nbd"):
        try:
            return _nbd_image(path, ro)
        except DiskError:
            pass                                               # (no nbd here: say what would open it)
    raise DiskError(f"A {fmt.upper() or 'virtual disk'} file needs guestmount to open it here "
                    "(sudo apt install libguestfs-tools).")


# ── Linux: udisks (the desktop's own way: no root, and it shows in Files) ──

def _children(dev):
    """A device and its partitions: [(path, fstype, [mountpoints])]."""
    code, out, _ = _run(["lsblk", "-J", "-o", "PATH,FSTYPE,MOUNTPOINTS", dev])
    if code:
        return []
    rows = []

    def walk(ds):
        for d in ds:
            fs = d.get("fstype") or ""
            if not fs and _root():                             # (lsblk learns these from udev; blkid looks for itself)
                fs = _run(["blkid", "-p", "-o", "value", "-s", "TYPE", d["path"]])[1].strip()   # (-p: never a cached answer)
            rows.append((d["path"], fs, [m for m in (d.get("mountpoints") or []) if m]))
            walk(d.get("children") or [])
    walk(json.loads(out).get("blockdevices", []))
    return rows


def _nodes(dev):
    """As root where nothing makes device files (no udev: a container, a rescue system), make the partitions' own
    from what the kernel says about them."""
    import stat
    base = os.path.basename(dev)
    sysdir = f"/sys/block/{base}"
    if not _root() or not os.path.isdir(sysdir):
        return
    for part in os.listdir(sysdir):
        node = "/dev/" + part
        if part.startswith(base) and os.path.exists(f"{sysdir}/{part}/dev") and not os.path.exists(node):
            major, minor = map(int, open(f"{sysdir}/{part}/dev").read().split(":"))
            try:
                os.mknod(node, stat.S_IFBLK | 0o660, os.makedev(major, minor))
            except OSError:
                pass


def _settle(dev, want_parts=True, wait=4.0):
    """Partitions take a moment to appear after a loop device is made."""
    import time
    _nodes(dev)
    end = time.time() + wait
    rows = _children(dev)
    while time.time() < end and want_parts and not any(fs for _, fs, _ in rows):
        time.sleep(0.25)
        _nodes(dev)
        rows = _children(dev)
    return rows


def _udisks_image(path, ro):
    cmd = ["udisksctl", "loop-setup", "--no-user-interaction", "-f", path] + (["-r"] if ro else [])
    code, out, err = _run(cmd)
    m = re.search(r"as (/dev/loop\d+)", out)
    if code or not m:
        net = _on_network(path)
        if net:
            raise DiskError(f"{os.path.basename(path)} is on a network drive ({net}), and this computer couldn't open it "
                            f"as a disk from there. Copy it here first, or open it on the computer it's on. "
                            f"({_plain(err or out, path)})")
        raise DiskError(_plain(err or out, path))
    loop = m.group(1)
    mounts = _udisks_mount_all(loop)
    places = [mp for _, mp in mounts]
    if not places:
        _run(["udisksctl", "loop-delete", "--no-user-interaction", "-b", loop])
        raise DiskError(f"{os.path.basename(path)} has nothing on it that this computer can read.")

    def undo():
        done = {dev for dev, _ in mounts}
        for dev in list(done) + [d for d, fs, mps in _children(loop) if mps and d not in done]:
            _run(["udisksctl", "unmount", "--no-user-interaction", "-b", dev])
        _run(["udisksctl", "loop-delete", "--no-user-interaction", "-b", loop])
    return Mounted({"path": path}, "udisks", places, undo)


def _udisks_mount_all(dev):
    """Mount every filesystem on a device (the desktop may have got there first: that's fine). [(device, where)]"""
    places = []
    for part, fs, mps in _settle(dev):
        if not fs or fs in ("swap",):
            continue
        if not mps:
            code, out, err = _run(["udisksctl", "mount", "--no-user-interaction", "-b", part])
            m = re.search(r" at (.+?)\.?$", out.strip())
            if m:
                mps = [m.group(1)]
            else:
                mps = next((x[2] for x in _children(part) if x[0] == part), [])
        places += [(part, mp) for mp in mps]
    return places


def _on_network(path):
    """The filesystem a file is on, when it's a network or FUSE one (an SSH drive...), else ""."""
    try:
        best, kind = "", ""
        real = os.path.realpath(path)
        for line in open("/proc/mounts"):
            dev, mp, fs = line.split()[:3]
            mp = mp.replace("\\040", " ")
            if (real == mp or real.startswith(mp.rstrip("/") + "/")) and len(mp) > len(best):
                best, kind = mp, fs
        return kind if kind.startswith("fuse") or kind in ("nfs", "nfs4", "cifs", "smb3", "9p") else ""
    except OSError:
        return ""


def _plain(text, path=""):
    t = (text or "").strip()
    low = t.lower()
    if "not authorized" in low or "notauthorized" in low:
        return "This computer's policy didn't allow it (try once from the desktop: it may ask for your password)."
    if "no such file" in low:
        return f"There's no file at {path}."
    return t.splitlines()[-1] if t else "It couldn't be mounted."


# ── Linux: as root, without udisks ──

def _own_mount_dir(name):
    base = "/media/mountie" if _root() else os.path.join(os.path.expanduser("~"), "Mountie")
    safe = re.sub(r"[^\w.-]+", "_", name).strip("_") or "disk"
    mp = os.path.join(base, safe)
    os.makedirs(mp, exist_ok=True)
    return mp


def _partition_table(path):
    """[(number, start byte, length)] of a disk image's partitions, read by partx; [] if it has none."""
    code, out, _ = _run(["partx", "--show", "-g", "-b", "-o", "NR,START,SECTORS", path])
    if code:
        return []
    parts = []
    for line in out.splitlines():
        bits = line.split()
        if len(bits) == 3 and all(b.isdigit() for b in bits):
            parts.append((int(bits[0]), int(bits[1]) * 512, int(bits[2]) * 512))
    return parts


_named = {}                                                    # an offset loop device -> its partition's number


def _loop_image(path, ro):
    code, out, err = _run(["losetup", "-f", "--show", "-P"] + (["-r"] if ro else []) + [path])
    if code:
        raise DiskError(err.strip() or "losetup failed")
    loop = out.strip()
    loops = [loop]
    mounted = []
    stem = os.path.splitext(os.path.basename(path))[0]
    found = [(d, fs, m) for d, fs, m in _settle(loop) if fs]
    if not found:                                              # the kernel won't make partition devices for this loop
        for nr, start, length in _partition_table(path):       # (some do not): a loop device of its own for each
            c, o, _ = _run(["losetup", "-f", "--show", "-o", str(start), "--sizelimit", str(length)] + (["-r"] if ro else []) + [path])
            if c == 0:
                loops.append(o.strip())
                fs = next((f for _, f, _ in _children(o.strip()) if f), "")
                found.append((o.strip(), fs, []))
                _named[o.strip()] = str(nr)
    for dev, fs, mps in found:
        if not fs or fs == "swap":
            continue
        nr = _named.pop(dev, None) or (dev.rsplit("p", 1)[-1] if dev != loop else "")
        mp = _own_mount_dir(f"{stem}-{nr}" if nr else stem)
        c, _, e = _run(["mount"] + (["-o", "ro"] if ro else []) + [dev, mp])
        if c == 0:
            mounted.append(mp)
    if not mounted:
        for lp in loops:
            _run(["losetup", "-d", lp])
        raise DiskError(f"{os.path.basename(path)} has nothing on it that this computer can read.")

    def undo():
        for mp in mounted:
            if _run(["umount", mp])[0]:
                _run(["umount", "-l", mp])                     # busy: let go as soon as it's free
            try:
                os.rmdir(mp)
            except OSError:
                pass
        for lp in loops:
            _run(["losetup", "-d", lp])
    return Mounted({"path": path}, "loop", mounted, undo)


def _nbd_image(path, ro):
    if not os.path.exists("/dev/nbd0"):
        _run(["modprobe", "nbd", "max_part=16"])
    dev = next((f"/dev/nbd{i}" for i in range(16) if os.path.exists(f"/dev/nbd{i}")
                and open(f"/sys/block/nbd{i}/size").read().strip() == "0"), None)
    if not dev:
        raise DiskError("No free nbd device (modprobe nbd).")
    code, _, err = _run(["qemu-nbd", "-c", dev] + (["-r"] if ro else []) + [path])
    if code:
        raise DiskError(err.strip() or "qemu-nbd failed")
    mounted = []
    stem = os.path.splitext(os.path.basename(path))[0]
    for d, fs, mps in _settle(dev):
        if fs and fs != "swap":
            mp = _own_mount_dir(f"{stem}-{d.rsplit('p', 1)[-1]}")
            if _run(["mount"] + (["-o", "ro"] if ro else []) + [d, mp])[0] == 0:
                mounted.append(mp)

    def undo():
        for mp in mounted:
            _run(["umount", mp])
        _run(["qemu-nbd", "-d", dev])
    return Mounted({"path": path}, "qemu-nbd", mounted, undo)


def _fuseiso(path, name):
    mp = _own_mount_dir(name or os.path.splitext(os.path.basename(path))[0])
    code, _, err = _run(["fuseiso", path, mp])
    if code:
        raise DiskError(err.strip() or "fuseiso failed")

    def undo():
        _run(["fusermount", "-u", mp])
        try:
            os.rmdir(mp)
        except OSError:
            pass
    return Mounted({"path": path}, "fuseiso", [mp], undo)


def _guestmount(path, ro, name):
    mp = _own_mount_dir(name or os.path.splitext(os.path.basename(path))[0])
    code, _, err = _run(["guestmount", "-a", path, "-i", "--ro" if ro else "--rw", mp], timeout=180)
    if code:
        raise DiskError((err.strip().splitlines() or ["guestmount failed"])[-1])

    def undo():
        _run(["guestunmount", mp]) if shutil.which("guestunmount") else _run(["fusermount", "-u", mp])
        try:
            os.rmdir(mp)
        except OSError:
            pass
    return Mounted({"path": path}, "guestmount", [mp], undo)


def _linux_partition(dev, ro):
    rows = _children(dev)
    if rows and rows[0][2]:
        return Mounted({"path": dev}, "already", rows[0][2], lambda: None)     # mounted already: just show it
    if shutil.which("udisksctl") and not _root():
        code, out, err = _run(["udisksctl", "mount", "-b", dev] + (["-o", "ro"] if ro else []), timeout=120)
        m = re.search(r" at (.+?)\.?$", out.strip())
        if code or not m:
            raise DiskError(_plain(err or out))
        return Mounted({"path": dev}, "udisks", [m.group(1)],
                       lambda: _run(["udisksctl", "unmount", "--no-user-interaction", "-b", dev]))
    if _root():
        mp = _own_mount_dir(os.path.basename(dev))
        code, _, err = _run(["mount"] + (["-o", "ro"] if ro else []) + [dev, mp])
        if code:
            raise DiskError(err.strip())

        def undo():
            _run(["umount", mp])
            try:
                os.rmdir(mp)
            except OSError:
                pass
        return Mounted({"path": dev}, "mount", [mp], undo)
    raise DiskError("Mounting partitions needs udisks (sudo apt install udisks2).")


def unmount_partition(dev):
    """Unmount a partition mounted by anyone (the desktop, or before Mountie started)."""
    if WINDOWS:
        disk, part = dev.split(":")
        code, out, err = _ps(f"Get-Partition -DiskNumber {int(disk)} -PartitionNumber {int(part)} | "
                             "ForEach-Object { foreach ($p in $_.AccessPaths) { if ($p -match '^[A-Z]:\\\\$') "
                             "{ Remove-PartitionAccessPath -DiskNumber $_.DiskNumber -PartitionNumber $_.PartitionNumber "
                             "-AccessPath $p } } }", admin=True)
    elif MAC:
        code, out, err = _run(["diskutil", "unmount", dev])
    elif shutil.which("udisksctl") and not _root():
        code, out, err = _run(["udisksctl", "unmount", "-b", dev], timeout=60)
    else:
        code, out, err = _run(["umount", dev])
    if code:
        low = (err or out).lower()
        if "busy" in low or "target is busy" in low:
            raise DiskError("Something has it open (a file manager window, a terminal in it?). Close that and try again.")
        raise DiskError(_plain(err or out))


# ── Windows ──

def _is_admin():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _ps(script, admin=False, timeout=120):
    """Run PowerShell; with admin and not already admin, through a UAC prompt (the answer comes back in a file)."""
    import tempfile
    if not admin or _is_admin():
        return _run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                    timeout=timeout)
    with tempfile.TemporaryDirectory() as tmp:
        body, out = os.path.join(tmp, "do.ps1"), os.path.join(tmp, "out.txt")
        with open(body, "w", encoding="utf-8") as f:
            f.write(f"try {{ & {{ {script} }} *>&1 | Out-File -Encoding utf8 '{out}'; exit 0 }} "
                    f"catch {{ $_.Exception.Message | Out-File -Encoding utf8 '{out}'; exit 1 }}")
        launch = (f"$p = Start-Process powershell -Verb RunAs -Wait -PassThru -WindowStyle Hidden -ArgumentList "
                  f"'-NoProfile','-ExecutionPolicy','Bypass','-File','{body}'; exit $p.ExitCode")
        code, _, err = _run(["powershell", "-NoProfile", "-Command", launch], timeout=timeout)
        text = open(out, encoding="utf-8-sig").read() if os.path.exists(out) else ""
        if code and not text:
            return code, "", "Windows didn't give permission (the admin question was declined)."
        return code, text, text if code else ""


def _win_image(path, ro):
    p = path.replace("'", "''")
    kind = os.path.splitext(path)[1].lower()
    script = (f"$i = Mount-DiskImage -ImagePath '{p}' -Access {'ReadOnly' if ro else 'ReadWrite'} -PassThru; Start-Sleep -Milliseconds 800; "
              f"$l = @(($i | Get-Volume -ErrorAction SilentlyContinue).DriveLetter) + "
              f"@((Get-DiskImage -ImagePath '{p}' | Get-Disk -ErrorAction SilentlyContinue | Get-Partition -ErrorAction SilentlyContinue).DriveLetter); "
              f"($l | Where-Object {{ $_ }} | ForEach-Object {{ \"$($_):\" }}) -join ','")
    code, out, err = _ps(script, admin=kind in (".vhd", ".vhdx"))
    letters = [x for x in out.strip().split(",") if re.fullmatch(r"[A-Z]:", x.strip())]
    if code or not letters:
        raise DiskError((err or out).strip().splitlines()[-1] if (err or out).strip() else "Windows couldn't mount it.")
    return Mounted({"path": path}, "Windows", letters,
                   lambda: _ps(f"Dismount-DiskImage -ImagePath '{p}'", admin=kind in (".vhd", ".vhdx")))


def _win_partition(item):
    disk, part = str(item["path"]).split(":")
    code, out, err = _ps(f"Add-PartitionAccessPath -DiskNumber {int(disk)} -PartitionNumber {int(part)} -AssignDriveLetter; "
                         f"(Get-Partition -DiskNumber {int(disk)} -PartitionNumber {int(part)}).DriveLetter", admin=True)
    letter = (out.strip().splitlines() or [""])[-1].strip()
    if code or not re.fullmatch(r"[A-Z]", letter):
        raise DiskError((err or out).strip() or "Windows couldn't give it a drive letter.")
    return Mounted(item, "Windows", [letter + ":"], lambda: unmount_partition(item["path"]))


# ── macOS ──

def _mac_image(path, ro):
    import plistlib
    code, out, err = _run(["hdiutil", "attach", "-plist"] + (["-readonly"] if ro else []) + [path])
    if code:
        raise DiskError(err.strip() or "hdiutil couldn't attach it")
    ents = plistlib.loads(out.encode()).get("system-entities", [])
    places = [e["mount-point"] for e in ents if e.get("mount-point")]
    dev = next((e["dev-entry"] for e in ents if e.get("dev-entry")), "")
    return Mounted({"path": path}, "hdiutil", places, lambda: _run(["hdiutil", "detach", dev]))


def _mac_partition(dev):
    code, out, err = _run(["diskutil", "mount", dev])
    if code:
        raise DiskError(err.strip() or out.strip())
    mp = next((p["mounted"] for p in _mac_partitions() if p["path"] == dev), "")
    return Mounted({"path": dev}, "diskutil", [mp] if mp else [], lambda: _run(["diskutil", "unmount", dev]))


# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
#  The ones mounted from here
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════

class Disks:
    """What has been mounted from here, by name; on_change(name, state, detail) as each changes (connecting is
    "mounting" here; mounted's detail is where, comma-separated)."""

    def __init__(self, on_change=None):
        self.running, self.status = {}, {}
        self.on_change = on_change
        self._lock = threading.Lock()

    def _say(self, name, state, detail=""):
        self.status[name] = {"state": state, "detail": detail}
        if self.on_change:
            try:
                self.on_change(name, state, detail)
            except Exception:
                pass

    def up(self, item):
        name = item.get("name") or os.path.basename(str(item.get("path")))
        self._say(name, "mounting")

        def go():
            try:
                m = mount(item)
                with self._lock:
                    self.running[name] = m
                self._say(name, "mounted", ", ".join(m.places) + f" ({m.how})")
            except DiskError as e:
                self._say(name, "error", str(e))
            except Exception as e:
                self._say(name, "error", str(e))
        threading.Thread(target=go, daemon=True).start()

    def down(self, name, item=None):
        with self._lock:
            m = self.running.pop(name, None)
        try:
            if m is not None:
                m.stop()
            elif item and (item.get("kind") == "part" or kind_of(item.get("path", "")) == "part"):
                unmount_partition(item["path"])               # mounted by someone else: unmount it all the same
            self._say(name, "off")
        except DiskError as e:
            self._say(name, "error", str(e))

    def down_all(self, wait=10.0):
        import time
        names = list(self.running)
        threads = [threading.Thread(target=self.down, args=(n,), daemon=True) for n in names]
        for t in threads:
            t.start()
        end = time.time() + wait
        for t in threads:
            t.join(max(0.0, end - time.time()))
