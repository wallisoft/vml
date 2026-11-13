import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright
from PIL import Image
URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/listings?languageid=95&languagecode=en-gb"
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(2500)
    cnt = page.evaluate("""()=>{const imgs=[...document.querySelectorAll('img')];
        return {total:imgs.length,
                data:imgs.filter(i=>i.src&&(i.src.startsWith('blob:')||i.src.startsWith('data:')||i.src.includes('screenshot'))).length,
                caps:(document.body.innerText.match(/Add image caption/g)||[]).length};}""")
    print("counts:", cnt)
    page.screenshot(path="/tmp/pc_full.png", full_page=True)
    img = Image.open("/tmp/pc_full.png").convert("RGB")
    w,h = img.size
    nw = 900; nh = int(h*nw/w)
    img.resize((nw,nh)).save("/tmp/pc_shots.jpg", quality=66)
    print("full size", w, h, "-> 900x", nh)
    ctx.close()
