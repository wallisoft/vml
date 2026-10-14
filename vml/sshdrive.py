"""
SSH drives: a folder on any SSH server, shown as a drive on this computer.

    Windows   a drive letter. Through WinFsp when it's installed (fast, no size limits: the same driver SSHFS-Win uses),
              otherwise through Windows' own WebDAV client (nothing to install; slower, and Windows caps files at
              50 MB until FileSizeLimitInBytes is raised).
    Linux     a folder, through the system's sshfs when it's there, otherwise WebDAV on 127.0.0.1 for the file manager.
    macOS     sshfs (macFUSE) when it's there.

Nothing here needs the engine: `python -m vml.sshdrive mount ...` runs one drive from a terminal, and the engine's
SshMount command runs the same code. A drive is a plain dict (see DRIVE_DEFAULTS), kept by the app in its settings.

Sign-in is a password, a key file (with its passphrase, if it has one), or the SSH agent. The server's own key is
remembered the first time (its fingerprint goes back in the drive's "hostkey") and a changed key is refused, as
ssh itself does.
"""
import base64
import errno
import hashlib
import io
import os
import posixpath
import shutil
import socket
import stat as _stat
import subprocess
import sys
import threading
import time

DRIVE_DEFAULTS = {
    "name": "",            # shown in the app and as the volume label
    "host": "",
    "port": 22,
    "user": "",
    "auth": "agent",       # "password", "key" or "agent"
    "password": "",
    "key": "",             # path to a private key file
    "keytext": "",         # or the key itself (a phone has no key files; also fine on a computer)
    "passphrase": "",
    "remote": "",          # folder on the server ("" is the user's home)
    "mount": "",           # Windows: a drive letter like "S:"; elsewhere a folder
    "automount": True,
    "readonly": False,
    "hostkey": "",         # "ssh-ed25519 SHA256:..." once known
    "actas": "",           # "" (yourself), or "root", "www-data"...: the drive works as that user, through sudo
    "method": "auto",      # "auto", "winfsp", "webdav" or "sshfs"
}

WINDOWS = sys.platform.startswith("win")
CACHE_SECONDS = 2.0


class RemoteError(Exception):
    """kind: notfound, exists, notempty, notdir, isdir, denied, hostkey, auth, offline, io"""

    def __init__(self, kind, message=""):
        super().__init__(message or kind)
        self.kind = kind


class Entry:
    __slots__ = ("name", "is_dir", "size", "mtime", "atime", "mode")

    def __init__(self, name, is_dir, size=0, mtime=0.0, atime=0.0, mode=0):
        self.name, self.is_dir, self.size, self.mtime, self.atime, self.mode = name, is_dir, size, mtime, atime, mode

    def __repr__(self):
        return f"Entry({self.name!r}, {'dir' if self.is_dir else self.size})"


def _from_attr(name, a):
    mode = a.st_mode or 0
    return Entry(name, _stat.S_ISDIR(mode), a.st_size or 0, float(a.st_mtime or 0), float(a.st_atime or a.st_mtime or 0), mode)


def _kind(exc):
    """What a remote failure means, from errno (paramiko maps SFTP status codes onto errno)."""
    if isinstance(exc, RemoteError):
        return exc.kind
    e = getattr(exc, "errno", None)
    if e == errno.ENOENT:
        return "notfound"
    if e == errno.EEXIST:
        return "exists"
    if e in (errno.EACCES, errno.EPERM):
        return "denied"
    if e == errno.ENOTEMPTY:
        return "notempty"
    if e == errno.ENOTDIR:
        return "notdir"
    if e == errno.EISDIR:
        return "isdir"
    return "io"


def _clean(rel):
    """A path inside the drive, always "/..." with forward slashes, never escaping its root."""
    rel = str(rel or "/").replace("\\", "/")
    parts = []
    for p in rel.split("/"):
        if p in ("", "."):
            continue
        if p == "..":
            if parts:
                parts.pop()
            continue
        parts.append(p)
    return "/" + "/".join(parts)


class _Cache:
    """Remembers stat and listing answers for a couple of seconds: Explorer asks the same question many times over."""

    def __init__(self):
        self._lock = threading.Lock()
        self._stat, self._dirs = {}, {}

    def get_stat(self, rel):
        with self._lock:
            v = self._stat.get(rel)
            return v[1] if v and time.monotonic() - v[0] < CACHE_SECONDS else None

    def put_stat(self, rel, entry):
        with self._lock:
            self._stat[rel] = (time.monotonic(), entry)

    def get_dir(self, rel):
        with self._lock:
            v = self._dirs.get(rel)
            return v[1] if v and time.monotonic() - v[0] < CACHE_SECONDS else None

    def put_dir(self, rel, entries):
        with self._lock:
            now = time.monotonic()
            self._dirs[rel] = (now, entries)
            for e in entries:
                self._stat[posixpath.join(rel, e.name)] = (now, e)

    def forget(self, *rels):
        with self._lock:
            for rel in rels:
                self._stat.pop(rel, None)
                self._dirs.pop(rel, None)
                self._dirs.pop(posixpath.dirname(rel) or "/", None)


class BaseRemote:
    """What the drive backends need from a remote. SftpRemote is the real one; LocalRemote stands in for tests."""

    readonly = False

    def __init__(self):
        self.cache = _Cache()

    # each takes a drive path ("/a/b")
    def stat(self, rel): raise NotImplementedError
    def listdir(self, rel): raise NotImplementedError
    def open(self, rel, mode): raise NotImplementedError      # a file object: read/write/seek/truncate/flush/close
    def mkdir(self, rel): raise NotImplementedError
    def remove(self, rel): raise NotImplementedError
    def rmdir(self, rel): raise NotImplementedError
    def rename(self, old, new): raise NotImplementedError     # replaces new if it's there
    def truncate(self, rel, size): raise NotImplementedError
    def set_times(self, rel, atime, mtime): raise NotImplementedError

    def space(self):
        return (1 << 40, 1 << 39)    # (total, free) when the server won't say

    def close(self): pass

    # cached versions the backends use
    def cstat(self, rel):
        rel = _clean(rel)
        e = self.cache.get_stat(rel)
        if e is None:
            e = self.stat(rel)
            self.cache.put_stat(rel, e)
        return e

    def clistdir(self, rel):
        rel = _clean(rel)
        es = self.cache.get_dir(rel)
        if es is None:
            es = sorted(self.listdir(rel), key=lambda e: e.name.lower())
            self.cache.put_dir(rel, es)
        return es

    def exists(self, rel):
        try:
            self.cstat(rel)
            return True
        except RemoteError as e:
            if e.kind == "notfound":
                return False
            raise


