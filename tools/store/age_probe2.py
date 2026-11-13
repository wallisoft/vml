
import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright

URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/ageratings/edit"
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(2000)
    page.get_by_text("All Other App Types", exact=False).first.click(); page.wait_for_timeout(3500)
    for i in range(page.get_by_role("radiogroup").count()):
        no = page.get_by_role("radiogroup").nth(i).get_by_text("No", exact=True)
        if no.count():
            try: no.first.click(); page.wait_for_timeout(350)
            except Exception: pass
    page.wait_for_timeout(1500)
    page.mouse.wheel(0, 4000); page.wait_for_timeout(1200)
    # dump every actionable control with visibility
    ctrls = page.evaluate("""() => {
      const sel = \"button, input[type=submit], input[type=button], a[role=button], [role=button]\";
      return [...document.querySelectorAll(sel)].map(e=>{
        const r=e.getBoundingClientRect(); const cs=getComputedStyle(e);
        return {t:(e.innerText||e.value||e.getAttribute(\"aria-label\")||\"\").trim().slice(0,28),
                vis: cs.display!=\"none\" && cs.visibility!=\"hidden\" && r.width>0,
                dis: e.disabled||e.getAttribute(\"aria-disabled\")==\"true\"};
      }).filter(x=>x.t && !x.t.startsWith(\"Learn more\"));
    }""")
    print("CONTROLS:", ctrls)
    ctx.close()
