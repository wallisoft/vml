"""
A terminal window: in a folder, or running a command (an ssh session) and staying open after it.
Linux: $TERMINAL, then the desktop's own (x-terminal-emulator, GNOME, KDE, Xfce, MATE...), then xterm.
Windows: Windows Terminal if it's there, else a console window. macOS: Terminal.
"""
import os
import shlex
import shutil
import subprocess
import sys

WINDOWS = sys.platform.startswith("win")
MAC = sys.platform == "darwin"

# how each Linux terminal is told: a folder to start in, and a command to run (argv after it)
LINUX = (
    ("gnome-terminal", ["--working-directory={cwd}"], ["--"]),
    ("kgx", ["--working-directory={cwd}"], ["-e"]),
    ("konsole", ["--workdir", "{cwd}"], ["-e"]),
    ("xfce4-terminal", ["--working-directory={cwd}"], ["-x"]),
    ("mate-terminal", ["--working-directory={cwd}"], ["-x"]),
    ("tilix", ["--working-directory={cwd}"], ["-e"]),
    ("kitty", ["--directory", "{cwd}"], []),
    ("alacritty", ["--working-directory", "{cwd}"], ["-e"]),
    ("wezterm", ["start", "--cwd", "{cwd}"], ["--"]),
    ("xterm", [], ["-e"]),
)


def _linux_terminal():
    own = os.environ.get("TERMINAL", "")
    if own and shutil.which(own.split()[0]):
        name = os.path.basename(own.split()[0])
        for t in LINUX:
            if t[0] == name:
                return t
        return (own.split()[0], [], ["-e"])
    for t in LINUX:
        if shutil.which(t[0]):
            return t
    if shutil.which("x-terminal-emulator"):                 # Debian's choice, whatever it is
        real = os.path.basename(os.path.realpath(shutil.which("x-terminal-emulator")))
        for t in LINUX:
            if real.startswith(t[0]):
                return ("x-terminal-emulator",) + t[1:]
        return ("x-terminal-emulator", [], ["-e"])
    return None


def open_terminal(cwd="", argv=None):
    """Open a terminal; returns "" or what went wrong. argv: a command to run there (the window stays open after)."""
    cwd = os.path.expanduser(cwd or "~")
    if not os.path.isdir(cwd):
        cwd = os.path.expanduser("~")
    try:
        if WINDOWS:
            line = subprocess.list2cmdline(argv) if argv else ""
            if shutil.which("wt"):
                cmd = ["wt", "-d", cwd] + (["cmd", "/k", line] if argv else [])
            else:
                cmd = ["cmd", "/c", "start", "", "cmd", "/k"] + ([line] if argv else [f'cd /d "{cwd}"'])
            subprocess.Popen(cmd, cwd=cwd, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return ""
        if MAC:
            script = f"cd {shlex.quote(cwd)}" + (f"; {shlex.join(argv)}" if argv else "")
            esc = script.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{esc}"',
                              "-e", 'tell application "Terminal" to activate'])
            return ""
        t = _linux_terminal()
        if not t:
            return "No terminal program found (set $TERMINAL to yours)."
        name, at, run = t
        cmd = [name] + [a.format(cwd=cwd) for a in at]
        if argv:                                             # (the shell after it keeps the window open to read)
            keep = f"{shlex.join(argv)}; echo; read -rp 'Press Enter to close. ' _"
            cmd += run + ["bash", "-c", keep]
        subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return ""
    except OSError as e:
        return f"Couldn't open a terminal: {e}"


def ssh_argv(d):
    """The ssh command for a drive: its server, port, user and key, starting in its folder (as its Act as user
    if it has one: sudo asks for the password there if it needs one)."""
    from .sshdrive import _own_folder
    port = int(d.get("port") or 22)
    argv = ["ssh", "-t", "-p", str(port)]
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in (d.get("name") or ""))
    kh = os.path.join(_own_folder(), f"known_hosts-{safe}") if not WINDOWS else ""
    if kh and os.path.exists(kh):                            # the server key Mountie pinned: that one and no other
        argv += ["-o", f"UserKnownHostsFile={kh}", "-o", "StrictHostKeyChecking=yes"]
    else:
        argv += ["-o", "StrictHostKeyChecking=accept-new"]
    if (d.get("auth") or "") == "key" and d.get("key"):
        argv += ["-i", os.path.expanduser(d["key"]), "-o", "IdentitiesOnly=yes"]
    argv.append(f"{d['user']}@{d['host']}" if d.get("user") else d["host"])
    remote, actas = (d.get("remote") or "").strip(), (d.get("actas") or "").strip()
    cd = f"cd {shlex.quote(remote)} 2>/dev/null; " if remote else ""
    if actas:                       # the folder may be that user's alone (/var/www/html): cd once switched to them
        inner = cd + "command -v bash >/dev/null && exec bash -i || exec sh -i"
        go = f"exec sudo -u {shlex.quote(actas)} sh -c {shlex.quote(inner)}"
    else:
        go = cd + "exec \"$SHELL\" -l"
    return argv + [go]
