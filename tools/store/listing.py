#!/usr/bin/env python3
"""
A Microsoft Store listing, filled in for you: the Partner Center pages that have no API (a new product's Store listing,
its properties, its age ratings...) driven in a real browser you can watch, from a listing file you can read.

You sign in yourself, once, in the browser it opens; it keeps that sign-in in its own profile (not your everyday
browser's), so no password is ever in a file or a script. It fills in fields and stops: you look it over and press
Save or Submit yourself.

    python3 tools/store/listing.py login                    open Partner Center: sign in, then close the window
    python3 tools/store/listing.py survey URL [--fields]    every field on that page (label, kind), and its links and
                                                            buttons (not with --fields), to
                                                            ~/.cache/storelisting/survey-*.json: what fill can fill
    python3 tools/store/listing.py fill LISTING URL         that page's fields, from a listing file
    python3 tools/store/listing.py check LISTING            the listing file's fields, and anything too long

A listing file (VML, like a recipe), e.g. apps/mountie/store/listing.vml:

    @Listing Mountie
    Language=English (United Kingdom)
    Short description=Your drives, all in one place
    Description=<<END
    Mount cloud storage, SSH servers, disk images and your phone as ordinary drives...
    END
    Product features=Mount SSH and SFTP folders as drives | Open ISO and VHD files | Share your phone over Wi-Fi
    Search terms=ssh drive | sftp | mount | iso | vhd
    Copyright and trademark info=© 2026 Wallisoft
    Privacy policy URL=https://tiny-web.uk/privacy.php
    Website=https://mountie.eur.bz
    Support contact info=hello@tiny-web.uk
    Screenshots=store/shot1.png | store/shot2.png

Each key is the field's label as Partner Center shows it (survey lists them); "a | b | c" fills a field that has
several boxes (features, search terms) one box each, or uploads several files. Paths are from the listing file's folder.
Needs Playwright: python3 -m pip install --user playwright && python3 -m playwright install chromium
"""
import json
import re
import sys
import time
from pathlib import Path

HOME = Path.home() / ".cache" / "storelisting"
PROFILE = HOME / "profile"
START = "https://partner.microsoft.com/dashboard/apps-and-games/overview"
LIMITS = {"short description": 1000, "description": 10000, "product features": 200, "search terms": 30,
          "copyright and trademark info": 200}                 # (per box, as Partner Center counts them)


def read_listing(path):
    p = Path(path)
    fields, key, lines, name = {}, None, None, ""
    for raw in p.read_text(encoding="utf-8").splitlines():
        if lines is not None:
            if raw.strip() == "END":
                fields[key], lines = "\n".join(lines).strip(), None
            else:
                lines.append(raw)
            continue
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@Listing"):
            name = line[8:].strip()
            continue
        k, _, v = line.partition("=")
        if v.strip() == "<<END":
            key, lines = k.strip(), []
        else:
            fields[k.strip()] = v.strip()
    return name, fields, p.parent


def check(path):
    name, fields, _ = read_listing(path)
    print(f"{name}: {len(fields)} fields")
    bad = 0
    for k, v in fields.items():
        parts = [x.strip() for x in v.split("|")] if "|" in v and "\n" not in v else [v]
        limit = LIMITS.get(k.lower())
        over = [x for x in parts if limit and len(x) > limit]
        print(f"  {k}: {len(parts)} part(s), {sum(len(x) for x in parts)} characters" + (f"  TOO LONG (over {limit})" if over else ""))
        bad += bool(over)
    return 1 if bad else 0


def browser(pw):
    PROFILE.mkdir(parents=True, exist_ok=True)
    ctx = pw.chromium.launch_persistent_context(str(PROFILE), headless=bool(__import__("os").environ.get("LISTING_HEADLESS")), viewport={"width": 1400, "height": 900})
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return ctx, page


def signed_in(page):
    return "login.microsoftonline.com" not in page.url and "login.live.com" not in page.url


def settle(page, seconds=40):
    """Partner Center builds its pages after they load: wait until it has drawn something worth reading."""
    end = time.time() + seconds
    while time.time() < end:
        try:
            n = page.evaluate("() => [...document.querySelectorAll('a[href], button, input, textarea')]"
                              ".filter(e => e.offsetParent).length")
        except Exception:
            n = 0
        if n > 8:
            page.wait_for_timeout(1500)                       # (and a moment more for the rest of it)
            return
        page.wait_for_timeout(1000)


