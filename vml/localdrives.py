"""
Drives that don't need a server: a folder on this computer seen through an ignore list (~/Downloads as
"DownloadFiles", showing only what you want to see), and a RAM disk.

Both are remotes in sshdrive's sense (BaseRemote), so anything that can show a remote as a drive shows these too:
WinFsp on Windows, and on Linux a small FUSE filesystem (FuseDrive) that runs in a process of its own, so a stuck
read can never freeze the app and the app's Ctrl-C stays the app's.

    python -m vml.localdrives serve SPEC.json MOUNTPOINT      (what FuseDrive starts; SPEC is a drive's settings)
"""
import errno
import io
import json
import os
import posixpath
import stat as _stat
import subprocess
import sys
import threading
import time
import zipfile

from . import ignore
from .sshdrive import BaseRemote, Entry, LocalRemote, RemoteError, _bookmark, _clean

MB = 1 << 20


# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
#  A folder through an ignore list
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════

class FilteredRemote(LocalRemote):
    """A local folder, less whatever its ignore list leaves out (or, with show_only, only what the list names).
    What's left out isn't there at all: it can't be listed, opened, or made."""

    def __init__(self, root, text="", show_only=False, readonly=False):
        super().__init__(root)
        if not os.path.isdir(self.root):
            raise RemoteError("notfound", f"There's no folder {root}")
        self.pats = ignore.patterns(text)
        self.show_only = bool(show_only)
        self.readonly = bool(readonly)

    def _out(self, rel, is_dir):
        if not self.pats:
            return False
        h = ignore.hidden(self.pats, rel, is_dir)
        return (not h) if self.show_only else h

    def _gone(self, rel, is_dir=None):
        """Is rel, or a folder it's in, left out? (is_dir None: look.)"""
        parts = _clean(rel).strip("/").split("/")
        if parts == [""]:
            return False
        for i in range(1, len(parts)):
            if self._out("/".join(parts[:i]), True):
                return True
        if is_dir is None:
            is_dir = os.path.isdir(self._p(rel))
        return self._out("/".join(parts), is_dir)

    def _check(self, rel, is_dir=None, write=False):
        if write and self.readonly:
            raise RemoteError("denied", "This drive is read-only")
        if self._gone(rel, is_dir):
            raise RemoteError("notfound" if not write else "denied", f"{rel} is left out of this drive")

    def stat(self, rel):
        e = super().stat(rel)
        self._check(rel, e.is_dir)
        return e

    def listdir(self, rel):
        self._check(rel, True)
        base = _clean(rel).strip("/")
        return [e for e in super().listdir(rel) if not self._out(f"{base}/{e.name}".strip("/"), e.is_dir)]

    def open(self, rel, mode):
        self._check(rel, False, write=any(c in mode for c in "wa+"))
        return super().open(rel, mode)

    def mkdir(self, rel):
        self._check(rel, True, write=True)
        super().mkdir(rel)

    def remove(self, rel):
        self._check(rel, False, write=True)
        super().remove(rel)

    def rmdir(self, rel):
        self._check(rel, True, write=True)
        super().rmdir(rel)

    def rename(self, old, new):
        self._check(old, None, write=True)
        self._check(new, os.path.isdir(self._p(old)), write=True)
        super().rename(old, new)

    def truncate(self, rel, size):
        self._check(rel, False, write=True)
        super().truncate(rel, size)

    def set_times(self, rel, atime, mtime):
        self._check(rel, None, write=True)
        super().set_times(rel, atime, mtime)


# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
#  A RAM disk
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════

class _Node:
    __slots__ = ("is_dir", "data", "kids", "mtime", "atime", "mode")

    def __init__(self, is_dir, mode=None):
        now = time.time()
        self.is_dir = is_dir
        self.data = None if is_dir else bytearray()
        self.kids = {} if is_dir else None
        self.mtime = self.atime = now
        self.mode = mode or ((_stat.S_IFDIR | 0o755) if is_dir else (_stat.S_IFREG | 0o644))


