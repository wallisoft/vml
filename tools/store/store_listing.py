import sys, re
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright

LISTING = "/home/steve/kato-submit/listing.vml"
LOGO = "/home/steve/kato-submit/kato-300.png"
URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/listings?languageid=95&languagecode=en-gb"

def log(*a): print(*a, flush=True)

with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    name, fields, folder = listing.read_listing(LISTING)

    url = URL
    page.goto(url, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(1500)
    log("on:", page.url)
    has_desc = page.get_by_label("Description", exact=True).count() > 0
    log("has Description field:", has_desc)
    if not has_desc:
        # likely need to add a language first
        body = page.locator("body").inner_text()[:300].replace("\n"," ")
        log("no form yet. body:", body)
        # try to add English (United Kingdom)
        add = page.get_by_role("button", name=re.compile("add", re.I))
        log("add buttons:", [b.strip() for b in page.evaluate("()=>[...document.querySelectorAll('button')].map(b=>b.innerText).filter(t=>t&&t.length<30)")][:15])
        ctx.close(); sys.exit(2)

    # fill text fields (skip language + screenshots, handled separately)
    done, missed = [], []
    for label, value in fields.items():
        if label.lower() in ("language", "screenshots"): continue
        parts = [x.strip() for x in value.split("|")] if "|" in value and "\n" not in value else [value]
        boxes = None
        for how in (dict(exact=True), None):
            try:
                f = page.get_by_label(label, **how) if how else page.get_by_label(re.compile(re.escape(label), re.I))
                if f.count(): boxes = f; break
            except Exception: pass
        if not boxes: missed.append(label); continue
        try:
            for i, part in enumerate(parts[:boxes.count()]):
                b = boxes.nth(i); b.scroll_into_view_if_needed(); b.fill(part); page.wait_for_timeout(150)
            done.append(label)
        except Exception as e:
            missed.append(f"{label}:{str(e).splitlines()[0][:50]}")
    log("filled:", done)
    log("missed:", missed)

    # screenshots one at a time (#image-upload-input is a single-file input)
    shots = [p.strip() for p in fields.get("Screenshots","").split("|") if p.strip()]
    for s in shots:
        fp = str((folder / s).resolve())
        try:
            inp = page.locator("#image-upload-input")
            if not inp.count():
                inp = page.locator("input[type=file]").first
            inp.set_input_files([fp]); page.wait_for_timeout(9000)
            dlg = page.locator("[role=dialog]")
            if dlg.count() and dlg.first.is_visible():
                try: page.get_by_role("button", name="OK").first.click()
                except Exception: pass
            log("screenshot uploaded:", s)
        except Exception as e:
            log("screenshot FAIL", s, str(e).splitlines()[0][:80])

    # 300x300 logo: file input near 'logo'/'1:1'/'300'
    idx = page.evaluate("""(keys) => [...document.querySelectorAll('input[type=file]')].findIndex(e=>{
        let p=e; for(let k=0;k<7&&p;k++){p=p.parentElement; if(p&&p.innerText){const t=p.innerText.toLowerCase();
        if(keys.some(w=>t.includes(w))) return true;}} return false;})""", ["logo","1:1","300 x 300","300x300"])
    log("logo input idx:", idx)
    if idx >= 0:
        try:
            page.locator("input[type=file]").nth(idx).set_input_files([LOGO]); page.wait_for_timeout(9000)
            log("logo uploaded")
        except Exception as e:
            log("logo FAIL", str(e).splitlines()[0][:80])
    else:
        log("no logo upload box found; file inputs:",
            page.evaluate("()=>[...document.querySelectorAll('input[type=file]')].map((e,i)=>i+':'+(e.id||e.name||'?')).slice(0,10)"))

    # Save
    page.wait_for_timeout(1500)
    saved = None
    for nm in ["Save draft","Save","Save all"]:
        b = page.get_by_role("button", name=nm, exact=True)
        if b.count() and b.first.is_enabled():
            try: b.first.scroll_into_view_if_needed(); b.first.click(timeout=10000); saved=nm; break
            except Exception as e: log("save click", nm, "err", str(e).splitlines()[0][:60])
    log("saved via:", saved)
    page.wait_for_timeout(8000)
    log("final url:", page.url)
    # any remaining-required warnings
    warn = page.evaluate("()=>[...document.querySelectorAll('[role=alert],[class*=error],[class*=Error]')].map(e=>e.innerText.trim()).filter(t=>t&&t.length<120).slice(0,6)")
    log("warnings:", warn)
    ctx.close()
