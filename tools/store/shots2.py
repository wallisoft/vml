import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright
URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/listings?languageid=95&languagecode=en-gb"
FOLDER = "/home/steve/kato-submit"
SHOTS = ["shot1.png", "shot2.png", "shot3.png"]
def log(*a): print(*a, flush=True)

def shot_idx(page):
    return page.evaluate("""()=>[...document.querySelectorAll('input[type=file]')].findIndex(e=>{
        let p=e; for(let k=0;k<12&&p;k++){p=p.parentElement; if(p&&p.innerText){
        const t=p.innerText; if(t.includes('Max upload')||t.includes('3840 x 2160')) return true;}}
        return false;})""")

with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(2000)
    for s in SHOTS:
        idx = shot_idx(page)
        if idx < 0: log("screenshot input not found for", s); break
        try:
            page.locator("input[type=file]").nth(idx).set_input_files([f"{FOLDER}/{s}"])
            page.wait_for_timeout(9000)
            dlg = page.locator("[role=dialog]")
            if dlg.count() and dlg.first.is_visible():
                log("  dialog:", dlg.first.inner_text()[:100].replace(chr(10)," "))
                try: page.get_by_role("button", name="OK").first.click(); page.wait_for_timeout(1500)
                except Exception: pass
            log("uploaded", s, "(idx", idx, ")")
        except Exception as e:
            log("FAIL", s, str(e).splitlines()[0][:90])
    page.wait_for_timeout(1500)
    # count uploaded screenshots: caption boxes / blob thumbnails
    cnt = page.evaluate("""()=>{const blobs=[...document.querySelectorAll('img')].filter(i=>i.src&&i.src.startsWith('blob:')).length;
        const caps=document.body.innerText.split('Add image caption').length-1; return {blobs, capSlots:caps};}""")
    log("after upload:", cnt)
    b = page.get_by_role("button", name="Save", exact=True)
    if b.count() and b.first.is_enabled():
        b.first.scroll_into_view_if_needed(); b.first.click(timeout=10000); page.wait_for_timeout(9000)
        log("saved. url:", page.url)
    else:
        log("Save not enabled")
    ctx.close()