class LocalRemote(BaseRemote):
    """A local folder behaving like a remote: lets the drive backends be tested without a server."""

    def __init__(self, root):
        super().__init__()
        self.root = os.path.abspath(root)

    def _p(self, rel):
        return os.path.join(self.root, _clean(rel).lstrip("/"))

    def _wrap(self, fn, *a):
        try:
            return fn(*a)
        except OSError as e:
            raise RemoteError(_kind(e), str(e))

    def stat(self, rel):
        st = self._wrap(os.stat, self._p(rel))
        return Entry(posixpath.basename(_clean(rel)) or "/", _stat.S_ISDIR(st.st_mode), st.st_size, st.st_mtime, st.st_atime, st.st_mode)

    def listdir(self, rel):
        base = self._p(rel)
        out = []
        for n in self._wrap(os.listdir, base):
            try:
                st = os.stat(os.path.join(base, n))
            except OSError:
                continue
            out.append(Entry(n, _stat.S_ISDIR(st.st_mode), st.st_size, st.st_mtime, st.st_atime, st.st_mode))
        return out

    def open(self, rel, mode):
        if "w" in mode or "a" in mode:
            self.cache.forget(_clean(rel))
        return self._wrap(open, self._p(rel), mode)

    def mkdir(self, rel):
        self.cache.forget(_clean(rel))
        self._wrap(os.mkdir, self._p(rel))

    def remove(self, rel):
        self.cache.forget(_clean(rel))
        self._wrap(os.remove, self._p(rel))

    def rmdir(self, rel):
        self.cache.forget(_clean(rel))
        self._wrap(os.rmdir, self._p(rel))

    def rename(self, old, new):
        self.cache.forget(_clean(old), _clean(new))
        self._wrap(os.replace, self._p(old), self._p(new))

    def truncate(self, rel, size):
        self.cache.forget(_clean(rel))
        self._wrap(os.truncate, self._p(rel), size)

    def set_times(self, rel, atime, mtime):
        self.cache.forget(_clean(rel))
        self._wrap(os.utime, self._p(rel), (atime, mtime))

    def space(self):
        u = shutil.disk_usage(self.root)
        return (u.total, u.free)


def fingerprint(key):
    """"ssh-ed25519 SHA256:..." the way ssh shows it."""
    digest = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
    return f"{key.get_name()} SHA256:{digest}"


class SftpRemote(BaseRemote):
    """A folder on an SSH server, over SFTP. Reconnects by itself when the line drops."""

    def __init__(self, drive, on_hostkey=None):
        super().__init__()
        self.d = dict(DRIVE_DEFAULTS, **drive)
        self.readonly = bool(self.d.get("readonly"))
        self.on_hostkey = on_hostkey          # called with the fingerprint the first time a server is seen
        self._lock = threading.RLock()
        self._ssh = self._sftp = None
        self._root = None
        self.connect()

    # ── connection ──
    def connect(self):
        import paramiko
        with self._lock:
            self.close()
            d = self.d
            ssh = paramiko.SSHClient()
            seen = {}

            class Pin(paramiko.MissingHostKeyPolicy):
                def missing_host_key(self, client, hostname, key):
                    seen["fp"] = fingerprint(key)

            ssh.set_missing_host_key_policy(Pin())
            kw = dict(hostname=d["host"], port=int(d["port"] or 22), username=d["user"] or None, timeout=15,
                      banner_timeout=15, auth_timeout=20, allow_agent=False, look_for_keys=False)
            auth = d.get("auth") or "agent"
            if auth == "password":
                kw["password"] = d["password"]
            elif auth == "key":
                kw["pkey"] = self._load_key(d["key"], d.get("passphrase") or None, d.get("keytext") or "")
            else:
                kw["allow_agent"], kw["look_for_keys"] = True, True
            try:
                ssh.connect(**kw)
            except paramiko.AuthenticationException as e:
                raise RemoteError("auth", f"The server didn't accept the sign-in for {d['user']}@{d['host']}: {e}")
            except (socket.error, paramiko.SSHException, EOFError) as e:
                if "authentication" in str(e).lower():          # e.g. no password, no key and no agent
                    raise RemoteError("auth", f"No way to sign in to {d['host']}: {e}. Give a password or a key.")
                if isinstance(e, socket.gaierror):
                    raise RemoteError("offline", f"There's no server called {d['host']} (or no internet).")
                if "Unable to connect to port" in str(e) or isinstance(e, ConnectionRefusedError):
                    raise RemoteError("offline", f"Couldn't reach {d['host']}: nothing answered on port {d['port'] or 22}.")
                if isinstance(e, socket.timeout):
                    raise RemoteError("offline", f"Couldn't reach {d['host']}: no answer (a firewall, or the wrong address?).")
                raise RemoteError("offline", f"Couldn't reach {d['host']}: {e}")
            self.server_key = ssh.get_transport().get_remote_server_key()
            fp = fingerprint(self.server_key)
            if d.get("hostkey") and d["hostkey"] != fp:
                ssh.close()
                raise RemoteError("hostkey", f"{d['host']} has a different key from last time ({fp}, expected {d['hostkey']}). "
                                             "If the server was rebuilt, clear the remembered key and connect again.")
            if not d.get("hostkey"):
                d["hostkey"] = fp
                if self.on_hostkey:
                    try:
                        self.on_hostkey(fp)
                    except Exception:
                        pass
            ssh.get_transport().set_keepalive(30)
            self._ssh = ssh
            actas = (d.get("actas") or "").strip()
            login = ssh.get_transport().get_username()
            if actas and actas != login:
                self.sftp_path = sftp_server_path(ssh)
                self._sftp = _sudo_sftp(ssh, login, actas, self.sftp_path)
            else:
                self._sftp = ssh.open_sftp()
            root = (d.get("remote") or "").strip() or "."
            self._root = self._sftp.normalize(root)
            self.cache = _Cache()

    @staticmethod
    def _load_key(path, passphrase, text=""):
        import paramiko
        path = os.path.expanduser(path)
        if not text and not os.path.isfile(path):
            raise RemoteError("auth", f"There's no key file at {path}.")
        last = None
        for cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
            try:
                if text:
                    return cls.from_private_key(io.StringIO(reshape_key(text)), password=passphrase)
                return cls.from_private_key_file(path, password=passphrase)
            except paramiko.PasswordRequiredException:
                raise RemoteError("auth", "That key needs its passphrase.")
            except Exception as e:
                last = e
        raise RemoteError("auth", f"Couldn't read the key {path}: {last}")

    def close(self):
        with self._lock:
            for c in (self._sftp, self._ssh):
                try:
                    if c:
                        c.close()
                except Exception:
                    pass
            self._ssh = self._sftp = None

    @property
    def connected(self):
        t = self._ssh.get_transport() if self._ssh else None
        return bool(t and t.is_active())

    def _p(self, rel):
        return posixpath.join(self._root, _clean(rel).lstrip("/")) if _clean(rel) != "/" else self._root

    def _do(self, fn):
        """Run fn(sftp); once more after reconnecting if the connection had dropped.
        (An SFTP refusal and a dropped line are both OSErrors in Python 3: whether the connection is still up
        is what tells them apart.)"""
        for attempt in (1, 2):
            try:
                if not self.connected:
                    self.connect()
                return fn(self._sftp)
            except RemoteError:
                raise
            except Exception as e:
                if self.connected and isinstance(e, OSError) and not isinstance(e, (ConnectionError, socket.timeout)):
                    raise RemoteError(_kind(e), str(e))       # the server said no
                if attempt == 2:
                    raise RemoteError("offline", str(e))
                time.sleep(0.5)

    # ── operations ──
    def stat(self, rel):
        a = self._do(lambda s: s.stat(self._p(rel)))
        return _from_attr(posixpath.basename(_clean(rel)) or "/", a)

    def listdir(self, rel):
        return [_from_attr(a.filename, a) for a in self._do(lambda s: s.listdir_attr(self._p(rel)))
                if a.filename not in (".", "..")]

    def open(self, rel, mode):
        writing = "w" in mode or "a" in mode or "+" in mode
        if writing:
            self.cache.forget(_clean(rel))
            # no local buffer: every write goes straight out, pipelined, so a size asked for right after (on the same
            # channel, so answered in order) is already right; Windows trusts the size it's told after each write
            f = self._do(lambda s: s.open(self._p(rel), mode, bufsize=0))
            f.set_pipelined(True)
        else:
            f = self._do(lambda s: s.open(self._p(rel), mode, bufsize=1 << 16))
            try:
                if self.cstat(rel).size <= 16 << 20:
                    f.prefetch()          # small files: fetch it all at once; big ones (videos...) only what's read
            except RemoteError:
                pass
        return _SftpFile(f, self, rel)

    def mkdir(self, rel):
        self.cache.forget(_clean(rel))
        self._do(lambda s: s.mkdir(self._p(rel)))

    def remove(self, rel):
        self.cache.forget(_clean(rel))
        self._do(lambda s: s.remove(self._p(rel)))

    def rmdir(self, rel):
        self.cache.forget(_clean(rel))
        try:
            self._do(lambda s: s.rmdir(self._p(rel)))
        except RemoteError as e:
            if e.kind == "io" and self.listdir(rel):     # SFTP reports a non-empty folder as a plain failure
                raise RemoteError("notempty", str(e))
            raise

    def rename(self, old, new):
        self.cache.forget(_clean(old), _clean(new))
        po, pn = self._p(old), self._p(new)

        def go(s):
            try:
                s.posix_rename(po, pn)          # OpenSSH: replaces new atomically
            except IOError as e:
                if getattr(e, "errno", None) not in (None, errno.EOPNOTSUPP):
                    raise
                try:
                    s.remove(pn)
                except IOError:
                    pass
                s.rename(po, pn)
        self._do(go)

    def truncate(self, rel, size):
        self.cache.forget(_clean(rel))
        self._do(lambda s: s.truncate(self._p(rel), size))

    def set_times(self, rel, atime, mtime):
        self.cache.forget(_clean(rel))
        self._do(lambda s: s.utime(self._p(rel), (atime, mtime)))

    def space(self):
        try:
            out = self._do(lambda s: self._ssh.exec_command(f"df -Pk '{self._root}'", timeout=10)[1].read().decode())
            parts = out.strip().splitlines()[-1].split()
            return (int(parts[1]) * 1024, int(parts[3]) * 1024)
        except Exception:
            return super().space()


