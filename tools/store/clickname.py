import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright
from PIL import Image
URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/listings?languageid=95&languagecode=en-gb"
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(2500)
    page.mouse.click(500, 246); page.wait_for_timeout(1800)
    opts = page.evaluate("""()=>[...document.querySelectorAll('[role=option],.ms-Dropdown-item,[role=menuitem],li[role]')].map(o=>o.innerText.trim()).filter(t=>t&&t.length<60).slice(0,25)""")
    print("OPTIONS:", opts)
    page.screenshot(path="/tmp/cn.png")
    im=Image.open("/tmp/cn.png").convert("RGB"); 
    im.crop((120,80,780,560)).save("/tmp/cn.jpg", quality=80)
    print("saved")
    ctx.close()
