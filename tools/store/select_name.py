import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright
from PIL import Image
URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/listings?languageid=95&languagecode=en-gb"
def log(*a): print(*a, flush=True)
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(2500)
    page.mouse.click(500, 246); page.wait_for_timeout(1500)
    picked=False
    opt = page.get_by_role("option", name="kato kvm")
    if opt.count():
        opt.first.click(); picked="role=option"
    else:
        t = page.get_by_text("kato kvm", exact=True)
        if t.count(): t.first.click(); picked="text"
    page.wait_for_timeout(1500)
    # verify
    val = page.evaluate("""()=>{const e=[...document.querySelectorAll('*')].filter(x=>x.childElementCount===0 && /no longer reserved/i.test(x.innerText||'')); 
        return {err: e.length>0};}""")
    log("picked:", picked, "error still present:", val["err"])
    # Save
    b = page.get_by_role("button", name="Save", exact=True)
    if b.count() and b.first.is_enabled():
        b.first.click(timeout=10000); page.wait_for_timeout(9000)
        log("saved. url:", page.url)
    else:
        log("Save not enabled/found")
    ctx.close()