def survey(page, url):
    page.goto(url, wait_until="domcontentloaded")
    settle(page)
    if not signed_in(page):
        sys.exit("Not signed in: run  listing.py login  first, and sign in in the window it opens.")
    found = page.evaluate("""() => {
        const out = [];
        const label = el => {
            if (el.labels && el.labels.length) return el.labels[0].innerText.trim();
            const by = el.getAttribute('aria-labelledby');
            if (by) return by.split(' ').map(i => (document.getElementById(i) || {}).innerText || '').join(' ').trim();
            return (el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.name || '').trim();
        };
        for (const el of document.querySelectorAll('input, textarea, select, [contenteditable="true"]')) {
            if (el.type === 'hidden' || !el.offsetParent) continue;
            out.push({label: label(el), kind: el.tagName.toLowerCase() + (el.type ? ':' + el.type : ''),
                      value: (el.value || '').slice(0, 60)});
        }
        const seen = new Set();
        for (const el of document.querySelectorAll('a[href], button, [role="button"], [role="link"]')) {
            if (!el.offsetParent) continue;
            const text = (el.innerText || el.getAttribute('aria-label') || '').trim().replace(/\\s+/g, ' ');
            const href = el.href || '';
            if (!text || seen.has(text + href)) continue;
            seen.add(text + href);
            out.push({label: text.slice(0, 80), kind: el.tagName === 'A' ? 'link' : 'button', value: href});
        }
        return out;
    }""")
    HOME.mkdir(parents=True, exist_ok=True)
    out = HOME / f"survey-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"url": page.url, "title": page.title(), "fields": found}, indent=1), encoding="utf-8")
    fields = [f for f in found if f["kind"] not in ("link", "button")]
    print(f"{len(fields)} fields, {len(found) - len(fields)} links and buttons on '{page.title()}' -> {out}")
    for f in found:
        if f["kind"] in ("link", "button") and "--fields" in sys.argv:
            continue
        print(f"  {f['kind']:<16} {f['label'][:70]}" + (f"   ({f['value']})" if f['value'] else ""))


def fill(page, path, url):
    name, fields, folder = read_listing(path)
    page.goto(url, wait_until="domcontentloaded")
    settle(page)
    if not signed_in(page):
        sys.exit("Not signed in: run  listing.py login  first, and sign in in the window it opens.")
    done, missed = 0, []
    for label, value in fields.items():
        if label.lower() == "language":
            continue
        parts = [x.strip() for x in value.split("|")] if "|" in value and "\n" not in value else [value]
        boxes, n = None, 0
        for how in (dict(exact=True), dict()):                 # (the exact label first: "Description" isn't "Short description")
            try:
                found = page.get_by_label(label, **how) if how else page.get_by_label(re.compile(re.escape(label), re.I))
                if found.count():
                    boxes, n = found, found.count()
                    break
            except Exception:
                pass
        if n == 0:
            missed.append(label)
            continue
        first = boxes.first
        kind = (first.get_attribute("type") or "").lower()
        try:
            if kind == "file":                                 # screenshots, logos: upload the files
                first.set_input_files([str((folder / x).resolve()) for x in parts])
            else:
                for i, part in enumerate(parts[:n]):
                    box = boxes.nth(i)
                    box.scroll_into_view_if_needed()
                    box.fill(part)
            done += 1
            print(f"  filled: {label}" + (f" ({min(len(parts), n)} of {len(parts)} parts: the page has {n} boxes)"
                                          if len(parts) > n and kind != "file" else f" ({len(parts)} parts)" if len(parts) > 1 else ""))
        except Exception as e:
            missed.append(f"{label} ({str(e).splitlines()[0][:80]})")
    print(f"{name}: {done} filled" + (f"; not found or not fillable: {', '.join(missed)}" if missed else ""))
    print("Nothing has been saved or submitted: look it over in the window, then Save (or Submit) yourself.")


def main(argv):
    if not argv or argv[0] not in ("login", "survey", "fill", "check"):
        print(__doc__)
        return 1
    if argv[0] == "check":
        return check(argv[1])
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx, page = browser(pw)
        if argv[0] == "login":
            page.goto(START)
            print("Sign in to Partner Center in the window; close it when you see the dashboard.")
            page.wait_for_event("close", timeout=0)
        elif argv[0] == "survey":
            survey(page, argv[1])
            input("Press Enter here to close the browser... ") if sys.stdin.isatty() else page.wait_for_timeout(15000)
        else:
            fill(page, argv[1], argv[2])
            print("The window stays open until you close it.")
            page.wait_for_event("close", timeout=0)
        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
