"""Why isn't the designer's theme changing on this computer? Run it and paste what it prints.

    python3 tests/diag_themes.py

It changes nothing of yours: it works on a copy of your settings. First it tries the theme with no screen at all
(the same check the tests make), then on your real screen for a second, and says what colour the menu bar was
before and after in each case."""
import json, os, shutil, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

if len(sys.argv) > 1 and sys.argv[1] == "--try":
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from vml import engine as E
    eng = E.Engine()
    eng.cmd_InfoDialog = lambda *a, **k: None
    eng.load(os.path.join(HERE, "designer", "designer.vml"))
    app = QApplication.instance()
    out = {"platform": app.platformName(), "style": app.style().objectName(), "lua_paths": eng.lua_paths}
    def spin(n=12):
        for _ in range(n):
            app.processEvents()
    def bar():
        w = eng.windows[0].widget
        c = w.grab().toImage().pixelColor(min(300, w.width() - 5), 12)
        return "#%02X%02X%02X" % (c.red(), c.green(), c.blue())
    def go():
        spin()
        theme = eng.find("Theme")
        out["theme_control"] = None if theme is None else theme.type.name
        out["menu_items"] = [n for n in ("SetThemeClassic", "SetThemeForest") if eng.find(n) is not None]
        out["start_pref"] = eng.vml("GetPreference", "theme", "(none)")
        out["bar_before"] = bar()
        want = "Plum" if out["start_pref"] == "Forest" else "Forest"
        out["asked_for"] = want
        item = eng.find("SetTheme" + want)
        try:
            item.action.trigger()                       # exactly what a click on Settings, Theme, and its name does
            out["clicked"] = "the menu item"
        except Exception as exc:
            out["clicked"] = "couldn't click the item (%r): ran the script instead" % (exc,)
            eng.run_script("SetTheme", want)
        spin()
        out["pref_after"] = eng.vml("GetPreference", "theme", "(none)")
        out["theme_background_after"] = None if theme is None else str(theme.props.get("Background"))
        out["bar_after"] = bar()
        out["status"] = eng.vml("GetStatusText") if hasattr(eng, "cmd_GetStatusText") else ""
        print("RESULT " + json.dumps(out))
        app.quit()
    QTimer.singleShot(700, go)
    QTimer.singleShot(15000, app.quit)
    sys.exit(eng.run())

real = os.path.expanduser("~/.vml")
print("Visualised from:", HERE)
print("~/.vml holds:", sorted(os.listdir(real)) if os.path.isdir(real) else "nothing")
for sub in ("system/lua", "designer", "designer/modules", "system"):
    d = os.path.join(real, sub)
    if os.path.isdir(d):
        print(f"  ~/.vml/{sub}:", sorted(os.listdir(d))[:30])
work = tempfile.mkdtemp(prefix="vml-diag-")
if os.path.exists(os.path.join(real, "prefs.json")):
    try:
        print("your theme setting:", json.load(open(os.path.join(real, "prefs.json"))).get("theme", "(none)"))
    except Exception as exc:
        print("your prefs.json can't be read:", exc)
for label, env in (("with no screen", {"QT_QPA_PLATFORM": "offscreen"}), ("on your screen", {})):
    prefs = os.path.join(work, label.replace(" ", "-") + ".json")          # a fresh copy of your settings each time
    if os.path.exists(os.path.join(real, "prefs.json")):
        shutil.copy(os.path.join(real, "prefs.json"), prefs)
    e = dict(os.environ, VML_PREFS=prefs, **env)
    try:
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--try"], env=e, capture_output=True, text=True, timeout=40)
        line = next((l for l in r.stdout.splitlines() if l.startswith("RESULT ")), None)
        if line is None:
            print(f"\n{label}: it didn't finish. The last it said:\n  " + "\n  ".join((r.stderr or r.stdout).strip().splitlines()[-6:]))
            continue
        got = json.loads(line[7:])
        changed = got["bar_before"] != got["bar_after"]
        print(f"\n{label} ({got['platform']}, style {got['style']}):")
        print(f"  theme control: {got['theme_control']}   menu items found: {got['menu_items']}   clicked: {got['clicked']} ({got['asked_for']})")
        print(f"  setting: {got['start_pref']} -> {got['pref_after']}   theme's Background now: {got['theme_background_after']}")
        print(f"  menu bar colour: {got['bar_before']} -> {got['bar_after']}   {'CHANGED' if changed else 'DID NOT CHANGE'}")
        if label == "with no screen":
            print("  lua is looked for in:", got["lua_paths"])
    except subprocess.TimeoutExpired:
        print(f"\n{label}: it took too long and was stopped.")
shutil.rmtree(work, ignore_errors=True)
