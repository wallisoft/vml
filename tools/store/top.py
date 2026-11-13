import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright
from PIL import Image
URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/listings?languageid=95&languagecode=en-gb"
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(2500)
    page.screenshot(path="/tmp/top.png")   # viewport 1400x900
    im=Image.open("/tmp/top.png").convert("RGB"); w,h=im.size
    im.crop((120,80,760,430)).save("/tmp/top.jpg", quality=80)
    print("viewport", w, h, "crop saved")
    ctx.close()
