"""Opening a form in the designer and saving it again must keep every control, however deep, and every script.

(Saving used to walk only into Frames, so a canvas inside a canvas lost everything in it, with the scripts its buttons
used. Preview and Android export are made from that saved copy, so the app on the phone was missing its sign-in page.)

    QT_QPA_PLATFORM=offscreen python3 tests/test_designer_roundtrip.py      (or: python3 -m pytest tests)
"""
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FORM = """@Window Pages
Width=360
Height=400

@MenuTheme theme
Parent=Pages
Background=#0F766E

@Canvas c
Parent=Pages
Background=#FFFFFF

@TextBlock lblTitle
Parent=c
Canvas.Left=10
Canvas.Top=10
Text=Two pages

@Canvas pgOne
Parent=c
Canvas.Left=0
Canvas.Top=50
Width=360
Height=300

@TextBox txtName
Parent=pgOne
Canvas.Left=10
Canvas.Top=0
Width=200
Height=30

@Button btnGo
Parent=pgOne
Canvas.Left=10
Canvas.Top=40
Width=100
Height=30
Content=Go
OnClick=DoGo

@Canvas pgTwo
Parent=c
Canvas.Left=0
Canvas.Top=50
Width=360
Height=300
IsVisible=false

@Frame frInner
Parent=pgTwo
Canvas.Left=10
Canvas.Top=10
Width=300
Height=200

@Button btnBack
Parent=frInner
Canvas.Left=10
Canvas.Top=10
Width=100
Height=30
Content=Back
OnClick=DoBack

@Script DoGo
Interpreter=lua
<<LUA
Vml("SetProperty", "pgOne", "IsVisible", "false")
Vml("SetProperty", "pgTwo", "IsVisible", "true")
LUA

@Script DoBack
Interpreter=lua
<<LUA
Vml("SetProperty", "pgTwo", "IsVisible", "false")
Vml("SetProperty", "pgOne", "IsVisible", "true")
LUA
"""


def controls(text):
    """Every control below the form's own canvas (which the designer names after the form), as (type, name)."""
    top = {"c", "PagesCanvas"}
    return sorted((t, n) for t, n in re.findall(r"(?m)^@(\w+) (\w+)$", text)
                  if t not in ("Script", "Window", "MenuTheme") and not (t == "Canvas" and n in top))


def test_nested_containers_survive_designer_save():
    from PySide6.QtCore import QTimer
    from vml.engine import Engine
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "host.vml").write_text("@Window W\nWidth=800\nHeight=900\n\n@DesignSurface Surface\nParent=W\n")
        (d / "pages.vml").write_text(FORM)
        e = Engine(None)
        e.load(str(d / "host.vml"))
        done = {}

        def go():
            try:
                e.cmd_ImportVml(str(d / "pages.vml"), "Surface")
                e.cmd_ExportVml("Surface", str(d / "once.vml"))
                e.cmd_ImportVml(str(d / "once.vml"), "Surface")
                e.cmd_ExportVml("Surface", str(d / "twice.vml"))
            except Exception as exc:                    # (reported below, not lost inside the event loop)
                done["error"] = exc
            e.app.quit()
        QTimer.singleShot(200, go)
        e.run()
        assert "error" not in done, done.get("error")
        once, twice = (d / "once.vml").read_text(), (d / "twice.vml").read_text()

    want = [(t, n) for t, n in controls(FORM)]
    got = [(t, n) for t, n in controls(once)]
    assert got == want, f"controls lost or changed on saving:\n  want {want}\n  got  {got}"
    for name in ("DoGo", "DoBack"):
        assert f"@Script {name}" in once, f"script {name} lost on saving"
    assert "@MenuTheme" in once, "the MenuTheme was lost on saving a form without a menu bar"
    assert re.search(r"(?m)^@TextBox txtName\nParent=pgOne$", once), "txtName no longer inside pgOne"
    assert re.search(r"(?m)^@Button btnBack\nParent=frInner$", once), "btnBack no longer inside frInner"
    assert re.search(r"(?m)^@Canvas pgTwo\nParent=\w+\n(?:.+\n)*?IsVisible=false$", once), "pgTwo no longer starts hidden"
    assert controls(twice) == controls(once), "a second save changed the form again"




def test_stacked_pages_are_layers_in_the_designer():
    """Pages stacked in one place show one at a time while designing; choosing a control on a hidden page brings
    that page forward; and none of it changes what's saved."""
    from PySide6.QtCore import QTimer
    from vml.engine import Engine
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "host.vml").write_text("@Window W\nWidth=800\nHeight=900\n\n@DesignSurface Surface\nParent=W\n")
        (d / "pages.vml").write_text(FORM)
        e = Engine(None)
        e.load(str(d / "host.vml"))
        seen = {}

        def go():
            try:
                e.cmd_ImportVml(str(d / "pages.vml"), "Surface")
                v = e.find("Surface").widget
                seen["stacks"] = [[n.name for n in g] for g in v.layers_now]
                seen["front"] = dict(v.layer_front)
                seen["one shown"] = e.find("pgOne").host.isVisible() and not e.find("pgTwo").host.isVisible()
                v.select("btnBack")                     # inside frInner, inside the hidden pgTwo
                seen["after"] = dict(v.layer_front)
                e.cmd_ExportVml("Surface", str(d / "saved.vml"))
                seen["saved"] = (d / "saved.vml").read_text()
            except Exception as exc:
                seen["error"] = exc
            e.app.quit()
        QTimer.singleShot(200, go)
        e.run()
    assert "error" not in seen, seen.get("error")
    assert seen["stacks"] == [["pgOne", "pgTwo"]], seen["stacks"]
    assert seen["front"] == {("pgOne", "pgTwo"): "pgOne"} and seen["one shown"], seen
    assert seen["after"] == {("pgOne", "pgTwo"): "pgTwo"}, "choosing btnBack didn't bring pgTwo forward"
    assert re.search(r"(?m)^@Canvas pgTwo\nParent=\w+\n(?:.+\n)*?IsVisible=false$", seen["saved"]), "pgTwo's own IsVisible changed"
    assert "IsVisible=false" not in re.search(r"(?ms)^@Canvas pgOne\n.*?(?=^@)", seen["saved"]).group(0), "pgOne saved as hidden"


if __name__ == "__main__":
    test_nested_containers_survive_designer_save()
    print("ok: nested containers survive the designer's save")
    test_stacked_pages_are_layers_in_the_designer()
    print("ok: stacked pages are layers in the designer")
