
import sys, time
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright

URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/ageratings/edit"
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(2000)
    # 1) App type: All Other App Types
    page.get_by_text("All Other App Types", exact=False).first.click()
    page.wait_for_timeout(3500)
    # 2) every Yes/No question -> No
    groups = page.get_by_role("radiogroup")
    n = groups.count()
    done = 0
    for i in range(n):
        g = groups.nth(i)
        no = g.get_by_text("No", exact=True)
        if no.count():
            try:
                no.first.click(); done += 1; page.wait_for_timeout(400)
            except Exception as e:
                print("  grp", i, "No click failed:", str(e).splitlines()[0][:80])
    print("radiogroups:", n, "No-clicked:", done)
    # also any stray physical-media Yes/No not in a radiogroup
    page.wait_for_timeout(1500)
    # verify
    state = page.evaluate("""() => [...document.querySelectorAll(\"[role=radiogroup]\")].map(g=>{const r=[...g.querySelectorAll(\"input[type=radio]\")].find(x=>x.checked); const l=r?(r.closest(\"label\")||r.parentElement):null; return (l?l.innerText.trim().slice(0,30):\"NONE\")})""")
    print("selected:", state)
    # Save draft
    try:
        page.get_by_role("button", name="Save draft").first.click(timeout=15000)
        page.wait_for_timeout(9000)
        print("saved. url:", page.url)
    except Exception as e:
        print("save failed:", str(e).splitlines()[0][:120])
    print("BODY:", page.locator("body").inner_text()[:260].replace(chr(10)," "))
    ctx.close()
