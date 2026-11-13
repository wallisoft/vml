import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright
URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/listings?languageid=95&languagecode=en-gb"
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(2000)
    info = page.evaluate("""() => [...document.querySelectorAll('input[type=file]')].map((e,i)=>{
        let ctx=''; let p=e;
        for(let k=0;k<9&&p;k++){p=p.parentElement; if(p){
            const h=p.querySelector('h1,h2,h3,h4,label,legend');
            if(h&&h.innerText&&h.innerText.trim().length>2){ctx=h.innerText.trim().slice(0,50);break;}
        }}
        const near=e.closest('section,div[class]'); 
        return {i, id:e.id||'', accept:(e.accept||'').slice(0,40), ctx, multiple:e.multiple};
    })""")
    for r in info: print(r)
    ctx.close()
