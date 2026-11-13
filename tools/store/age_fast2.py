
import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright

URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/ageratings/edit"
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); page.wait_for_timeout(5000)
    page.get_by_text("All Other App Types", exact=False).first.click(); page.wait_for_timeout(2500)
    for i in range(page.get_by_role("radiogroup").count()):
        no = page.get_by_role("radiogroup").nth(i).get_by_text("No", exact=True)
        if no.count():
            try: no.first.click(); page.wait_for_timeout(180)
            except Exception: pass
    # explicit physical-media No
    try:
        cont = page.get_by_text("physical media", exact=False).first.locator("xpath=ancestor::*[.//input[@type=\"radio\"]][1]")
        cont.get_by_text("No", exact=True).first.click(); page.wait_for_timeout(600)
        print("physical-media No clicked")
    except Exception as e:
        print("phys No err:", str(e).splitlines()[0][:90])
    page.wait_for_timeout(800)
    # Save draft diagnostics
    sd = page.get_by_role("button", name="Save draft")
    print("Save draft count:", sd.count(), "enabled:", (sd.first.is_enabled() if sd.count() else None))
    if sd.count() and sd.first.is_enabled():
        sd.first.scroll_into_view_if_needed(); sd.first.click(timeout=9000); page.wait_for_timeout(9000)
        print("SAVED. url:", page.url)
    # any validation text
    val = page.evaluate("""() => [...document.querySelectorAll(\"[class*=error], [role=alert], [class*=required]\")].map(e=>e.innerText.trim()).filter(t=>t&&t.length<120).slice(0,6)""")
    print("validation:", val)
    print("body:", page.locator("body").inner_text()[:160].replace(chr(10)," "))
    ctx.close()
