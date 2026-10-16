"""Styles: Class (shared @Style blocks) and Style (CSS for one control), on the desktop and the web (vml/styles.py).

    QT_QPA_PLATFORM=offscreen python3 tests/test_styles.py
(The web half needs Playwright and Chromium; without them it is skipped.)
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FORM = """@Window Styled
Title=Styles
Width=360
Height=300
Background=#F4F1FB

@Canvas c
Parent=Styled
Background=#F4F1FB

@Button btnOne
Parent=c
Canvas.Left=20
Canvas.Top=20
Width=150
Height=40
Class=pill
Content=Pill

@Button btnTwo
Parent=c
Canvas.Left=190
Canvas.Top=20
Width=150
Height=40
Class=pill go
Content=Go

@Button btnOld
Parent=c
Canvas.Left=20
Canvas.Top=80
Width=150
Height=40
Background=#4F46E5
Foreground=#FFFFFF
CornerRadius=20
Content=Old props
OnClick=SwapClass

@TextBlock lblCard
Parent=c
Canvas.Left=20
Canvas.Top=140
Width=320
Height=80
Text=A card with a shadow
Style=background: #FFFFFF; border-radius: 16px; padding: 12px; box-shadow: 0 6px 18px rgba(79,70,229,0.25); transition: all .2s

@TextBox txtName
Parent=c
Canvas.Left=20
Canvas.Top=236
Width=320
Height=40
Style=border: 2px solid #DDD6FE; border-radius: 20px; padding: 0 14px; :focus { border-color: #4F46E5 }

@Style pill
<<CSS
background: #FFFFFF; color: #4F46E5; border: 1.5px solid #DDD6FE; border-radius: 20px; font-weight: 600
:hover { background: #F5F3FF }
:pressed { background: #EDE9FE }
CSS

@Style go
<<CSS
background: linear-gradient(to right, #6366F1, #4F46E5); color: #FFFFFF; border: none
:hover { background: #4338CA }
CSS

@Script SwapClass
Interpreter=lua
<<LUA
Step = (Step or 0) + 1
if Step == 1 then Vml("SetProperty", "btnOne", "Class", "go") else Vml("SetProperty", "btnOne", "Class", "") end
LUA
"""


def test_reading_css():
    from vml import styles as st
    s = st.parse("background:#fff; border-radius:17px\n:hover { background: #F5F3FF } :pressed{background:#EDE9FE} /* c */")
    assert s[""] == [("background", "#fff"), ("border-radius", "17px")] and s["hover"] == [("background", "#F5F3FF")]
    m = st.merge({"": {"background-color": "#000", "border-radius": "6px"}}, s, st.parse("border-radius: 4px"))
    assert m[""]["border-radius"] == "4px" and list(m[""])[-1] == "border-radius"      # the latest wins
    g = st._qt_gradient("linear-gradient(to right, #6366F1, #4F46E5 80%)")
    assert g == "qlineargradient(x1:0, y1:0.5, x2:1, y2:0.5, stop:0 #6366F1, stop:0.8 #4F46E5)", g
    assert st._qt_colour("#0003") == "rgba(0,0,0,51)" and st._qt_colour("rgba(1,2,3,0.5)") == "rgba(1,2,3,128)"
    assert st.shadow("0 4px 12px rgba(0,0,0,0.2), 0 1px 2px #000") == (0.0, 4.0, 12.0, "rgba(0,0,0,51)")
    sheet, drop, out = st.qt_sheet("#b", st.merge(st.parse("color:red; transition: all .2s; box-shadow: 0 1px 2px #000")))
    assert sheet == "#b { color: red; }" and drop and out == ["transition"]


def test_desktop():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from vml.engine import Engine
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "Styled.vml"
        f.write_text(FORM)
        eng = Engine()
        eng.load(str(f), show=False)
        n = eng.nodes
        s1, s2, s3 = (n[x].widget.styleSheet() for x in ("btnOne", "btnTwo", "btnOld"))
        assert "border-radius: 20px" in s1 and "6px" not in s1, s1           # a Class's corners, not the default's
        assert "#btnOne:hover" in s1 and "#btnOne:pressed" in s1
        assert "qlineargradient" in s2 and "border: none" in s2, s2          # "pill go": go wins where they differ
        assert "border-radius: 20px" in s3 and "6px" not in s3, s3           # CornerRadius on a coloured button, at last
        fx = n["lblCard"].host.graphicsEffect()
        assert fx is not None and fx.blurRadius() == 18 and fx.yOffset() == 6
        assert "#txtName:focus" in n["txtName"].widget.styleSheet()
        eng.cmd_SetProperty("btnOne", "Class", "go")
        assert "qlineargradient" in n["btnOne"].widget.styleSheet()
        eng.cmd_SetProperty("lblCard", "Style", "background: #FEF3C7")
        assert n["lblCard"].host.graphicsEffect() is None and "#FEF3C7" in n["lblCard"].widget.styleSheet()
        eng.cmd_SetProperty("btnOne", "Shadow", "5")                          # the easy way: a level, 0..10
        fx = n["btnOne"].host.graphicsEffect()
        assert fx is not None and type(fx).__name__ == "QGraphicsDropShadowEffect" and fx.blurRadius() == 18, fx
        eng.cmd_SetProperty("btnOne", "Shadow", "0")
        assert n["btnOne"].host.graphicsEffect() is None
        eng.cmd_SetProperty("btnOne", "Opacity", "40")
        fx = n["btnOne"].host.graphicsEffect()
        assert type(fx).__name__ == "QGraphicsOpacityEffect" and abs(fx.opacity() - 0.4) < 0.01
        eng.cmd_SetProperty("btnOne", "Opacity", "100")
        assert n["btnOne"].host.graphicsEffect() is None


def test_web():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  (web: Playwright isn't installed, skipped)")
        return
    from vml.html import export_html
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "Styled.vml"
        f.write_text(FORM)
        page = export_html(str(f), str(Path(d) / "Styled.html"))
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 400, "height": 340})
            pg.goto(Path(page).as_uri())
            pg.wait_for_timeout(1500)
            cs = lambda sel, prop: pg.evaluate(f"getComputedStyle(document.querySelector('{sel}'))['{prop}']")
            assert cs("#v_btnOne", "borderTopLeftRadius") == "20px"
            assert "linear-gradient" in cs("#v_btnTwo", "backgroundImage")
            assert "rgba(79, 70, 229" in cs("#v_lblCard", "boxShadow")
            assert "0.2s" in cs("#v_lblCard", "transitionDuration")                # the web gets all of CSS
            pg.hover("#v_btnOne")
            pg.wait_for_timeout(300)
            assert cs("#v_btnOne", "backgroundColor") == "rgb(245, 243, 255)"
            pg.mouse.move(0, 0)
            pg.click("#v_btnOld")                                                     # SwapClass: Class=go
            pg.wait_for_timeout(300)
            assert "linear-gradient" in cs("#v_btnOne", "backgroundImage")
            pg.click("#v_btnOld")                                                     # then no Class at all
            pg.wait_for_timeout(300)
            assert cs("#v_btnOne", "backgroundImage") == "none"
            pg.hover("#v_btnOne")
            pg.wait_for_timeout(300)
            assert cs("#v_btnOne", "backgroundColor") != "rgb(245, 243, 255)"      # its :hover went with it
            b.close()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("  ok", name)
    print("styles: all passed")
