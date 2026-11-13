import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright
URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/listings?languageid=95&languagecode=en-gb"
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(2500)
    info = page.evaluate("""()=>{
        const out={selects:[],comboboxes:[],error:''};
        document.querySelectorAll('select').forEach(s=>{
            out.selects.push({label:(s.getAttribute('aria-label')||s.name||''), opts:[...s.options].map(o=>o.text).slice(0,12), val:s.value});
        });
        document.querySelectorAll('[role=combobox]').forEach(c=>{
            out.comboboxes.push({label:(c.getAttribute('aria-label')||c.innerText||'').slice(0,40), val:(c.value||c.innerText||'').slice(0,40)});
        });
        const err=[...document.querySelectorAll('[class*=error],[role=alert]')].map(e=>e.innerText.trim()).filter(t=>t&&t.length<160);
        out.error=err.slice(0,4);
        return out;
    }""")
    import json; print(json.dumps(info, indent=1))
    ctx.close()
