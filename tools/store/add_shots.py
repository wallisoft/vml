import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright
URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/listings?languageid=95&languagecode=en-gb"
FOLDER = "/home/steve/kato-submit"
def log(*a): print(*a, flush=True)
def shot_input_idx(page):
    return page.evaluate("""()=>[...document.querySelectorAll('input[type=file]')].findIndex(e=>{let p=e;
        for(let k=0;k<12&&p;k++){p=p.parentElement; if(p&&p.innerText&&(p.innerText.includes('Max upload')||p.innerText.includes('3840 x 2160'))) return true;} return false;})""")
def shots_count(page):
    return page.evaluate("""()=>[...document.querySelectorAll('img')].filter(i=>i.src&&(i.src.startsWith('blob:')||i.src.startsWith('data:'))).length""")
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(2500)
    start = shots_count(page); log("start screenshots:", start)
    for s in ["shot2.png", "shot3.png"]:
        before = shots_count(page)
        idx = shot_input_idx(page)
        if idx < 0: log("no screenshot input for", s); break
        page.locator("input[type=file]").nth(idx).set_input_files([f"{FOLDER}/{s}"])
        ok=False
        for _ in range(14):
            page.wait_for_timeout(1500)
            dlg = page.locator("[role=dialog]")
            if dlg.count() and dlg.first.is_visible():
                try: page.get_by_role("button", name="OK").first.click()
                except Exception: pass
            if shots_count(page) > before: ok=True; break
        log(s, "added:", ok, "count now:", shots_count(page))
    final = shots_count(page); log("final screenshots:", final)
    b = page.get_by_role("button", name="Save", exact=True)
    if b.count() and b.first.is_enabled():
        b.first.click(timeout=10000); page.wait_for_timeout(9000); log("saved", page.url)
    else: log("Save not enabled")
    ctx.close()
