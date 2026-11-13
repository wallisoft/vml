import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright
URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/listings?languageid=95&languagecode=en-gb"
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(2000)
    for idx in [0,1,2,5,6,7,8]:
        t = page.evaluate("""(idx)=>{const e=[...document.querySelectorAll('input[type=file]')][idx];
            let p=e; for(let k=0;k<12&&p;k++){p=p.parentElement; if(p&&p.innerText&&p.innerText.trim().length>15){
            return p.innerText.trim().replace(/\\s+/g,' ').slice(0,140);}} return '(none)';}""", idx)
        print(idx, '=>', t)
    ctx.close()