class _MemFile:
    """An open file on the RAM disk."""

    def __init__(self, remote, node, rel, mode):
        self.r, self.node, self.rel = remote, node, rel
        self.readable = "r" in mode or "+" in mode
        self.writable = any(c in mode for c in "wa+")
        self.pos = len(node.data) if "a" in mode else 0
        self.closed = False

    def read(self, n=-1):
        if not self.readable:
            raise io.UnsupportedOperation("not readable")
        with self.r.lock:
            d = self.node.data
            end = len(d) if n is None or n < 0 else min(len(d), self.pos + n)
            out = bytes(d[self.pos:end])
            self.pos = max(self.pos, end)
            self.node.atime = time.time()
            return out

    def write(self, b):
        if not self.writable:
            raise io.UnsupportedOperation("not writable")
        b = bytes(b)
        with self.r.lock:
            d = self.node.data
            grow = max(0, self.pos + len(b) - len(d))
            self.r._room(grow)
            if self.pos > len(d):
                d.extend(b"\0" * (self.pos - len(d)))
            d[self.pos:self.pos + len(b)] = b
            self.r.used += grow
            self.pos += len(b)
            self.node.mtime = time.time()
        self.r.cache.forget(self.rel)
        return len(b)

    def seek(self, off, whence=0):
        with self.r.lock:
            self.pos = max(0, off if whence == 0 else self.pos + off if whence == 1 else len(self.node.data) + off)
            return self.pos

    def tell(self):
        return self.pos

    def truncate(self, size=None):
        self.r._resize(self.node, self.pos if size is None else size)
        self.r.cache.forget(self.rel)
        return size

    def flush(self): pass

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class MemoryRemote(BaseRemote):
    """Files kept in this computer's memory, up to `limit` bytes. Gone when the drive stops, unless it's told
    where to keep them (keep=a .zip file): then they're saved there on the way down and back on the way up."""

    def __init__(self, limit=512 * MB, keep=""):
        super().__init__()
        self.limit = max(1 * MB, int(limit))
        self.keep = keep or ""
        self.used = 0
        self.lock = threading.RLock()
        self.top = _Node(True)
        if self.keep and os.path.exists(self.keep):
            self.load(self.keep)

    def _find(self, rel):
        node = self.top
        for p in _clean(rel).strip("/").split("/"):
            if not p:
                continue
            if not node.is_dir:
                raise RemoteError("notdir", rel)
            node = node.kids.get(p)
            if node is None:
                raise RemoteError("notfound", f"No {rel}")
        return node

    def _parent(self, rel):
        rel = _clean(rel)
        if rel == "/":
            raise RemoteError("exists", "/")
        parent = self._find(posixpath.dirname(rel))
        if not parent.is_dir:
            raise RemoteError("notdir", rel)
        return parent, posixpath.basename(rel)

    def _room(self, grow):
        if grow > 0 and self.used + grow > self.limit:
            raise RemoteError("full", f"The RAM disk is full ({self.limit // MB} MB)")

    def _resize(self, node, size):
        with self.lock:
            if node.is_dir:
                raise RemoteError("isdir", "That's a folder")
            d, size = node.data, max(0, int(size))
            grow = size - len(d)
            self._room(grow)
            if grow > 0:
                d.extend(b"\0" * grow)
            else:
                del d[size:]
            self.used += grow
            node.mtime = time.time()

    @staticmethod
    def _entry(name, n):
        return Entry(name, n.is_dir, 0 if n.is_dir else len(n.data), n.mtime, n.atime, n.mode)

    def stat(self, rel):
        with self.lock:
            return self._entry(posixpath.basename(_clean(rel)) or "/", self._find(rel))

    def listdir(self, rel):
        with self.lock:
            n = self._find(rel)
            if not n.is_dir:
                raise RemoteError("notdir", rel)
            return [self._entry(k, v) for k, v in n.kids.items()]

    def open(self, rel, mode):
        rel = _clean(rel)
        with self.lock:
            parent, name = self._parent(rel)
            node = parent.kids.get(name)
            if node is None:
                if mode.startswith("r"):
                    raise RemoteError("notfound", f"No {rel}")
                node = parent.kids[name] = _Node(False)
                parent.mtime = time.time()
            elif node.is_dir:
                raise RemoteError("isdir", rel)
            elif "x" in mode:
                raise RemoteError("exists", rel)
            if "w" in mode:
                self._resize(node, 0)
        self.cache.forget(rel)
        return _MemFile(self, node, rel, mode)

    def mkdir(self, rel):
        with self.lock:
            parent, name = self._parent(rel)
            if name in parent.kids:
                raise RemoteError("exists", rel)
            parent.kids[name] = _Node(True)
            parent.mtime = time.time()
        self.cache.forget(_clean(rel))

    def _size(self, n):
        return sum(self._size(k) for k in n.kids.values()) if n.is_dir else len(n.data)

    def remove(self, rel):
        with self.lock:
            parent, name = self._parent(rel)
            n = parent.kids.get(name)
            if n is None:
                raise RemoteError("notfound", rel)
            if n.is_dir:
                raise RemoteError("isdir", rel)
            del parent.kids[name]
            self.used -= len(n.data)
            parent.mtime = time.time()
        self.cache.forget(_clean(rel))

    def rmdir(self, rel):
        with self.lock:
            parent, name = self._parent(rel)
            n = parent.kids.get(name)
            if n is None:
                raise RemoteError("notfound", rel)
            if not n.is_dir:
                raise RemoteError("notdir", rel)
            if n.kids:
                raise RemoteError("notempty", rel)
            del parent.kids[name]
            parent.mtime = time.time()
        self.cache.forget(_clean(rel))

    def rename(self, old, new):
        old, new = _clean(old), _clean(new)
        with self.lock:
            if (new + "/").startswith(old + "/"):
                if new == old:
                    return
                raise RemoteError("denied", "A folder can't go inside itself")
            op, oname = self._parent(old)
            n = op.kids.get(oname)
            if n is None:
                raise RemoteError("notfound", old)
            np_, nname = self._parent(new)
            there = np_.kids.get(nname)
            if there is not None:
                if there.is_dir and (not n.is_dir or there.kids):
                    raise RemoteError("notempty" if there.kids else "isdir", new)
                if not there.is_dir and n.is_dir:
                    raise RemoteError("notdir", new)
                self.used -= self._size(there)
            del op.kids[oname]
            np_.kids[nname] = n
            op.mtime = np_.mtime = time.time()
        self.cache.forget(old, new)

    def truncate(self, rel, size):
        with self.lock:
            self._resize(self._find(rel), size)
        self.cache.forget(_clean(rel))

    def set_times(self, rel, atime, mtime):
        with self.lock:
            n = self._find(rel)
            n.atime, n.mtime = atime, mtime
        self.cache.forget(_clean(rel))

    def chmod(self, rel, mode):
        with self.lock:
            n = self._find(rel)
            n.mode = _stat.S_IFMT(n.mode) | (mode & 0o7777)

    def space(self):
        return (self.limit, max(0, self.limit - self.used))

    # keeping the contents between runs
    def save(self, path=None):
        path = path or self.keep
        if not path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".saving"
        with self.lock, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
            def walk(node, at):
                for name, n in node.kids.items():
                    rel = f"{at}{name}"
                    zi = zipfile.ZipInfo(rel + ("/" if n.is_dir else ""), time.localtime(max(n.mtime, 315532800))[:6])
                    zi.external_attr = (n.mode & 0xFFFF) << 16
                    zi.compress_type = zipfile.ZIP_DEFLATED
                    z.writestr(zi, b"" if n.is_dir else bytes(n.data))
                    if n.is_dir:
                        walk(n, rel + "/")
            walk(self.top, "")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    def load(self, path):
        with self.lock, zipfile.ZipFile(path) as z:
            for zi in z.infolist():
                rel = "/" + zi.filename.strip("/")
                parts, node = rel.strip("/").split("/"), self.top
                for p in parts[:-1]:
                    node = node.kids.setdefault(p, _Node(True))
                mode = (zi.external_attr >> 16) or None
                when = time.mktime(zi.date_time + (0, 0, -1))
                if zi.is_dir():
                    n = node.kids.setdefault(parts[-1], _Node(True, mode))
                else:
                    data = z.read(zi)
                    if self.used + len(data) > self.limit:
                        raise RemoteError("full", f"What was kept ({path}) doesn't fit in {self.limit // MB} MB")
                    n = node.kids[parts[-1]] = _Node(False, mode)
                    n.data[:] = data
                    self.used += len(data)
                n.mtime = n.atime = when

    def close(self):
        self.save()


