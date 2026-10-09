"""Timer and ProgressBar in a browser: the same form as on the desktop."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright isn't installed: skipping\n0/0 passed")
    raise SystemExit(0)
from vml.html import export_html

WORK = tempfile.mkdtemp(prefix="vml-weblive-")
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

form = os.path.join(WORK, "live.vml")
with open(form, "w") as f:
    f.write("""@Window Live
Title=Live
Width=320
Height=220

@Canvas c
Parent=Live

@Timer tmr
Parent=c
Interval=30
OnTick=Tick

@Timer tmrOff
Parent=c
Interval=30
IsEnabled=false
OnTick=TickOff

@ProgressBar bar
Parent=c
Canvas.Left=10
Canvas.Top=60
Width=200
Height=18
Value=25
ShowText=true

@ProgressBar blocks
Parent=c
Canvas.Left=10
Canvas.Top=90
Width=200
Height=18
Value=50
BarStyle=Blocks
Foreground=#16A34A

@ProgressBar busy
Parent=c
Canvas.Left=10
Canvas.Top=120
Width=200
Height=6
BarStyle=Thin
IsIndeterminate=true

@TextBlock lbl
Parent=c
Canvas.Left=10
Canvas.Top=150
Text=0

@Button btnGo
Parent=c
Canvas.Left=10
Canvas.Top=175
Content=Go
OnClick=Go

@Script Tick
Interpreter=lua
<<LUA
local n = (tonumber(Vml("GetProperty", "lbl", "Text")) or 0) + 1
Vml("SetProperty", "lbl", "Text", tostring(n))
Vml("SetProperty", "bar", "Value", tostring(math.min(100, n * 20)))
if n >= 5 then Vml("SetProperty", "tmr", "IsEnabled", "false") end
LUA

@Script TickOff
Interpreter=lua
<<LUA
Vml("SetProperty", "btnGo", "Content", "ticked")
LUA

@Script Go
Interpreter=lua
<<LUA
Vml("SetProperty", "lbl", "Text", "0")
Vml("SetProperty", "tmr", "Interval", "10")
Vml("SetProperty", "tmr", "IsEnabled", "true")
LUA
""")
out = export_html(form, os.path.join(WORK, "live.html"))
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 320, "height": 220})
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto("file://" + str(out))
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    pg.wait_for_function("document.querySelector('#v_lbl').textContent === '5'", timeout=5000)
    pg.wait_for_timeout(200)
    check("web: a Timer ticks every Interval and stops when turned off", pg.inner_text("#v_lbl"), "5")
    check("web: one that starts off never ticks", pg.inner_text("#v_btnGo"), "Go")
    check("web: a Timer isn't seen", pg.is_visible("#v_tmr"), False)
    width = lambda sel: round(pg.eval_on_selector(sel + " > i", "e => e.getBoundingClientRect().width"))
    check("web: the bar follows its Value, with the percentage written on it", (width("#v_bar"), pg.inner_text("#v_bar > b"), pg.evaluate("vml.Vml('GetProperty', 'bar', 'Value')")), (200, "100%", "100"))
    pg.evaluate("vml.Vml('SetProperty', 'bar', 'Value', '25')")
    check("web: and can be set", (width("#v_bar"), pg.inner_text("#v_bar > b")), (50, "25%"))
    w = width("#v_blocks")
    check("web: Blocks lights whole blocks only, in its own colour", (90 <= w <= 110, pg.eval_on_selector("#v_blocks", "e => getComputedStyle(e).getPropertyValue('--bar').trim().toLowerCase()")), (True, "#16a34a"))
    x0 = pg.eval_on_selector("#v_busy > i", "e => e.getBoundingClientRect().x"); pg.wait_for_timeout(400)
    x1 = pg.eval_on_selector("#v_busy > i", "e => e.getBoundingClientRect().x")
    check("web: IsIndeterminate sweeps", x0 != x1)
    pg.click("#v_btnGo")
    pg.wait_for_function("document.querySelector('#v_lbl').textContent === '5'", timeout=5000)
    check("web: a script can turn a Timer back on, with a new Interval", pg.inner_text("#v_lbl"), "5")
    check("web: nothing went wrong in the page", errors, [])
    b.close()
print(f"\n{sum(ok)}/{len(ok)} passed")
sys.exit(0 if all(ok) else 1)
