import sys
sys.path.insert(0, "tools/store")
import listing
from playwright.sync_api import sync_playwright
URL = "https://partner.microsoft.com/en-us/dashboard/products/9NC0S7C163TV/submissions/1152921505702184067/listings?languageid=95&languagecode=en-gb"
FOLDER = "/home/steve/kato-submit"
def log(*a): print(*a, flush=True)
def empty_shot_idx(page):
    return page.evaluate("""()=>{const ins=[...document.querySelectorAll('input[type=file]')];
      for(let i=0;i<ins.length;i++){let e=ins[i], inSec=false, host=null, p=e;
        for(let k=0;k<12&&p;k++){p=p.parentElement; if(p&&p.innerText&&p.innerText.includes('Max upload')) inSec=true;
          if(p&&!host&&p.offsetParent){const w=p.getBoundingClientRect().width; if(w<420&&w>80) host=p;}}
        if(inSec && host && !host.querySelector('img')) return i;}
      return -1;}""")
def shots_count(page):
    return page.evaluate("""()=>[...document.querySelectorAll('img')].filter(i=>i.src&&(i.src.startsWith('blob:')||i.src.startsWith('data:'))).length""")
def kill_modal(page):
    for _ in range(3):
        m = page.locator(".modal.in, [role=dialog]")
        if m.count() and m.first.is_visible():
            for nm in ["OK","Close","Cancel","Got it"]:
                btn=page.get_by_role("button", name=nm, exact=True)
                if btn.count() and btn.first.is_visible():
                    try: btn.first.click(); page.wait_for_timeout(800); break
                    except Exception: pass
            else:
                try: page.keyboard.press("Escape")
                except Exception: pass
            page.wait_for_timeout(600)
        else: break
with sync_playwright() as pw:
    ctx, page = listing.browser(pw)
    page.goto(URL, wait_until="domcontentloaded"); listing.settle(page); page.wait_for_timeout(2500)
    log("start:", shots_count(page))
    for s in ["shot2.png", "shot3.png"]:
        before = shots_count(page)
        idx = empty_shot_idx(page)
        log("empty shot slot for", s, "=", idx)
        if idx < 0: log("  none found, stopping"); break
        page.locator("input[type=file]").nth(idx).set_input_files([f"{FOLDER}/{s}"])
        ok=False
        for _ in range(14):
            page.wait_for_timeout(1500); kill_modal(page)
            if shots_count(page) > before: ok=True; break
        log(s, "added:", ok, "count:", shots_count(page))
    kill_modal(page)
    log("final:", shots_count(page))
    b=page.get_by_role("button", name="Save", exact=True)
    if b.count() and b.first.is_enabled():
        try: b.first.click(timeout=12000); page.wait_for_timeout(9000); log("saved", page.url)
        except Exception as e: log("save err", str(e).splitlines()[0][:80])
    else: log("save not enabled")
    ctx.close()
