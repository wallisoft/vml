"""
Ignore lists, as a .gitignore writes them: what to leave out of a view of some files. Used by the file boxes' Hide
box and by Mountie's folder drives.

    *.log           anything ending .log, anywhere
    build/          folders called build (a trailing / means folders only)
    /notes.txt      only at the top
    docs/*.pdf      a pattern with a / in it is matched against the path from the top
    !keep.log       never leave this one out, whatever came before (the last pattern that matches wins)
    # a comment     ignored, as are blank lines

Patterns may also be separated by spaces or commas on one line (the Hide box is one line).
"""
import re
from fnmatch import fnmatchcase


def patterns(text):
    """The patterns in an ignore list."""
    out = []
    for line in str(text or "").splitlines():
        line = re.sub(r"(^|\s)#.*", "", line)
        out += [p for p in re.split(r"[\s,]+", line) if p]
    return out


def _matches(p, path, name, is_dir):
    dir_only = p.endswith("/")
    p = p.rstrip("/")
    if dir_only and not is_dir:
        return False
    if not p:
        return is_dir                                          # "*/" or "/" alone: every folder
    if p.startswith("/") or "/" in p:                          # a path from the top
        p = p.lstrip("/")
        return fnmatchcase(path, p) or fnmatchcase(path, p + "/*")
    return fnmatchcase(name, p)


def hidden(pats, path, is_dir):
    """Is this left out? path is from the top of the view ("a/b.txt" or "/a/b.txt"); pats from patterns()."""
    path = str(path).strip("/")
    name = path.rsplit("/", 1)[-1]
    out = False
    for p in pats:
        keep = p.startswith("!")
        if _matches(p[1:] if keep else p, path, name, is_dir):
            out = not keep
    return out


def hidden_by(text, name, is_dir):
    """The Hide box's question about one name in the folder being looked at."""
    return hidden(patterns(text), name, is_dir)


# Ready-made ignore lists: what people usually want left out. (name, what it covers, patterns)
USUAL = (
    ("folders", "Folders", "*/"),
    ("hidden", "Hidden files and folders", ".*"),
    ("partial", "Unfinished downloads", "*.part *.crdownload *.download *.tmp *.partial"),
    ("installers", "Installers", "*.deb *.rpm *.AppImage *.appimage *.snap *.flatpak *.exe *.msi *.msix *.dmg *.pkg"),
    ("archives", "Archives", "*.zip *.tar *.tar.gz *.tgz *.tar.xz *.txz *.tar.bz2 *.7z *.rar *.gz *.xz *.bz2 *.zst"),
    ("images", "Disk images", "*.iso *.img *.vhd *.vhdx *.vmdk *.qcow2 *.vdi *.raw"),
    ("video", "Videos", "*.mp4 *.mkv *.avi *.mov *.webm *.m4v *.wmv"),
    ("music", "Music", "*.mp3 *.flac *.ogg *.m4a *.wav *.aac *.opus"),
    ("pictures", "Pictures", "*.jpg *.jpeg *.png *.gif *.webp *.heic *.bmp *.tif *.tiff *.svg"),
    ("documents", "Documents", "*.pdf *.doc *.docx *.odt *.xls *.xlsx *.ods *.ppt *.pptx *.odp *.txt *.md *.rtf"),
    ("code", "Code clutter", "node_modules/ __pycache__/ *.pyc .venv/ venv/ dist/ build/ target/ .git/ *.o *.class"),
    ("junk", "System junk", "Thumbs.db desktop.ini .DS_Store *.lnk *~ *.bak *.swp"),
)
