import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright
from PIL import Image
URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/listings?languageid=95&languagecode=en-gb"
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(2500)
    # locate the control just after the "Product name" label
    box = page.evaluate("""()=>{
      const labels=[...document.querySelectorAll('*')].filter(e=>e.childElementCount===0 && /^Product name/i.test((e.innerText||'').trim()));
      if(!labels.length) return {found:false};
      let n=labels[0];
      // walk forward to the first interactive control
      let host=n.closest('div');
      let ctrl = host && host.parentElement ? host.parentElement.querySelector('[role=combobox],[role=listbox],select,input,[class*=Dropdown],[class*=dropdown],button') : null;
      if(!ctrl) return {found:true, ctrl:false, hostText:(host&&host.parentElement&&host.parentElement.innerText||'').slice(0,80)};
      const r=ctrl.getBoundingClientRect();
      return {found:true, ctrl:true, tag:ctrl.tagName, role:ctrl.getAttribute('role')||'', cls:(ctrl.className||'').toString().slice(0,40), x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2), w:Math.round(r.width)};
    }""")
    import json; print("CTRL:", json.dumps(box))
    if box.get("ctrl"):
        try:
            page.mouse.click(box["x"], box["y"]); page.wait_for_timeout(1800)
        except Exception as e: print("click err", str(e)[:80])
        opts = page.evaluate("""()=>[...document.querySelectorAll('[role=option],.ms-Dropdown-item,[role=listbox] [role=option],li')].map(o=>o.innerText.trim()).filter(t=>t&&t.length<50).slice(0,20)""")
        print("OPTIONS:", opts)
        page.screenshot(path="/tmp/nm.png")
        im=Image.open("/tmp/nm.png").convert("RGB"); w,h=im.size
        im.crop((0,0,min(w,900),min(h,700))).save("/tmp/nm.jpg", quality=70)
        print("cropped shot saved", w, h)
    ctx.close()
