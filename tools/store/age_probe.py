
import sys, time
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright

URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/ageratings/edit"
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(2000)
    page.get_by_text("All Other App Types", exact=False).first.click(); page.wait_for_timeout(3500)
    groups = page.get_by_role("radiogroup")
    for i in range(groups.count()):
        no = groups.nth(i).get_by_text("No", exact=True)
        if no.count():
            try: no.first.click(); page.wait_for_timeout(350)
            except Exception: pass
    # physical-media / ratings-board question (may be outside a radiogroup): click its No
    page.wait_for_timeout(1000)
    # enumerate ALL buttons with enabled/disabled + text
    btns = page.evaluate("""() => [...document.querySelectorAll(\"button\")].map(b=>({t:(b.innerText||b.getAttribute(\"aria-label\")||\"\").trim().slice(0,30), d:b.disabled||b.getAttribute(\"aria-disabled\")==\"true\"})).filter(x=>x.t)""")
    print("buttons:", btns)
    # any unanswered radiogroup?
    unans = page.evaluate("""() => [...document.querySelectorAll(\"[role=radiogroup]\")].map((g,i)=>({i,has:[...g.querySelectorAll(\"input[type=radio]\")].some(x=>x.checked)})).filter(x=>!x.has)""")
    print("unanswered groups:", unans)
    ctx.close()