class _SftpFile:
    """A remote file that remembers which drive path it belongs to, so writes clear the cache."""

    def __init__(self, f, remote, rel):
        self.f, self.remote, self.rel = f, remote, _clean(rel)

    def read(self, n=-1):
        return self.f.read(n)

    def write(self, b):
        self.remote.cache.forget(self.rel)
        return self.f.write(b)

    def seek(self, pos, whence=0):
        return self.f.seek(pos, whence)

    def tell(self):
        return self.f.tell()

    def truncate(self, size):
        self.remote.cache.forget(self.rel)
        return self.f.truncate(size)

    def flush(self):
        return self.f.flush()

    def close(self):
        try:
            self.f.close()
        finally:
            self.remote.cache.forget(self.rel)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
#  Windows: WinFsp
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════

def winfsp_available():
    if not WINDOWS:
        return False
    try:
        import winfspy  # noqa: F401  (loads winfsp-x64.dll; fails if WinFsp isn't installed)
        return True
    except Exception:
        return False


EPOCH_AS_FILETIME = 116444736000000000


def _ft(t):
    return int(t * 10_000_000) + EPOCH_AS_FILETIME


def _unix(ft):
    return (ft - EPOCH_AS_FILETIME) / 10_000_000


def _winfsp_operations():
    """Built on first use, so this module imports fine where winfspy isn't installed."""
    from winfspy import (BaseFileSystemOperations, FILE_ATTRIBUTE, CREATE_FILE_CREATE_OPTIONS, NTStatusError,
                         NTStatusObjectNameNotFound, NTStatusObjectNameCollision, NTStatusAccessDenied,
                         NTStatusNotADirectory, NTStatusEndOfFile, NTStatusDirectoryNotEmpty,
                         NTStatusMediaWriteProtected)
    from winfspy.plumbing.security_descriptor import SecurityDescriptor
    from winfspy.plumbing.status import NTSTATUS

    NT = {"notfound": NTStatusObjectNameNotFound, "exists": NTStatusObjectNameCollision, "denied": NTStatusAccessDenied,
          "notdir": NTStatusNotADirectory, "notempty": NTStatusDirectoryNotEmpty}
    DELETE, SET_WRITE_TIME = 0x01, 0x40

    def nt(fn):
        def wrapper(self, *a, **kw):
            try:
                return fn(self, *a, **kw)
            except RemoteError as e:
                if e.kind in NT:
                    raise NT[e.kind]()
                if e.kind == "offline":
                    raise NTStatusError(NTSTATUS.STATUS_NETWORK_UNREACHABLE)
                raise NTStatusError(NTSTATUS.STATUS_UNEXPECTED_IO_ERROR)
        wrapper.__name__ = fn.__name__
        return wrapper

    class Ctx:
        def __init__(self, rel, is_dir):
            self.rel, self.is_dir, self.f, self.writing = rel, is_dir, None, False

    class SshOperations(BaseFileSystemOperations):
        def __init__(self, remote, label):
            super().__init__()
            self.r = remote
            self.label = (label or "SSH")[:31]
            self.sd = SecurityDescriptor.from_string("O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;WD)")
            self._lock = threading.RLock()

        @staticmethod
        def _rel(file_name):
            return _clean(str(file_name))

        def _attrs(self, e):
            a = FILE_ATTRIBUTE.FILE_ATTRIBUTE_DIRECTORY if e.is_dir else FILE_ATTRIBUTE.FILE_ATTRIBUTE_ARCHIVE
            if e.name.startswith(".") and e.name not in (".", ".."):
                a |= FILE_ATTRIBUTE.FILE_ATTRIBUTE_HIDDEN
            if self.r.readonly:
                a |= FILE_ATTRIBUTE.FILE_ATTRIBUTE_READONLY
            return a

        def _info(self, e):
            alloc = (e.size + 4095) // 4096 * 4096
            return {"file_attributes": self._attrs(e), "allocation_size": alloc, "file_size": e.size,
                    "creation_time": _ft(e.mtime), "last_access_time": _ft(e.atime or e.mtime),
                    "last_write_time": _ft(e.mtime), "change_time": _ft(e.mtime), "index_number": 0}

        def _ro(self):
            if self.r.readonly:
                raise NTStatusMediaWriteProtected()

        @nt
        def get_volume_info(self):
            total, free = self.r.space()
            return {"total_size": total, "free_size": free, "volume_label": self.label}

        def set_volume_label(self, volume_label):
            self.label = volume_label[:31]

        @nt
        def get_security_by_name(self, file_name):
            e = self.r.cstat(self._rel(file_name))
            return (self._attrs(e), self.sd.handle, self.sd.size)

        @nt
        def create(self, file_name, create_options, granted_access, file_attributes, security_descriptor, allocation_size):
            self._ro()
            rel = self._rel(file_name)
            parent = posixpath.dirname(rel) or "/"
            if not self.r.cstat(parent).is_dir:
                raise NTStatusNotADirectory()
            if self.r.exists(rel):
                raise NTStatusObjectNameCollision()
            if create_options & CREATE_FILE_CREATE_OPTIONS.FILE_DIRECTORY_FILE:
                self.r.mkdir(rel)
                return Ctx(rel, True)
            c = Ctx(rel, False)
            c.f, c.writing = self.r.open(rel, "w+b"), True
            return c

        @nt
        def open(self, file_name, create_options, granted_access):
            rel = self._rel(file_name)
            return Ctx(rel, self.r.cstat(rel).is_dir)

        def _handle(self, c, write):
            with self._lock:
                if c.f and (c.writing or not write):
                    return c.f
                if c.f:
                    c.f.close()
                c.f, c.writing = self.r.open(c.rel, "r+b" if write else "rb"), write
                return c.f

        def close(self, file_context):
            if file_context.f:
                try:
                    file_context.f.close()
                except Exception:
                    pass
                file_context.f = None

        @nt
        def get_file_info(self, file_context):
            return self._info(self.r.cstat(file_context.rel))

        @nt
        def get_security(self, file_context):
            return self.sd

        def set_security(self, file_context, security_information, modification_descriptor):
            pass      # the server's own permissions are what count

        @nt
        def read(self, file_context, offset, length):
            size = self.r.cstat(file_context.rel).size
            if offset >= size:
                raise NTStatusEndOfFile()
            f = self._handle(file_context, False)
            with self._lock:
                f.seek(offset)
                return f.read(min(length, size - offset))

        @nt
        def write(self, file_context, buffer, offset, write_to_end_of_file, constrained_io):
            self._ro()
            data = bytes(buffer)
            # the size only matters for appends and constrained writes: plain writes skip the round trip
            size = self.r.cstat(file_context.rel).size if (write_to_end_of_file or constrained_io) else 0
            if write_to_end_of_file:
                if file_context.f:
                    file_context.f.flush()
                    size = self.r.stat(file_context.rel).size
                offset = size
            if constrained_io:
                if offset >= size:
                    return 0
                data = data[:size - offset]
            f = self._handle(file_context, True)
            with self._lock:
                f.seek(offset)
                f.write(data)
            return len(data)

        @nt
        def flush(self, file_context):
            if file_context and file_context.f:
                file_context.f.flush()

        @nt
        def set_file_size(self, file_context, new_size, set_allocation_size):
            self._ro()
            if set_allocation_size:
                return        # allocation is the server's business
            if file_context.f and file_context.writing:
                file_context.f.truncate(new_size)
            else:
                self.r.truncate(file_context.rel, new_size)

        @nt
        def overwrite(self, file_context, file_attributes, replace_file_attributes, allocation_size):
            self._ro()
            f = self._handle(file_context, True)
            f.truncate(0)

        @nt
        def set_basic_info(self, file_context, file_attributes, creation_time, last_access_time, last_write_time,
                           change_time, file_info):
            if last_write_time and not self.r.readonly:
                a = _unix(last_access_time) if last_access_time else _unix(last_write_time)
                try:
                    if file_context.f:
                        file_context.f.flush()
                    self.r.set_times(file_context.rel, a, _unix(last_write_time))
                except RemoteError:
                    pass      # some servers won't set times: not worth failing the copy for
            return self._info(self.r.cstat(file_context.rel))

        @nt
        def can_delete(self, file_context, file_name):
            self._ro()
            if file_context.is_dir and self.r.clistdir(file_context.rel):
                raise NTStatusDirectoryNotEmpty()

        @nt
        def cleanup(self, file_context, file_name, flags):
            if flags & DELETE:
                self.close(file_context)
                if file_context.is_dir:
                    self.r.rmdir(file_context.rel)
                else:
                    self.r.remove(file_context.rel)

        @nt
        def rename(self, file_context, file_name, new_file_name, replace_if_exists):
            self._ro()
            old, new = self._rel(file_name), self._rel(new_file_name)
            if self.r.exists(new) and old.lower() != new.lower():
                if not replace_if_exists:
                    raise NTStatusObjectNameCollision()
                if self.r.cstat(new).is_dir:
                    raise NTStatusAccessDenied()
            self.close(file_context)
            self.r.rename(old, new)
            file_context.rel = new

        @nt
        def read_directory(self, file_context, marker):
            if not file_context.is_dir:
                raise NTStatusNotADirectory()
            rel = file_context.rel
            out = []
            if rel != "/":
                me = self.r.cstat(rel)
                up = self.r.cstat(posixpath.dirname(rel) or "/")
                out += [{"file_name": ".", **self._info(me)}, {"file_name": "..", **self._info(up)}]
            out += [{"file_name": e.name, **self._info(e)} for e in self.r.clistdir(rel)]
            out.sort(key=lambda x: x["file_name"])
            if marker is None:
                return out
            return [x for x in out if x["file_name"] > marker]

        @nt
        def get_dir_info_by_name(self, file_context, file_name):
            e = self.r.cstat(posixpath.join(file_context.rel, file_name))
            return {"file_name": file_name, **self._info(e)}

    return SshOperations


