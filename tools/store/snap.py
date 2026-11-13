import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright
from PIL import Image
URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/listings?languageid=95&languagecode=en-gb"
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(2500)
    # report: screenshots count, any stray images in hero/xbox slots
    rep = page.evaluate("""()=>{const blobs=[...document.querySelectorAll('img')].filter(i=>i.src&&(i.src.startsWith('blob:')||i.src.startsWith('data:'))).length;
        const warn=[...document.querySelectorAll('[class*=error],[role=alert],[class*=warning]')].map(e=>e.innerText.trim()).filter(t=>t&&t.length<140).slice(0,5);
        return {blobImgs:blobs, warnings:warn};}""")
    print("REPORT:", rep)
    page.screenshot(path="/tmp/snap.png", full_page=True)
    im=Image.open("/tmp/snap.png").convert("RGB"); w,h=im.size
    nw=900; nh=int(h*nw/w); im.resize((nw,nh)).save("/tmp/snap.jpg", quality=66)
    print("size", w, h)
    ctx.close()
