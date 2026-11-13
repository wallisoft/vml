import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright
from PIL import Image
URL="https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067"
def log(*a): print(*a, flush=True)
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(3000)
    log("on:", page.url)
    btn = page.get_by_role("button", name="Submit for certification")
    if not (btn.count() and btn.first.is_enabled()):
        log("Submit button not found/enabled; buttons:", page.evaluate("()=>[...document.querySelectorAll('button')].map(b=>b.innerText.trim()).filter(t=>t&&t.length<40).slice(0,15)"))
        page.screenshot(path="/tmp/sub.png"); ctx.close(); sys.exit(1)
    btn.first.click(); log("clicked Submit for certification")
    page.wait_for_timeout(6000)
    # secondary confirm if any
    for nm in ["Submit","Confirm","Yes","OK"]:
        b2 = page.get_by_role("button", name=nm, exact=True)
        if b2.count() and b2.first.is_visible() and b2.first.is_enabled():
            try: b2.first.click(); log("confirmed via", nm); page.wait_for_timeout(5000); break
            except Exception: pass
    page.wait_for_timeout(8000)
    log("url now:", page.url)
    body = page.locator("body").inner_text()
    import re
    for kw in ["certification","Pre-processing","Preprocessing","In review","In the Store","submitted","progress","In draft"]:
        if kw.lower() in body.lower():
            m = re.search(r'.{0,40}'+re.escape(kw)+r'.{0,40}', body, re.I)
            log("status hint:", (m.group(0) if m else kw).replace(chr(10)," ").strip()[:90])
    page.screenshot(path="/tmp/sub.png", full_page=True)
    im=Image.open("/tmp/sub.png").convert("RGB"); w,h=im.size
    nw=850; im.resize((nw,int(h*nw/w))).save("/tmp/sub.jpg", quality=72)
    log("done; shot", w, h)
    ctx.close()
