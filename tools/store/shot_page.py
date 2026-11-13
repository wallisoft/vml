import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto("https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/overview", wait_until="domcontentloaded")
    listing.settle(page); page.wait_for_timeout(2500)
    page.screenshot(path="/tmp/pc_overview.png", full_page=True)
    print("overview shot ok", page.url)
    ctx.close()
