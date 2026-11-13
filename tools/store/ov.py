import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright
from PIL import Image
URL="https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067"
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(3000)
    print("url:", page.url)
    # section statuses + warnings
    info = page.evaluate("""()=>{
      const rows=[...document.querySelectorAll('a[href*=submissions]')].map(a=>{
        const t=(a.innerText||'').trim().replace(/\\s+/g,' ');
        return t;}).filter(t=>t && t.length<60);
      const warn=[...document.querySelectorAll('[class*=warning],[class*=Warning],[role=alert],[class*=error]')].map(e=>e.innerText.trim()).filter(t=>t&&t.length<160);
      const body=document.body.innerText;
      const blur = (body.match(/blur[^.]*\\.?/i)||[''])[0];
      const sub = !!document.querySelector('button')&&[...document.querySelectorAll('button')].some(b=>/submit/i.test(b.innerText));
      return {rows:[...new Set(rows)].slice(0,20), warn:warn.slice(0,6), blur, hasSubmit:sub};
    }""")
    import json; print(json.dumps(info, indent=1))
    page.screenshot(path="/tmp/ov.png", full_page=True)
    im=Image.open("/tmp/ov.png").convert("RGB"); w,h=im.size
    nw=850; im.resize((nw,int(h*nw/w))).save("/tmp/ov.jpg", quality=70)
    print("shot", w, h)
    ctx.close()