class WinFspDrive:
    method = "winfsp"

    def __init__(self, remote, mountpoint, label):
        from winfspy import FileSystem
        from winfspy.plumbing.win32_filetime import filetime_now
        ops = _winfsp_operations()(remote, label)
        mp = mountpoint.rstrip("\\/")
        self.mountpoint = mp
        self.fs = FileSystem(mp, ops, sector_size=512, sectors_per_allocation_unit=8, volume_creation_time=filetime_now(),
                             volume_serial_number=int(hashlib.md5(label.encode()).hexdigest()[:8], 16), file_info_timeout=1000,
                             case_sensitive_search=1, case_preserved_names=1, unicode_on_disk=1, persistent_acls=1,
                             post_cleanup_when_modified_only=1, um_file_context_is_user_context2=1,
                             file_system_name="SSHDrive", prefix="", reject_irp_prior_to_transact0=False,
                             read_only_volume=bool(remote.readonly))
        self.fs.start()

    def stop(self):
        try:
            self.fs.stop()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
#  Everywhere: WebDAV on 127.0.0.1 (Windows maps it to a letter with its own WebDAV client)
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════

def _dav_provider_class():
    from wsgidav.dav_provider import DAVProvider, DAVCollection, DAVNonCollection
    from wsgidav.dav_error import (DAVError, HTTP_NOT_FOUND, HTTP_FORBIDDEN, HTTP_CONFLICT, HTTP_INTERNAL_ERROR,
                                   HTTP_PRECONDITION_FAILED)

    def dav(fn):
        def wrapper(*a, **kw):
            try:
                return fn(*a, **kw)
            except RemoteError as e:
                raise DAVError({"notfound": HTTP_NOT_FOUND, "denied": HTTP_FORBIDDEN, "exists": HTTP_PRECONDITION_FAILED,
                                "notempty": HTTP_CONFLICT}.get(e.kind, HTTP_INTERNAL_ERROR), str(e))
        return wrapper

    class Writer(io.RawIOBase):
        """Upload body goes straight to the remote file."""

        def __init__(self, f):
            self.f = f

        def writable(self):
            return True

        def write(self, b):
            self.f.write(bytes(b))
            return len(b)

        def close(self):
            if not self.closed:
                self.f.close()
            super().close()

    class Folder(DAVCollection):
        def __init__(self, path, environ, remote):
            super().__init__(path, environ)
            self.r = remote

        def _rel(self):
            return _clean(self.path)

        @dav
        def get_member_names(self):
            return [e.name for e in self.r.clistdir(self._rel())]

        def get_member(self, name):
            return self.provider.get_resource_inst(posixpath.join(self.path, name), self.environ)

        def get_display_info(self):
            return {"type": "Directory"}

        @dav
        def get_last_modified(self):
            return self.r.cstat(self._rel()).mtime

        def get_creation_date(self):
            return self.get_last_modified()

        @dav
        def create_empty_resource(self, name):
            if self.r.readonly:
                raise DAVError(HTTP_FORBIDDEN)
            rel = posixpath.join(self._rel(), name)
            self.r.open(rel, "wb").close()
            return self.provider.get_resource_inst(posixpath.join(self.path, name), self.environ)

        @dav
        def create_collection(self, name):
            if self.r.readonly:
                raise DAVError(HTTP_FORBIDDEN)
            self.r.mkdir(posixpath.join(self._rel(), name))

        @dav
        def delete(self):
            if self.r.readonly:
                raise DAVError(HTTP_FORBIDDEN)
            self._rmtree(self._rel())
            self.remove_all_properties(recursive=True)
            self.remove_all_locks(recursive=True)

        def _rmtree(self, rel):
            for e in self.r.listdir(rel):
                p = posixpath.join(rel, e.name)
                self._rmtree(p) if e.is_dir else self.r.remove(p)
            self.r.rmdir(rel)

        def support_recursive_move(self, dest_path):
            return True

        @dav
        def move_recursive(self, dest_path):
            if self.r.readonly:
                raise DAVError(HTTP_FORBIDDEN)
            self.r.rename(self._rel(), _clean(dest_path))

        @dav
        def copy_move_single(self, dest_path, *, is_move):
            if is_move:
                self.r.rename(self._rel(), _clean(dest_path))
            else:
                self.r.mkdir(_clean(dest_path))

    class File(DAVNonCollection):
        def __init__(self, path, environ, remote, entry):
            super().__init__(path, environ)
            self.r, self.e = remote, entry

        def _rel(self):
            return _clean(self.path)

        def get_content_length(self):
            return self.e.size

        def get_content_type(self):
            import mimetypes
            return mimetypes.guess_type(self.path)[0] or "application/octet-stream"

        def get_creation_date(self):
            return self.e.mtime

        def get_last_modified(self):
            return self.e.mtime

        def get_etag(self):
            return f"{int(self.e.mtime)}-{self.e.size}"

        def support_etag(self):
            return True

        def support_ranges(self):
            return True

        def get_display_name(self):
            return self.name

        @dav
        def get_content(self):
            return self.r.open(self._rel(), "rb")

        @dav
        def begin_write(self, *, content_type=None):
            if self.r.readonly:
                raise DAVError(HTTP_FORBIDDEN)
            return Writer(self.r.open(self._rel(), "wb"))

        @dav
        def delete(self):
            if self.r.readonly:
                raise DAVError(HTTP_FORBIDDEN)
            self.r.remove(self._rel())
            self.remove_all_properties(recursive=True)
            self.remove_all_locks(recursive=True)

        def support_recursive_move(self, dest_path):
            return True

        @dav
        def move_recursive(self, dest_path):
            if self.r.readonly:
                raise DAVError(HTTP_FORBIDDEN)
            self.r.rename(self._rel(), _clean(dest_path))

        @dav
        def copy_move_single(self, dest_path, *, is_move):
            if self.r.readonly:
                raise DAVError(HTTP_FORBIDDEN)
            if is_move:
                self.r.rename(self._rel(), _clean(dest_path))
                return
            with self.r.open(self._rel(), "rb") as src, self.r.open(_clean(dest_path), "wb") as dst:
                while True:
                    b = src.read(1 << 16)
                    if not b:
                        break
                    dst.write(b)

    class SshProvider(DAVProvider):
        def __init__(self, remote):
            super().__init__()
            self.r = remote

        def is_readonly(self):
            return self.r.readonly

        def get_resource_inst(self, path, environ):
            self._count_get_resource_inst += 1
            try:
                e = self.r.cstat(_clean(path))
            except RemoteError as err:
                if err.kind == "notfound":
                    return None
                raise
            return Folder(path, environ, self.r) if e.is_dir else File(path, environ, self.r, e)

    return SshProvider


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class WebDavDrive:
    method = "webdav"

    def __init__(self, remote, mountpoint, label, port=0, map_drive=True):
        from cheroot import wsgi
        from wsgidav.wsgidav_app import WsgiDAVApp
        self.port = port or free_port()
        self.url = f"http://127.0.0.1:{self.port}/"
        self.mountpoint = mountpoint
        app = WsgiDAVApp({
            "provider_mapping": {"/": _dav_provider_class()(remote)},
            "simple_dc": {"user_mapping": {"*": True}},     # 127.0.0.1 only, so no sign-in on top of SSH's
            "verbose": 1, "logging": {"enable": False}, "lock_storage": True,
            "hotfixes": {"emulate_win32_lastmod": True, "re_encode_path_info": True},
            "dir_browser": {"enable": True},
        })
        self.server = wsgi.Server(("127.0.0.1", self.port), app, numthreads=8)
        self.thread = threading.Thread(target=self.server.safe_start, daemon=True, name=f"webdav-{label}")
        self.thread.start()
        for _ in range(50):
            if self.server.ready:
                break
            time.sleep(0.1)
        self.mapped = False
        if map_drive and WINDOWS and mountpoint:
            letter = mountpoint.rstrip("\\/:")[:1] + ":"
            unc = rf"\\127.0.0.1@{self.port}\DavWWWRoot"
            subprocess.run(["net", "use", letter, "/delete", "/y"], capture_output=True, creationflags=_NO_WINDOW)
            r = subprocess.run(["net", "use", letter, unc, "/persistent:no"], capture_output=True, text=True,
                               creationflags=_NO_WINDOW)
            if r.returncode:
                self.stop()
                raise RemoteError("io", "Windows wouldn't map the drive: " + (r.stderr or r.stdout).strip() +
                                  " (is the WebClient service running?)")
            self.mapped = True
            self.mountpoint = letter

    def stop(self):
        if self.mapped:
            subprocess.run(["net", "use", self.mountpoint, "/delete", "/y"], capture_output=True, creationflags=_NO_WINDOW)
        try:
            self.server.stop()
        except Exception:
            pass