def remote_for(drive):
    """The remote behind a folder or RAM drive's settings."""
    kind = drive.get("kind")
    if kind == "folder":
        return FilteredRemote(os.path.expanduser(drive.get("path") or ""), drive.get("hide") or "",
                              show_only=drive.get("showonly"), readonly=drive.get("readonly"))
    if kind == "ram":
        return MemoryRemote(int(float(drive.get("size") or 512) * MB), os.path.expanduser(drive.get("keep") or ""))
    raise ValueError(f"Not a local drive: {kind!r}")


# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
#  Linux: a remote as a FUSE filesystem
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════

ERRNO = {"notfound": errno.ENOENT, "exists": errno.EEXIST, "notempty": errno.ENOTEMPTY, "notdir": errno.ENOTDIR,
         "isdir": errno.EISDIR, "denied": errno.EACCES, "full": errno.ENOSPC, "offline": errno.EIO, "io": errno.EIO}


def operations(remote):
    """mfusepy Operations answering from `remote`."""
    import mfusepy

    def fail(e):
        if isinstance(e, mfusepy.FuseOSError):
            return e
        if isinstance(e, RemoteError):
            return mfusepy.FuseOSError(ERRNO.get(e.kind, errno.EIO))
        if isinstance(e, OSError) and e.errno:
            return mfusepy.FuseOSError(e.errno)
        return mfusepy.FuseOSError(errno.EIO)

    def guard(fn):
        def run(self, *a):
            try:
                return fn(self, *a)
            except Exception as e:
                raise fail(e) from None
        run.__name__ = fn.__name__
        return run

    uid, gid = os.getuid(), os.getgid()

    class Ops(mfusepy.Operations):
        use_ns = True

        def __init__(self):
            self._open, self._n, self._lk = {}, 1, threading.Lock()

        def _fh(self, f):
            with self._lk:
                fh, self._n = self._n, self._n + 1
                self._open[fh] = (f, threading.Lock())
                return fh

        @guard
        def getattr(self, path, fh=None):
            e = remote.cstat(path)
            if e.is_dir:
                mode = _stat.S_IFDIR | (_stat.S_IMODE(e.mode) or 0o755)
            else:
                mode = _stat.S_IFREG | (_stat.S_IMODE(e.mode) or 0o644)
            if remote.readonly:
                mode &= ~0o222
            ns = lambda t: int((t or 0) * 1e9)
            return dict(st_mode=mode, st_nlink=2 if e.is_dir else 1, st_size=e.size, st_uid=uid, st_gid=gid,
                        st_mtime=ns(e.mtime), st_atime=ns(e.atime or e.mtime), st_ctime=ns(e.mtime),
                        st_blocks=(e.size + 511) // 512)

        @guard
        def readdir(self, path, fh):
            return [".", ".."] + [e.name for e in remote.clistdir(path)]

        @guard
        def open(self, path, flags):
            acc = flags & os.O_ACCMODE
            mode = "rb" if acc == os.O_RDONLY else "r+b"
            if flags & os.O_TRUNC and acc != os.O_RDONLY:
                mode = "w+b"
            return self._fh(remote.open(path, mode))

        @guard
        def create(self, path, mode, fi=None):
            return self._fh(remote.open(path, "w+b"))

        @guard
        def read(self, path, size, offset, fh):
            f, lk = self._open[fh]
            with lk:
                f.seek(offset)
                return f.read(size)

        @guard
        def write(self, path, data, offset, fh):
            f, lk = self._open[fh]
            with lk:
                f.seek(offset)
                return f.write(data) or len(data)

        @guard
        def truncate(self, path, length, fh=None):
            if fh in self._open:
                f, lk = self._open[fh]
                with lk:
                    f.truncate(length)
                remote.cache.forget(_clean(path))
            else:
                remote.truncate(path, length)
            return 0

        @guard
        def flush(self, path, fh):
            if fh in self._open:
                f, lk = self._open[fh]
                with lk:
                    f.flush()
            return 0

        def fsync(self, path, datasync, fh):
            return self.flush(path, fh)

        @guard
        def release(self, path, fh):
            with self._lk:
                f, _ = self._open.pop(fh, (None, None))
            if f is not None:
                f.close()
                remote.cache.forget(_clean(path))
            return 0

        @guard
        def mkdir(self, path, mode):
            remote.mkdir(path)
            return 0

        @guard
        def rmdir(self, path):
            remote.rmdir(path)
            return 0

        @guard
        def unlink(self, path):
            remote.remove(path)
            return 0

        @guard
        def rename(self, old, new):
            remote.rename(old, new)
            return 0

        @guard
        def utimens(self, path, times=None):
            now = time.time()
            a, m = (times[0] / 1e9, times[1] / 1e9) if times else (now, now)
            remote.set_times(path, a, m)
            return 0

        @guard
        def chmod(self, path, mode):
            if hasattr(remote, "chmod"):
                remote.chmod(path, mode)
            return 0

        def chown(self, path, uid_, gid_):
            return 0

        @guard
        def statfs(self, path):
            total, free = remote.space()
            bs = 4096
            return dict(f_bsize=bs, f_frsize=bs, f_blocks=total // bs, f_bfree=free // bs, f_bavail=free // bs,
                        f_files=1 << 20, f_ffree=1 << 19, f_namemax=255)

        def destroy(self, path):
            try:
                remote.close()
            except Exception as e:
                print(f"Couldn't keep the drive's contents: {e}", file=sys.stderr, flush=True)

    return Ops()


def serve(spec_path, mountpoint):
    """Run one drive until it's unmounted (the child process FuseDrive starts)."""
    import mfusepy
    drive = json.load(open(spec_path, encoding="utf-8"))
    try:
        os.remove(spec_path)
    except OSError:
        pass
    remote = remote_for(drive)
    name = "".join(c for c in (drive.get("name") or "mountie") if c.isalnum() or c in "-_") or "mountie"
    opts = dict(foreground=True, fsname=f"mountie:{name}", subtype="mountie", default_permissions=True)
    if remote.readonly:
        opts["ro"] = True
    mfusepy.FUSE(operations(remote), mountpoint, **opts)


def _fuse_problem(text):
    t = (text or "").strip()
    low = t.lower()
    if "no module named 'mfusepy'" in low:
        return "Mountie needs the mfusepy module for this (pip install mfusepy)."
    if "fuse" in low and ("not found" in low or "/dev/fuse" in low or "unable to load" in low or "oserror" in low):
        return "This computer can't mount folders (FUSE isn't available)."
    if "not empty" in low or "nonempty" in low:
        return f"The folder it goes in isn't empty: {t.splitlines()[-1]}"
    return t.splitlines()[-1] if t else "The drive couldn't be mounted."


class FuseDrive:
    """A folder or RAM drive in the file manager (Linux): a child process serving it through FUSE."""

    def __init__(self, drive, mountpoint):
        self.drive, self.mountpoint, self.proc = dict(drive), mountpoint, None
        self.name = drive.get("name") or posixpath.basename(mountpoint)

    def start(self, wait=8):
        os.makedirs(self.mountpoint, exist_ok=True)
        if os.path.ismount(self.mountpoint):
            subprocess.run(["fusermount3", "-uz", self.mountpoint], capture_output=True)
        if os.listdir(self.mountpoint):
            raise RemoteError("exists", f"The folder it goes in isn't empty: {self.mountpoint}")
        remote_for(self.drive)                      # check it can be made here, where the message can be shown
        import tempfile
        fd, spec = tempfile.mkstemp(prefix="mountie-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.drive, f)
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = dict(os.environ, PYTHONPATH=here + os.pathsep + os.environ.get("PYTHONPATH", ""))
        self.proc = subprocess.Popen([sys.executable, "-m", "vml.localdrives", "serve", spec, self.mountpoint],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env,
                                     start_new_session=True)
        end = time.monotonic() + wait
        while time.monotonic() < end:
            if os.path.ismount(self.mountpoint):
                threading.Thread(target=self._drain, daemon=True).start()
                _bookmark(self.mountpoint, self.name, True)
                return self
            if self.proc.poll() is not None:
                raise RemoteError("io", _fuse_problem(self.proc.stderr.read().decode(errors="replace")))
            time.sleep(0.05)
        self.proc.kill()
        raise RemoteError("io", "The drive didn't appear in time.")

    def _drain(self):
        for line in self.proc.stderr:
            sys.stderr.write(line.decode(errors="replace"))

    @property
    def alive(self):
        return self.proc is not None and self.proc.poll() is None and os.path.ismount(self.mountpoint)

    def stop(self, wait=15):
        """Unmount (gently; if something has it open, lazily). The child saves a kept RAM disk on the way out."""
        _bookmark(self.mountpoint, self.name, False)
        if os.path.ismount(self.mountpoint):
            r = subprocess.run(["fusermount3", "-u", self.mountpoint], capture_output=True)
            if r.returncode:
                subprocess.run(["fusermount3", "-uz", self.mountpoint], capture_output=True)
        if self.proc:
            try:
                self.proc.wait(wait)
            except subprocess.TimeoutExpired:
                self.proc.terminate()
                try:
                    self.proc.wait(3)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
        try:
            os.rmdir(self.mountpoint)
        except OSError:
            pass


def mountpoint_for(name):
    base = os.path.join(os.path.expanduser("~"), "Mountie")
    safe = "".join(c for c in name if c not in '/\\:*?"<>|').strip() or "Drive"
    return os.path.join(base, safe)


class _WinDrive:
    """Windows: the remote as a drive letter through WinFsp (or the built-in WebDAV client without it)."""

    def __init__(self, drive, name):
        from .sshdrive import WebDavDrive, WinFspDrive, free_letter, winfsp_available
        self.name, self.remote = name, remote_for(drive)
        mp = drive.get("letter") or free_letter()
        try:
            self.drv = WinFspDrive(self.remote, mp, name) if winfsp_available() else WebDavDrive(self.remote, mp, name)
        except Exception:
            self.drv = WebDavDrive(self.remote, mp, name)
        self.mountpoint = getattr(self.drv, "mountpoint", mp)

    @property
    def alive(self):
        return True

    def stop(self, wait=15):
        try:
            self.drv.stop()
        finally:
            self.remote.close()


def start(drive):
    """Mount a folder or RAM drive the way this computer does it. Returns something with .stop() and .mountpoint."""
    name = drive.get("name") or ("RamDisk" if drive.get("kind") == "ram" else "Folder")
    if sys.platform.startswith("win"):
        return _WinDrive(drive, name)
    return FuseDrive(dict(drive, name=name), drive.get("mountpoint") or mountpoint_for(name)).start()


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "serve":
        serve(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
