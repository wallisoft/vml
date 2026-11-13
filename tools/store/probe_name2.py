import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright
URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/listings?languageid=95&languagecode=en-gb"
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(2500)
    # dump anything with role listbox/combobox/button near top, and the error text
    info = page.evaluate("""()=>{
      const roles=[];
      document.querySelectorAll('[role=listbox],[role=combobox],[role=button],.ms-Dropdown,[aria-haspopup]').forEach(e=>{
        const t=(e.getAttribute('aria-label')||e.innerText||e.getAttribute('title')||'').trim().replace(/\\s+/g,' ').slice(0,45);
        const r=e.getBoundingClientRect();
        if(r.top<520 && t) roles.push({tag:e.tagName, role:e.getAttribute('role')||'', cls:(e.className||'').toString().slice(0,30), t, y:Math.round(r.top)});
      });
      // the red reservation message
      const msg=[...document.querySelectorAll('*')].map(e=>e.childElementCount===0?e.innerText:'').filter(t=>t&&/reserv/i.test(t)).slice(0,3);
      return {roles:roles.slice(0,20), msg};
    }""")
    import json; print(json.dumps(info, indent=1))
    ctx.close()