_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
#  Linux / macOS: the system's sshfs
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════

def _own_folder():
    """Where SSH Drive keeps its own bits on this computer (known server keys, the passphrase helper)."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    folder = os.path.join(base, "visualised", "sshdrive")
    os.makedirs(folder, mode=0o700, exist_ok=True)
    return folder


ASKPASS = "#!/bin/sh\n# SSH Drive: hands ssh the drive's password or key passphrase (kept in this process's own environment)\n" \
          "printf '%s\\n' \"$SSHDRIVE_SECRET\"\n"
HOSTKEY_ALGOS = {"ssh-rsa": "rsa-sha2-512,rsa-sha2-256"}       # (what ssh calls the ways to use each kind of key)


def _shows_itself(path):
    """Does the file manager list this mount by itself? (GIO shows mounts in the home folder, outside hidden
    folders, and under /media and /run/media: a bookmark as well would show it twice.)"""
    path = os.path.abspath(path)
    home = os.path.expanduser("~").rstrip("/")
    if path.startswith(home + "/"):
        return "/." not in path[len(home):]
    return path.startswith(("/media/", "/run/media/"))


def _bookmark(path, name, on):
    """A drive in the file manager's sidebar (GNOME Files and others read GTK's bookmarks), when it wouldn't be
    there anyway. Turning it off, or finding the mount shows itself, takes away any bookmark made before."""
    from urllib.parse import quote
    if on and _shows_itself(path):
        on = False
    bm = os.path.join(os.path.expanduser("~"), ".config", "gtk-3.0", "bookmarks")
    line = f"file://{quote(path)} {name}"
    try:
        lines = open(bm, encoding="utf-8").read().splitlines() if os.path.exists(bm) else []
        mine = f"file://{quote(path)}"
        kept = [l for l in lines if l.split(" ", 1)[0] != mine]
        if on:
            kept.append(line)
        if kept != lines:
            os.makedirs(os.path.dirname(bm), exist_ok=True)
            with open(bm, "w", encoding="utf-8") as f:
                f.write("\n".join(kept) + ("\n" if kept else ""))
    except OSError:
        pass


def _sshfs_problem(text, d):
    """sshfs's (that is, ssh's) complaint in plain words."""
    t = text.strip()
    low = t.lower()
    if "host key verification failed" in low:
        return f"{d['host']}'s key couldn't be checked. Test the drive again, then save."
    if "permission denied" in low:
        return f"The server didn't accept the sign-in for {d['user'] or 'that user'}."
    if "connection refused" in low:
        return f"Nothing answers on port {d['port'] or 22} at {d['host']}."
    if "timed out" in low:
        return f"No answer from {d['host']} (a firewall, or blocked for a while?)."
    if "not empty" in low:
        return f"The folder it goes in isn't empty: {t}"
    if "fuse: device not found" in low or "/dev/fuse" in low:
        return "This computer can't mount folders (FUSE isn't available)."
    return t or "sshfs couldn't mount it."


class SshfsDrive:
    """A folder in the file manager through the system's sshfs. The app has already signed in once itself (so it
    knows the server's key and that the sign-in works); sshfs is handed exactly that key, and the password or
    passphrase through a helper, so nothing waits for a question nobody can see."""
    method = "sshfs"

    def __init__(self, drive, mountpoint, server_key=None, sftp_path=""):
        d = dict(DRIVE_DEFAULTS, **drive)
        if not shutil.which("sshfs"):
            raise RemoteError("io", "sshfs isn't installed (on Ubuntu: sudo apt install sshfs)")
        self.name = d["name"] or d["host"]
        mp = os.path.expanduser(mountpoint or os.path.join("~", "SSH", self.name))
        if os.path.ismount(mp):                                  # left from before (the app was killed): let it go
            subprocess.run(["fusermount", "-uz", mp], capture_output=True, timeout=8)
        os.makedirs(mp, exist_ok=True)
        self.mountpoint = mp
        own = _own_folder()
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in self.name)
        port = int(d.get("port") or 22)
        opts = ["reconnect", "ServerAliveInterval=15", "ServerAliveCountMax=3", "follow_symlinks", "ConnectTimeout=15",
                f"fsname=sshdrive:{self.name}"]
        if sys.platform == "darwin":
            opts.append(f"volname={self.name}")                  # (macFUSE only: Linux's FUSE refuses it)
        if d.get("readonly"):
            opts.append("ro")
        actas = (d.get("actas") or "").strip()
        if actas and sftp_path:                                 # the other end works as that user (checked: sudo allows it)
            import shlex
            opts.append(f"sftp_server=sudo -n -u {shlex.quote(actas)} {shlex.quote(sftp_path)}")
        if server_key is not None:                               # exactly the key the app has pinned, and no other
            kh = os.path.join(own, f"known_hosts-{safe}")
            who = d["host"] if port == 22 else f"[{d['host']}]:{port}"
            with open(kh, "w") as f:
                f.write(f"{who} {server_key.get_name()} {server_key.get_base64()}\n")
            opts += [f"UserKnownHostsFile={kh}", "GlobalKnownHostsFile=/dev/null", "StrictHostKeyChecking=yes",
                     "HostKeyAlgorithms=" + HOSTKEY_ALGOS.get(server_key.get_name(), server_key.get_name())]
        self.keyfile = None
        secret = ""
        auth = d.get("auth") or "agent"
        if auth == "key":
            if d.get("keytext"):                                 # the key itself: a file only sshfs can read, while mounted
                self.keyfile = os.path.join(own, f"key-{safe}")
                fd = os.open(self.keyfile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as f:
                    f.write(reshape_key(d["keytext"]))
                opts.append("IdentityFile=" + self.keyfile)
            else:
                opts.append("IdentityFile=" + os.path.expanduser(d["key"]))
            opts.append("IdentitiesOnly=yes")
            secret = d.get("passphrase") or ""
        elif auth == "password":
            opts += ["PreferredAuthentications=keyboard-interactive,password", "PubkeyAuthentication=no"]
            secret = d.get("password") or ""
        env = dict(os.environ)
        if secret:
            helper = os.path.join(own, "askpass")
            if not os.path.exists(helper) or open(helper).read() != ASKPASS:
                with open(helper, "w") as f:
                    f.write(ASKPASS)
                os.chmod(helper, 0o700)
            env.update(SSH_ASKPASS=helper, SSH_ASKPASS_REQUIRE="force", SSHDRIVE_SECRET=secret, DISPLAY=env.get("DISPLAY", ":0"))
        target = f"{d['user'] + '@' if d['user'] else ''}{d['host']}:{d.get('remote') or ''}"
        cmd = ["sshfs", target, mp, "-p", str(port)]
        for o in opts:                                           # one -o each; a comma inside a value is escaped for FUSE
            cmd += ["-o", o.replace("\\", "\\\\").replace(",", "\\,")]
        try:
            r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env, timeout=40,
                               start_new_session=True)          # (no terminal for ssh to ask anything on)
        except subprocess.TimeoutExpired:
            self._forget()
            raise RemoteError("offline", f"{d['host']} took too long to answer.")
        if r.returncode:
            self._forget()
            raise RemoteError("io", _sshfs_problem(r.stderr or r.stdout, d))
        _bookmark(mp, self.name, True)

    def _forget(self):
        if self.keyfile and os.path.exists(self.keyfile):
            os.remove(self.keyfile)

    def stop(self):
        """Unmount; if something has it open (a file manager window), or the server has gone, unmount it lazily:
        it goes as soon as it's let go, and nothing is left hanging meanwhile."""
        mp = self.mountpoint
        _bookmark(mp, self.name, False)
        try:
            for flags in ("-u", "-uz"):
                for tool in ("fusermount3", "fusermount"):
                    if shutil.which(tool):
                        try:
                            if subprocess.run([tool, flags, mp], capture_output=True, timeout=8).returncode == 0:
                                return
                        except subprocess.TimeoutExpired:
                            pass
                        break
            if sys.platform == "darwin":
                subprocess.run(["umount", "-f", mp], capture_output=True, timeout=8)
        finally:
            self._forget()


# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
#  Mounting
# ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════

def free_letter():
    """The highest unused drive letter, Z: downwards."""
    import string
    used = set()
    if WINDOWS:
        import ctypes
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        used = {string.ascii_uppercase[i] for i in range(26) if mask >> i & 1}
    for L in reversed(string.ascii_uppercase[3:]):
        if L not in used:
            return L + ":"
    raise RemoteError("io", "No free drive letters")


SFTP_SERVERS = ("/usr/lib/openssh/sftp-server", "/usr/libexec/openssh/sftp-server", "/usr/lib/ssh/sftp-server",
                "/usr/libexec/sftp-server", "/usr/lib/sftp-server")


def _run(ssh, command, stdin=None, wait=20):
    """Run a command on the server: (exit status, stdout, stderr)."""
    chan = ssh.get_transport().open_session()
    chan.settimeout(wait)
    chan.exec_command(command)
    if stdin is not None:
        chan.sendall(stdin.encode())
    chan.shutdown_write()
    out, err = b"", b""
    end = time.time() + wait
    try:
        while time.time() < end:                         # both streams, until the command has finished and said all
            busy = False
            if chan.recv_ready():
                out += chan.recv(65536); busy = True
            if chan.recv_stderr_ready():
                err += chan.recv_stderr(65536); busy = True
            if not busy:
                if chan.exit_status_ready() and not chan.recv_ready() and not chan.recv_stderr_ready():
                    break
                time.sleep(0.02)
    except socket.timeout:
        pass
    status = chan.recv_exit_status() if chan.status_event.wait(max(0.0, end - time.time())) else -1
    chan.close()
    return status, out.decode(errors="replace"), err.decode(errors="replace")


def sftp_server_path(ssh):
    """Where this server keeps sftp-server (it differs between Linux families)."""
    probe = "; ".join(f'[ -x {p} ] && {{ echo {p}; exit 0; }}' for p in SFTP_SERVERS)
    status, out, _ = _run(ssh, probe + "; awk 'tolower($1)==\"subsystem\" && $2==\"sftp\" {print $3; exit}' /etc/ssh/sshd_config")
    path = out.strip().splitlines()[0] if out.strip() else ""
    if not path.startswith("/"):
        raise RemoteError("io", "Couldn't find sftp-server on the server, to run it as another user.")
    return path


