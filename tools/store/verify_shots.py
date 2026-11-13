import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright
from PIL import Image
URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/listings?languageid=95&languagecode=en-gb"
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(2500)
    # scroll to screenshots section
    idx = page.evaluate("""()=>[...document.querySelectorAll('input[type=file]')].findIndex(e=>{let p=e;
        for(let k=0;k<12&&p;k++){p=p.parentElement; if(p&&p.innerText&&(p.innerText.includes('Max upload')||p.innerText.includes('3840 x 2160'))) return true;} return false;})""")
    print("screenshot input idx:", idx)
    if idx>=0:
        page.locator("input[type=file]").nth(idx).scroll_into_view_if_needed()
        page.wait_for_timeout(1200)
    # count thumbnails more broadly
    cnt = page.evaluate("""()=>{const imgs=[...document.querySelectorAll('img')];
        return {total:imgs.length, data:imgs.filter(i=>i.src&&(i.src.startsWith('blob:')||i.src.startsWith('data:')||i.src.includes('screenshot'))).length,
                caps:(document.body.innerText.match(/Add image caption/g)||[]).length,
                thumbs:[...document.querySelectorAll('[class*=thumbnail],[class*=Thumbnail],[class*=preview],[class*=image-card]')].length};}""")
    print("counts:", cnt)
    page.screenshot(path="/tmp/pc_shots_full.png")
    img = Image.open("/tmp/pc_shots_full.png").convert("RGB")
    w,h = img.size
    nw = 1000; nh = int(h*nw/w)
    img.resize((nw,nh)).save("/tmp/pc_shots.jpg", quality=68)
    print("shot size", w, h)
    ctx.close()
