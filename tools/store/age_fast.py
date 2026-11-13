
import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright

URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/ageratings/edit"
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)   # fast: no 40s settle
    page.get_by_text("All Other App Types", exact=False).first.click()
    page.wait_for_timeout(2500)
    for i in range(page.get_by_role("radiogroup").count()):
        no = page.get_by_role("radiogroup").nth(i).get_by_text("No", exact=True)
        if no.count():
            try: no.first.click(); page.wait_for_timeout(180)
            except Exception: pass
    # save immediately
    saved = False
    for name in ["Save draft", "Save", "Next", "Generate", "Done"]:
        b = page.get_by_role("button", name=name, exact=True)
        if b.count() and b.first.is_enabled():
            try:
                b.first.scroll_into_view_if_needed(); b.first.click(timeout=8000); saved=name; break
            except Exception as e:
                print("click", name, "err:", str(e).splitlines()[0][:70])
    print("saved via:", saved)
    page.wait_for_timeout(9000)
    print("url:", page.url)
    print("body:", page.locator("body").inner_text()[:200].replace(chr(10)," "))
    ctx.close()