def _check_actas(name):
    import re
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", name or ""):
        raise RemoteError("auth", f"\"{name}\" isn't a user name (try root or www-data).")


def _sudo_sftp(ssh, login, actas, path):
    """SFTP as another user: the server's sftp-server started through sudo (which must allow it without a password:
    there's no terminal to type one into; allow_sudo sets that up)."""
    import shlex
    import paramiko
    _check_actas(actas)
    chan = ssh.get_transport().open_session()
    chan.exec_command(f"sudo -n -u {shlex.quote(actas)} {shlex.quote(path)}")
    try:
        return paramiko.SFTPClient(chan)
    except Exception:
        why = ""
        try:
            chan.settimeout(3)
            why = chan.recv_stderr(4096).decode(errors="replace")
        except Exception:
            pass
        chan.close()
        said = " ".join(why.strip().split())[:160]
        if "unknown user" in why:
            raise RemoteError("auth", f"There's no user {actas} on this server.")
        if why.strip() and "password is required" not in why and "a terminal is required" not in why:
            raise RemoteError("sudo", f"sudo wouldn't run the file server as {actas} (sudo said: {said}).")
        raise RemoteError("sudo", f"sudo won't let {login} act as {actas} without a password. "
                                  f"\"Allow it on the server\" sets that up (it asks for your sudo password once).")


def allow_sudo(drive, password):
    """Let this drive's user run sftp-server as `actas` without a password (a rule in /etc/sudoers.d of its own,
    checked with visudo before it is put in place, for that one program only). Returns (ok, what happened)."""
    import shlex
    d = dict(DRIVE_DEFAULTS, **drive)
    actas = (d.get("actas") or "").strip()
    _check_actas(actas)
    r = SftpRemote(dict(d, actas=""))
    try:
        ssh = r._ssh
        login = ssh.get_transport().get_username()
        path = sftp_server_path(ssh)
        rule = f"{login} ALL=({actas}) NOPASSWD: {path}"
        where = "/etc/sudoers.d/" + f"sshdrive-{login}-{actas}".replace(".", "_")   # (sudo skips names with dots)
        script = ('umask 077; t=$(mktemp) || exit 3; printf "%s\\n" "$1" > "$t" && visudo -cf "$t" >/dev/null '
                  '&& install -m 0440 -o root -g root "$t" "$2"; e=$?; rm -f "$t"; exit $e')
        command = f"sudo -S -p '' sh -c {shlex.quote(script)} sshdrive {shlex.quote(rule)} {shlex.quote(where)}"
        status, out, err = _run(ssh, command, stdin=(password or "") + "\n")
        low = err.lower()
        said = " ".join((err or out).strip().split())[:200]
        if status == 0:
            return True, f"Done: {login} can now work as {actas} through SSH Drive (the rule is in {where})."
        if "incorrect password" in low or "sorry, try again" in low or "no password was provided" in low:
            return False, (f"That isn't {login}'s sudo password on {d['host']} (a server's can differ from this computer's; "
                           f"sudo said: {said}).")
        if "not in the sudoers" in low or "not allowed" in low:
            return False, f"{login} isn't allowed to use sudo on {d['host']} (sudo said: {said})."
        return False, f"It didn't work (exit {status}): {said or 'nothing was said'}"
    finally:
        r.close()


def reshape_key(text):
    """A key pasted into a one-line box loses its line breaks: put them back (BEGIN line, body in 70s, END line)."""
    import re
    m = re.search(r"(-----BEGIN [A-Z0-9 ]+-----)(.*?)(-----END [A-Z0-9 ]+-----)", text.strip(), re.S)
    if not m or ":" in m.group(2):         # (an old PEM key with headers inside is left as it is)
        return text
    body = re.sub(r"\s+", "", m.group(2))
    return m.group(1) + "\n" + "".join(body[i:i + 70] + "\n" for i in range(0, len(body), 70)) + m.group(3) + "\n"


def likely_keys():
    """This user's private key files, the likeliest first (as ssh itself tries them)."""
    folder = os.path.join(os.path.expanduser("~"), ".ssh")
    found = []
    for name in ("id_ed25519", "id_ecdsa", "id_rsa", "id_ed25519_sk", "id_ecdsa_sk", "id_dsa"):
        p = os.path.join(folder, name)
        if os.path.isfile(p):
            found.append(p)
    try:                                       # any other private key in ~/.ssh (keys named after a server, say)
        for name in sorted(os.listdir(folder)):
            p = os.path.join(folder, name)
            if p not in found and not name.endswith(".pub") and os.path.isfile(p) and os.path.getsize(p) < 20000:
                with open(p, "rb") as f:
                    if b"PRIVATE KEY-----" in f.read(100):
                        found.append(p)
    except OSError:
        pass
    return found


def agent_available():
    """Whether an SSH agent is running with at least one key in it."""
    try:
        import paramiko
        a = paramiko.Agent()
        try:
            return len(a.get_keys()) > 0
        finally:
            a.close()
    except Exception:
        return False


# Cloudflare's proxy addresses (cloudflare.com/ips): a name behind them reaches web servers only, never SSH.
CLOUDFLARE = ("173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18",
              "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17",
              "162.158.0.0/15", "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
              "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32", "2405:8100::/32",
              "2a06:98c0::/29", "2c0f:f248::/32")


def behind_cloudflare(ip):
    import ipaddress
    try:
        a = ipaddress.ip_address(ip)
        return any(a in ipaddress.ip_network(n) for n in CLOUDFLARE if ipaddress.ip_network(n).version == a.version)
    except ValueError:
        return False


def diagnose(drive, wait=6):
    """The road to a server, a step at a time, before any signing in: does the name exist, is it Cloudflare's proxy
    (which carries no SSH), does anything answer on the port, and is it SSH that answers. Returns (ok, lines)."""
    d = dict(DRIVE_DEFAULTS, **drive)
    host, port = d["host"], int(d["port"] or 22)
    lines = []
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False, [f"✕ There's no server called {host} (check the spelling, or the internet)."]
    ips = list(dict.fromkeys(i[4][0] for i in infos))
    if ips != [host]:
        lines.append(f"✓ {host} is {', '.join(ips[:2])}")
    if all(behind_cloudflare(ip) for ip in ips):
        lines.append(f"✕ {'That' if ips != [host] else host} is Cloudflare's proxy, which carries web pages, not SSH. Use the server's own address, "
                     f"or a name for it that isn't proxied (grey cloud in Cloudflare).")
        return False, lines
    sock = None
    try:
        sock = socket.create_connection((host, port), timeout=wait)
    except ConnectionRefusedError:
        lines.append(f"✕ Nothing answers on port {port} (is SSH on another port?).")
        return False, lines
    except (socket.timeout, TimeoutError):
        lines.append(f"✕ No answer on port {port}: a firewall, or the server has blocked this computer for a while "
                     f"(fail2ban, after failed sign-ins).")
        return False, lines
    except OSError as e:
        lines.append(f"✕ Couldn't reach port {port}: {e.strerror or e}.")
        return False, lines
    try:
        sock.settimeout(wait)
        banner = b""
        while b"\n" not in banner and len(banner) < 512:
            got = sock.recv(256)
            if not got:
                break
            banner += got
        said = banner.decode("latin-1").strip().splitlines()[-1] if banner.strip() else ""
        if said.startswith("SSH-"):
            lines.append(f"✓ port {port} answers: {said[8:] or said}")
        elif said:
            lines.append(f"✕ Port {port} answers, but not with SSH (it said \"{said[:60]}\").")
            return False, lines
        else:
            lines.append(f"✕ Port {port} takes the connection, then hangs up: the server is turning new connections "
                         f"away (too many at once, or this computer is blocked for a while).")
            return False, lines
    except (socket.timeout, TimeoutError):
        lines.append(f"✕ Port {port} takes the connection but says nothing: the server is busy or limiting new connections.")
        return False, lines
    except OSError as e:
        lines.append(f"✕ Port {port} hung up: {e.strerror or e}.")
        return False, lines
    finally:
        try:
            sock.sendall(b"SSH-2.0-SSHDrive_check\r\n")   # a polite goodbye: not "no identification", which fail2ban counts
        except OSError:
            pass
        sock.close()
    return True, lines


