"""Drive the signed-in Partner Center: a list of steps (JSON) in, what the page says at the end out.
   python3 drive.py STEPS.json     steps: goto, click, fill, check, select, upload, wait, aria, url"""
import json, re, sys, time
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright

def loc(page, s):
    if "role" in s:
        return page.get_by_role(s["role"], name=re.compile(s["name"], re.I) if s.get("re") else s["name"],
                                exact=not s.get("re")).nth(s.get("nth", 0))
    if "label" in s:
        return page.get_by_label(s["label"], exact=s.get("exact", True)).nth(s.get("nth", 0))
    if "text" in s:
        return page.get_by_text(s["text"], exact=s.get("exact", True)).nth(s.get("nth", 0))
    return page.locator(s["css"]).nth(s.get("nth", 0))

def aria(page, keep=None, limit=7000):
    try:
        snap = page.locator("main, [role=main]").first.aria_snapshot(timeout=5000)
    except Exception:
        snap = page.locator("body").aria_snapshot()
    lines = snap.splitlines()
    if keep:
        lines = [l for l in lines if re.search(keep, l)]
    print("\n".join(lines)[:limit])

steps = json.load(open(sys.argv[1]))
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    for st in steps:
        k, v = next(iter(st.items()))
        try:
            if k == "goto":
                page.goto(v, wait_until="domcontentloaded"); listing.settle(page)
            elif k == "click":
                loc(page, v).click(timeout=20000, force=bool(v.get("force"))); page.wait_for_timeout(v.get("after", 2500))
            elif k == "fill":
                l = loc(page, v); l.scroll_into_view_if_needed(); l.fill(v["value"]); page.wait_for_timeout(300)
            elif k == "check":
                loc(page, v).check(timeout=10000)
            elif k == "select":
                loc(page, v).select_option(label=v["option"])
            elif k == "upload":
                with page.expect_file_chooser(timeout=15000) as fc:
                    loc(page, v).click()
                fc.value.set_files(v["files"]); page.wait_for_timeout(v.get("after", 8000))
            elif k == "setfiles":
                loc(page, v).set_input_files(v["files"]); page.wait_for_timeout(v.get("after", 8000))
            elif k == "upload_near":                           # the file input whose surroundings mention v["near"]
                idx = page.evaluate("""(near) => [...document.querySelectorAll('input[type=file]')].findIndex(e => {
                    let p = e; for (let k = 0; k < 6 && p; k++) { p = p.parentElement;
                        if (p && p.innerText && p.innerText.trim().length > 3) return p.innerText.includes(near); }
                    return false; })""", v["near"])
                if idx < 0:
                    raise RuntimeError(f"no upload box near {v['near']!r}")
                page.locator("input[type=file]").nth(idx).set_input_files(v["files"])
                page.wait_for_timeout(v.get("after", 12000))
                dlg = page.locator("[role=dialog]")
                if dlg.count() and dlg.first.is_visible():
                    print("  dialog:", dlg.first.inner_text().strip().replace("\n", " ")[:300])
                    page.get_by_role("button", name="OK").first.click()
            elif k == "eval":
                print(json.dumps(page.evaluate(v), indent=0)[:6000])
            elif k == "wait":
                page.wait_for_timeout(v)
            elif k == "url":
                print("URL:", page.url)
            elif k == "aria":
                aria(page, v.get("keep") if isinstance(v, dict) else None, v.get("limit", 7000) if isinstance(v, dict) else 7000)
            print(f"ok: {k} {json.dumps(v)[:90]}", flush=True)
        except Exception as e:
            print(f"FAILED: {k} {json.dumps(v)[:90]}: {str(e).splitlines()[0][:200]}", flush=True)
            aria(page, r"alert|button |combobox|textbox|rror", 2500)
            break
    print("URL:", page.url, "|", page.title())
    ctx.close()
