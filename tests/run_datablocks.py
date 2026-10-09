"""The data blocks sample project (apps/datablocks): two forms and a module, on the desktop and as web pages."""
import json, os, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine
from vml.html import export_html

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = Path(tempfile.mkdtemp(prefix="vml-blocks-")).resolve()
APP = WORK / "datablocks"
shutil.copytree(os.path.join(HERE, "apps", "datablocks"), APP, ignore=shutil.ignore_patterns("*.db", "*.html"))
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

eng = Engine()
app = QApplication.instance()
app.setQuitOnLastWindowClosed(False)
said, answers = [], []
eng.cmd_InfoDialog = lambda msg, title="": said.append(str(msg))
eng.cmd_ConfirmDialog = lambda msg, title="": True
eng.cmd_PromptDialog = lambda title="", prompt="", default="": answers.pop(0)

def settle(n=8):
    for _ in range(n):
        app.processEvents()

def in_scope(form):
    win = next(x for x in eng.windows if x.name == form and x.widget.isVisible())
    nodes = eng.scopes[win.scope]
    return (lambda name: nodes[name].widget), win

def steps():
    eng.load(eng.open_project(APP / "DataBlocks.vmlproj")); settle()
    w, _ = in_scope("Report")
    items = lambda name: [w(name).item(i).text() for i in range(w(name).count())]
    combo = lambda name: [w(name).itemText(i) for i in range(w(name).count())]
    check("the first run makes the tables and some content, and the lists fill", (combo("cboRoom"), items("lstFinding")),
          (["Bathroom", "Hall", "Kitchen"], ["The extractor fan is not clearing steam", "The sealant round the bath has failed", "Tiles are loose behind the basin"]))
    w("lstFinding").setCurrentRow(1); settle()
    check("choosing a finding narrows the advice", len(items("lstAdvice")), 2)
    w("cboRoom").setCurrentIndex(2); settle()
    check("choosing another room refills the findings and clears the advice", (items("lstFinding")[0], items("lstAdvice")), ("No isolating valve under the sink", []))
    w("btnAdd").click(); settle()
    check("Add with nothing chosen asks for a finding", said[-1], "Choose a finding first.")
    w("lstFinding").setCurrentRow(1); w("lstAdvice").setCurrentRow(0); w("btnAdd").click(); settle()
    w("cboSignoff").setCurrentIndex(1); w("btnSignoff").click(); settle()
    check("the report is put together from the blocks chosen", w("txtReport").toPlainText(),
          "Kitchen: The tap drips when closed. Replace the ceramic cartridges.\n\nSurveyed by eye only. No floors were lifted and no fittings were removed.")

    seen = {}
    def maintain():
        m, win = in_scope("Maintain")
        g = m("grdBlocks")
        seen["tags"] = [m("cboTag").itemText(i) for i in range(m("cboTag").count())]
        seen["heads"] = [g.horizontalHeaderItem(i).text() for i in range(g.columnCount())]
        seen["rows"] = g.rowCount()
        seen["labels"] = [(m(f"lblF{i}").text(), m(f"txtF{i}").isVisible()) for i in range(1, 6)]
        g.setCurrentCell(0, 0); settle()
        seen["picked"] = (m("lblEditing").text(), m("txtF1").text(), m("txtF2").text())
        m("txtF3").setText("Fit a quiet fan with a run-on timer."); m("btnSave").click(); settle()
        seen["after_edit"] = (g.rowCount(), g.item(0, 3).text(), m("lblEditing").text())
        m("txtF1").setText("Hall"); m("txtF2").setText("The loft hatch has no insulation"); m("txtF3").setText("Fit an insulated hatch."); m("btnSave").click(); settle()
        seen["after_new"] = g.rowCount()
        g.setCurrentCell(seen["after_new"] - 1, 0); settle(); m("btnDelete").click(); settle()
        seen["after_delete"] = g.rowCount()
        answers[:] = ["Materials", "Item, Supplier , Price"]
        m("btnNewTag").click(); settle()
        seen["new_tag"] = (m("cboTag").currentText(), [(m(f"lblF{i}").text(), m(f"txtF{i}").isVisible()) for i in range(1, 6)], g.rowCount())
        m("btnClose").click()
    QTimer.singleShot(500, maintain)
    w("btnMaintain").click(); settle()
    check("the maintenance form lists the tags, and shows a tag's blocks under its own field names", (seen.get("tags"), seen.get("heads"), seen.get("rows")), (["Findings", "Sign-offs"], ["id", "Room", "Finding", "Advice"], 8))
    check("the boxes are labelled with the tag's fields, and the unused ones hidden", seen.get("labels"), [("Room", True), ("Finding", True), ("Advice", True), ("", False), ("", False)])
    check("choosing a row puts it in the boxes", seen.get("picked"), ("Block 3", "Bathroom", "The extractor fan is not clearing steam"))
    check("Save changes that block, and the grid shows it", seen.get("after_edit"), (8, "Fit a quiet fan with a run-on timer.", "A new block"))
    check("Save with a new block adds one; Delete removes one", (seen.get("after_new"), seen.get("after_delete")), (9, 8))
    check("a new tag has its own field names, and starts empty", seen.get("new_tag"), ("Materials", [("Item", True), ("Supplier", True), ("Price", True), ("", False), ("", False)], 0))
    w("cboRoom").setCurrentIndex(0); settle(); w("lstFinding").setCurrentRow(0); settle()
    check("back on the report form, the lists show the edited content", items("lstAdvice"), ["Fit a quiet fan with a run-on timer."])
    check("the content is in the project's own SQLite file", (APP / "blocks.db").is_file())
    eng.stop_project(); settle()

    # ---- the same two forms as web pages
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright isn't installed: skipping the web half")
        return finish()
    os.remove(APP / "blocks.db")                                   # as a fresh copy would be
    report, maint = export_html(str(APP / "report.vml")), export_html(str(APP / "maintain.vml"))
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 720, "height": 520})
        pg, logs = ctx.new_page(), []
        pg.on("console", lambda m: logs.append(m.text))
        pg.on("dialog", lambda d: d.accept(answers.pop(0)) if d.type == "prompt" else d.accept())
        pg.goto("file://" + report)
        pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=30000)
        opts = lambda page, name: page.eval_on_selector(f"#v_{name}", "e => [...e.options].map(o => o.text)")
        check("web: the first run makes the tables and content inside the page, and the lists fill", (opts(pg, "cboRoom"), len(opts(pg, "lstFinding"))), (["Bathroom", "Hall", "Kitchen"], 3))
        pg.select_option("#v_lstFinding", "The sealant round the bath has failed")
        check("web: choosing a finding narrows the advice", len(opts(pg, "lstAdvice")), 2)
        pg.select_option("#v_lstAdvice", index=0); pg.click("#v_btnAdd")
        check("web: the report is put together the same way", pg.input_value("#v_txtReport"), "Bathroom: The sealant round the bath has failed. Rake it out and reseal with sanitary silicone.")
        mp = ctx.new_page()
        mp.on("console", lambda m: logs.append(m.text))
        mp.on("dialog", lambda d: d.accept(answers.pop(0)) if d.type == "prompt" else d.accept())
        mp.goto("file://" + maint)
        mp.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=30000)
        check("web: the maintenance page shows the same blocks, under the tag's field names", (mp.locator("#v_grdBlocks th").all_inner_texts(), mp.locator("#v_grdBlocks tbody tr").count(), mp.inner_text("#v_lblF3"), mp.is_visible("#v_txtF4")),
              (["id", "Room", "Finding", "Advice"], 8, "Advice", False))
        mp.click("#v_grdBlocks tbody tr >> nth=0")
        check("web: choosing a row puts it in the boxes", (mp.inner_text("#v_lblEditing"), mp.input_value("#v_txtF1")), ("Block 3", "Bathroom"))
        mp.fill("#v_txtF3", "Fit a quiet fan."); mp.click("#v_btnSave")
        check("web: Save changes the block", mp.locator("#v_grdBlocks tbody tr >> nth=0").locator("td").nth(3).inner_text(), "Fit a quiet fan.")
        answers[:] = ["Materials", "Item, Supplier"]
        mp.click("#v_btnNewTag")
        check("web: a new tag works too", (mp.eval_on_selector("#v_cboTag", "e => e.value"), mp.inner_text("#v_lblF2"), mp.is_visible("#v_txtF3")), ("Materials", "Supplier", False))
        pg.bring_to_front(); pg.evaluate("() => window.dispatchEvent(new Event('focus'))")
        pg.select_option("#v_lstFinding", "The extractor fan is not clearing steam")
        check("web: back on the report page, the edit made on the other page is there", opts(pg, "lstAdvice"), ["Fit a quiet fan."])
        check("web: nothing went wrong in either page", [l for l in logs if "error" in l.lower() or "ItemsSource:" in l], [])
        b.close()
    finish()

def finish():
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(300, steps)
app.exec()
sys.exit(0 if all(ok) else 1)