def test(drive):
    """Try a drive without mounting it. Returns (ok, detail, hostkey): the folder it reaches, or what went wrong."""
    d = dict(DRIVE_DEFAULTS, **drive)
    ok, lines = diagnose(d)
    if not ok:
        return False, "\n".join(lines), ""
    try:
        r = SftpRemote(d)
    except Exception as e:
        return False, "\n".join(lines + ["✕ " + str(e)]), ""
    try:
        root = r._root
        try:
            files = len(r._sftp.listdir(root))
        except Exception:
            files = -1
        where = f"{d['user'] + '@' if d['user'] else ''}{d['host']}:{root}"
        if (d.get("actas") or "").strip():
            where += f", working as {d['actas'].strip()}"
        there = "" if files < 0 else " (empty)" if files == 0 else f" ({files} thing{'' if files == 1 else 's'} there)"
        return True, "\n".join(lines + [f"✓ Connected to {where}{there}"]), r.d.get("hostkey", "")
    finally:
        r.close()


def mount(drive, on_hostkey=None):
    """Mounts one drive. Returns the running drive (with .stop(), .method and .mountpoint)."""
    d = dict(DRIVE_DEFAULTS, **drive)
    method = d.get("method") or "auto"
    if method == "sshfs" or (method == "auto" and not WINDOWS and shutil.which("sshfs")):
        check = SftpRemote(d, on_hostkey=on_hostkey)            # signs in once: clear errors, and the server's key pinned
        key = getattr(check, "server_key", None)
        check.close()                                           # (and the folder as the server resolved it, so sshfs
        return SshfsDrive(dict(d, remote=check._root or d.get("remote")), d.get("mount"), server_key=key,   # agrees)
                          sftp_path=getattr(check, "sftp_path", ""))
    remote = SftpRemote(d, on_hostkey=on_hostkey)
    label = d.get("name") or d.get("host")
    if WINDOWS:
        mp = d.get("mount") or free_letter()
        if method in ("auto", "winfsp") and winfsp_available():
            try:
                drv = WinFspDrive(remote, mp, label)
                drv.remote = remote
                return drv
            except Exception:
                if method == "winfsp":
                    remote.close()
                    raise
        drv = WebDavDrive(remote, mp, label)
    else:
        drv = WebDavDrive(remote, "", label, map_drive=False)
        drv.mountpoint = drv.url
    drv.remote = remote
    return drv


class Drives:
    """The running drives, by name, with a watchdog that remounts any that drop (laptop asleep, Wi-Fi gone...)."""

    def __init__(self, on_change=None, on_hostkey=None):
        self.running, self.wanted, self.status = {}, {}, {}
        self.on_change, self.on_hostkey = on_change, on_hostkey
        self._lock = threading.Lock()
        self._watch = None

    def _say(self, name, state, detail=""):
        self.status[name] = {"state": state, "detail": detail}
        if self.on_change:
            try:
                self.on_change(name, state, detail)
            except Exception:
                pass

    def up(self, drive):
        name = drive.get("name") or drive.get("host")
        self.wanted[name] = dict(drive)
        self._say(name, "connecting")

        def go():
            try:
                with self._lock:
                    old = self.running.pop(name, None)
                if old:
                    old.stop()
                drv = mount(drive, on_hostkey=lambda fp: self.on_hostkey and self.on_hostkey(name, fp))
                with self._lock:
                    self.running[name] = drv
                self._say(name, "mounted", f"{drv.mountpoint} ({drv.method})")
            except RemoteError as e:
                why = str(e)
                if e.kind == "offline":                   # say which step of the way failed
                    ok, lines = diagnose(drive)
                    if not ok:
                        why = lines[-1].lstrip("✕ ")
                    if "Cloudflare" in why:               # trying again won't help: wait for the user
                        self._say(name, "error", why)
                        return
                self._say(name, "error" if e.kind != "offline" else "offline", why)
            except Exception as e:
                self._say(name, "error", str(e))
        threading.Thread(target=go, daemon=True).start()
        self._start_watch()

    def down(self, name):
        self.wanted.pop(name, None)
        with self._lock:
            drv = self.running.pop(name, None)
        if drv:
            drv.stop()
            r = getattr(drv, "remote", None)
            if r:
                r.close()
        self._say(name, "off")

    def down_all(self, wait=8.0):
        """Every drive down, side by side, giving up after `wait` seconds (quitting must never hang on a server)."""
        names = list(dict.fromkeys(list(self.wanted) + list(self.running)))
        threads = [threading.Thread(target=self.down, args=(n,), daemon=True) for n in names]
        for t in threads:
            t.start()
        end = time.time() + wait
        for t in threads:
            t.join(max(0.0, end - time.time()))

    def _start_watch(self):
        if self._watch:
            return

        def loop():
            while True:
                time.sleep(20)
                for name, d in list(self.wanted.items()):
                    drv = self.running.get(name)
                    r = getattr(drv, "remote", None)
                    if drv is None and self.status.get(name, {}).get("state") in ("offline", "error"):
                        if self.status[name]["state"] == "offline":
                            self.up(d)            # try again; real errors (password, host key) wait for the user
                    elif r is not None and not r.connected:
                        try:
                            r.connect()
                            self._say(name, "mounted", f"{drv.mountpoint} ({drv.method})")
                        except RemoteError as e:
                            self._say(name, "offline", str(e))
        self._watch = threading.Thread(target=loop, daemon=True, name="sshdrive-watch")
        self._watch.start()


def main(argv=None):
    import argparse
    import getpass
    import json
    ap = argparse.ArgumentParser(prog="python -m vml.sshdrive", description="A folder on an SSH server as a drive.")
    ap.add_argument("target", help="user@host:/folder")
    ap.add_argument("mount", nargs="?", default="", help="drive letter (Windows) or folder")
    ap.add_argument("-p", "--port", type=int, default=22)
    ap.add_argument("-i", "--key", default="")
    ap.add_argument("--password", action="store_true", help="ask for a password")
    ap.add_argument("--method", default="auto", choices=["auto", "winfsp", "webdav", "sshfs"])
    ap.add_argument("--readonly", action="store_true")
    a = ap.parse_args(argv)
    user, _, rest = a.target.rpartition("@")
    host, _, remote = rest.partition(":")
    d = dict(DRIVE_DEFAULTS, name=host, host=host, port=a.port, user=user, remote=remote, mount=a.mount,
             method=a.method, readonly=a.readonly)
    if a.password:
        d.update(auth="password", password=getpass.getpass(f"{user}@{host}'s password: "))
    elif a.key:
        d.update(auth="key", key=a.key)
    drv = mount(d, on_hostkey=lambda fp: print("server key:", fp))
    print(f"mounted at {drv.mountpoint} ({drv.method}); Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        drv.stop()
        print("stopped")


if __name__ == "__main__":
    main()
