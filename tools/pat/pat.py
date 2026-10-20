#!/usr/bin/env python3
"""
Pat: posts your news (the driver) and keeps the books on what each post earned (the accountant). Pat.vml is the
window; this does the work, answering in JSON. Everything lives in one SQLite file, ~/.vml/pat/pat.db (PAT_DB to put
it elsewhere): your products, channels, posts and their numbers, in plain tables you can read, back up or move.

    pat.py channels                      the channels, as JSON (secrets left out)
    pat.py channel-save FILE             add or change one: JSON {id?, kind, name, handle, server, secret, enabled}
    pat.py channel-test ID               does it work? (logs in, says who it is)
    pat.py channel-remove ID
    pat.py products | product-save FILE | product-remove ID
    pat.py draft PRODUCT_ID              a draft for every enabled channel, sized and shaped for each
    pat.py posts [STATUS]                draft | approved | posted | assisted | failed (all if none)
    pat.py post-save FILE                {id, text}: change a draft's words
    pat.py approve ID | unapprove ID
    pat.py send ID                       posts it (or, for an assisted channel, says where to post it by hand)
    pat.py mark-posted ID URL            an assisted post, posted by hand: where it is
    pat.py stats                         fetches each posted post's numbers now
    pat.py report                        the books: totals per channel and per product, and each post's numbers
    pat.py kinds                         the kinds of channel Pat knows

Kinds:
    posted by Pat     mastodon (server, access token), bluesky (handle, app password), devto (API key),
                      facebook (a Page: its id as handle, a Page access token as secret)
    assisted          quora, reddit, hackernews, linkedin, x: Pat drafts, opens the page and puts the words on the
                      clipboard; you post it (those communities don't want bots, and an honest post from you does
                      better there anyway), then mark it posted with its link.
"""
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DB = Path(os.environ.get("PAT_DB") or Path.home() / ".vml" / "pat" / "pat.db")

KINDS = {
    "mastodon":   {"label": "Mastodon", "limit": 500, "assisted": False, "fields": ["server", "handle", "secret"],
                   "help": "Server: your instance (mastodon.social); Key: an access token (Preferences, Development, New application, write:statuses read:statuses)"},
    "bluesky":    {"label": "Bluesky", "limit": 300, "assisted": False, "fields": ["handle", "secret"],
                   "help": "Who: you.bsky.social; Key: an app password (Settings, Privacy and security, App passwords)"},
    "devto":      {"label": "dev.to", "limit": 0, "assisted": False, "fields": ["secret"],
                   "help": "Key: an API key (Settings, Extensions, DEV Community API Keys); posts are articles"},
    "facebook":   {"label": "Facebook Page", "limit": 0, "assisted": False, "fields": ["handle", "secret"],
                   "help": "Who: the Page's id; Key: a Page access token (Meta for Developers). A Page, not a profile: Facebook lets no app post to a person's own timeline"},
    "quora":      {"label": "Quora", "limit": 0, "assisted": True, "fields": ["handle"],
                   "help": "You post it: Pat drafts an answer and opens Quora's search for questions about it; you answer as yourself"},
    "reddit":     {"label": "Reddit", "limit": 0, "assisted": True, "fields": ["handle", "server"],
                   "help": "You post it; Server: the subreddit (r/linux). Read its rules first: many allow makers' posts only on set days"},
    "hackernews": {"label": "Hacker News", "limit": 80, "assisted": True, "fields": ["handle"],
                   "help": "You post it: a Show HN title; the link goes in its own box there"},
    "linkedin":   {"label": "LinkedIn", "limit": 3000, "assisted": True, "fields": ["handle"],
                   "help": "You post it (posting by app needs LinkedIn's approval: later)"},
    "x":          {"label": "X", "limit": 280, "assisted": True, "fields": ["handle"],
                   "help": "You post it (X charges for its posting API)"},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, link TEXT DEFAULT '',
    headline TEXT DEFAULT '', description TEXT DEFAULT '', tags TEXT DEFAULT '', created REAL);
CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
    handle TEXT DEFAULT '', server TEXT DEFAULT '', secret TEXT DEFAULT '', enabled INTEGER DEFAULT 1, created REAL);
CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY, product_id INTEGER, channel_id INTEGER, title TEXT DEFAULT '',
    text TEXT DEFAULT '', status TEXT DEFAULT 'draft', created REAL, posted REAL, remote_id TEXT DEFAULT '',
    url TEXT DEFAULT '', error TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS stats (id INTEGER PRIMARY KEY, post_id INTEGER, at REAL, likes INTEGER DEFAULT 0,
    reposts INTEGER DEFAULT 0, replies INTEGER DEFAULT 0, views INTEGER DEFAULT 0);
"""


def db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    fresh = not DB.exists()
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    if fresh:
        try:
            os.chmod(DB, 0o600)                          # (it holds your channels' keys: yours alone)
        except OSError:
            pass
    return con


def out(obj):
    print(json.dumps(obj, ensure_ascii=False))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- talking to the platforms

def http(method, url, body=None, headers=None, form=False, timeout=30):
    """(status, parsed JSON or text). Never raises for an HTTP error: its body is the answer."""
    h = {"User-Agent": "Pat (Wallisoft)", "Accept": "application/json", **(headers or {})}
    data = None
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            h["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw, code = r.read().decode("utf-8", "replace"), r.status
    except urllib.error.HTTPError as e:
        raw, code = e.read().decode("utf-8", "replace"), e.code
    try:
        return code, json.loads(raw)
    except ValueError:
        return code, raw


def why(code, body):
    if isinstance(body, dict):
        for k in ("error_description", "error", "message", "detail"):
            v = body.get(k)
            if isinstance(v, dict):
                v = v.get("message") or json.dumps(v)
            if v:
                return f"{code}: {v}"
    return f"{code}: {str(body)[:200]}"


def mastodon_base(ch):
    s = (ch["server"] or "mastodon.social").strip().rstrip("/")
    return s if s.startswith("http") else "https://" + s


def bluesky_session(ch):
    code, b = http("POST", "https://bsky.social/xrpc/com.atproto.server.createSession",
                   {"identifier": ch["handle"].lstrip("@"), "password": ch["secret"]})
    if code != 200:
        raise RuntimeError("Bluesky wouldn't log in: " + why(code, b))
    return b["accessJwt"], b["did"]


def link_facets(text):
    """Bluesky makes links clickable only when told where they are, in bytes."""
    facets, raw = [], text.encode("utf-8")
    for m in re.finditer(r"https?://[^\s)]+", text):
        start = len(text[:m.start()].encode("utf-8"))
        end = start + len(m.group(0).encode("utf-8"))
        facets.append({"index": {"byteStart": start, "byteEnd": end},
                       "features": [{"$type": "app.bsky.richtext.facet#link", "uri": m.group(0)}]})
    return facets


def test(ch):
    k = ch["kind"]
    if KINDS[k]["assisted"]:
        return f"{KINDS[k]['label']} is assisted: nothing to log in to (you post as yourself)."
    if k == "mastodon":
        code, b = http("GET", mastodon_base(ch) + "/api/v1/accounts/verify_credentials",
                       headers={"Authorization": "Bearer " + ch["secret"]})
        if code != 200:
            raise RuntimeError(why(code, b))
        return f"Mastodon: logged in as @{b.get('acct')} ({b.get('followers_count', 0)} followers)"
    if k == "bluesky":
        jwt, did = bluesky_session(ch)
        code, b = http("GET", "https://bsky.social/xrpc/app.bsky.actor.getProfile?actor=" + urllib.parse.quote(did),
                       headers={"Authorization": "Bearer " + jwt})
        return f"Bluesky: logged in as @{b.get('handle', ch['handle'])} ({b.get('followersCount', 0)} followers)" \
            if code == 200 else "Bluesky: logged in"
    if k == "devto":
        code, b = http("GET", "https://dev.to/api/users/me", headers={"api-key": ch["secret"]})
        if code != 200:
            raise RuntimeError(why(code, b))
        return f"dev.to: logged in as {b.get('username')}"
    if k == "facebook":
        code, b = http("GET", f"https://graph.facebook.com/v19.0/{ch['handle']}?fields=name,followers_count&access_token="
                       + urllib.parse.quote(ch["secret"]))
        if code != 200:
            raise RuntimeError(why(code, b))
        return f"Facebook Page: {b.get('name')} ({b.get('followers_count', 0)} followers)"
    raise RuntimeError("unknown kind " + k)


def publish(ch, post):
    """Post it: (remote id, url)."""
    k, text = ch["kind"], post["text"]
    if k == "mastodon":
        code, b = http("POST", mastodon_base(ch) + "/api/v1/statuses", {"status": text},
                       headers={"Authorization": "Bearer " + ch["secret"],
                                "Idempotency-Key": f"pat-{post['id']}"})          # (sent twice: posted once)
        if code not in (200, 201):
            raise RuntimeError(why(code, b))
        return str(b["id"]), b.get("url") or ""
    if k == "bluesky":
        jwt, did = bluesky_session(ch)
        record = {"$type": "app.bsky.feed.post", "text": text,
                  "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())}
        facets = link_facets(text)
        if facets:
            record["facets"] = facets
        code, b = http("POST", "https://bsky.social/xrpc/com.atproto.repo.createRecord",
                       {"repo": did, "collection": "app.bsky.feed.post", "record": record},
                       headers={"Authorization": "Bearer " + jwt})
        if code != 200:
            raise RuntimeError(why(code, b))
        rkey = b["uri"].rsplit("/", 1)[-1]
        return b["uri"], f"https://bsky.app/profile/{ch['handle'].lstrip('@')}/post/{rkey}"
    if k == "devto":
        tags = [t for t in re.split(r"[\s,#]+", post.get("tags") or "") if t][:4]
        code, b = http("POST", "https://dev.to/api/articles",
                       {"article": {"title": post["title"] or "News", "body_markdown": text, "published": True,
                                    "tags": [re.sub(r"[^a-z0-9]", "", t.lower()) for t in tags]}},
                       headers={"api-key": ch["secret"]})
        if code not in (200, 201):
            raise RuntimeError(why(code, b))
        return str(b["id"]), b.get("url") or ""
    if k == "facebook":
        body = {"message": text, "access_token": ch["secret"]}
        if post.get("link"):
            body["link"] = post["link"]
        code, b = http("POST", f"https://graph.facebook.com/v19.0/{ch['handle']}/feed", body, form=True)
        if code != 200:
            raise RuntimeError(why(code, b))
        pid = str(b.get("id", ""))
        return pid, f"https://www.facebook.com/{pid}"
    raise RuntimeError("not a channel Pat posts to")


def numbers(ch, post):
    """{likes, reposts, replies, views} for a posted post, now."""
    k, rid = ch["kind"], post["remote_id"]
    if k == "mastodon":
        code, b = http("GET", f"{mastodon_base(ch)}/api/v1/statuses/{rid}", headers={"Authorization": "Bearer " + ch["secret"]})
        if code == 200:
            return {"likes": b.get("favourites_count", 0), "reposts": b.get("reblogs_count", 0),
                    "replies": b.get("replies_count", 0), "views": 0}
    elif k == "bluesky":
        code, b = http("GET", "https://public.api.bsky.app/xrpc/app.bsky.feed.getPosts?uris=" + urllib.parse.quote(rid))
        if code == 200 and b.get("posts"):
            p = b["posts"][0]
            return {"likes": p.get("likeCount", 0), "reposts": p.get("repostCount", 0) + p.get("quoteCount", 0),
                    "replies": p.get("replyCount", 0), "views": 0}
    elif k == "devto":
        code, b = http("GET", "https://dev.to/api/articles/me/all?per_page=100", headers={"api-key": ch["secret"]})
        if code == 200:
            for a in b:
                if str(a.get("id")) == rid:
                    return {"likes": a.get("public_reactions_count", 0), "reposts": 0,
                            "replies": a.get("comments_count", 0), "views": a.get("page_views_count", 0)}
    elif k == "facebook":
        code, b = http("GET", f"https://graph.facebook.com/v19.0/{rid}?fields=reactions.summary(true),comments.summary(true),shares"
                       f"&access_token={urllib.parse.quote(ch['secret'])}")
        if code == 200:
            return {"likes": b.get("reactions", {}).get("summary", {}).get("total_count", 0),
                    "reposts": b.get("shares", {}).get("count", 0),
                    "replies": b.get("comments", {}).get("summary", {}).get("total_count", 0), "views": 0}
    return None


# ---------------------------------------------------------------- drafting

def shorten(text, limit):
    if not limit or len(text) <= limit:
        return text
    return text[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:-") + "…"


def hashtags(tags, n=3):
    return " ".join("#" + re.sub(r"[^A-Za-z0-9]", "", t) for t in re.split(r"[\s,]+", tags or "") if t)[: 200].split(" ")[:n]


def draft_for(kind, p):
    """A first draft for one kind of channel, from the product: (title, text). You edit and approve it."""
    name, link, head, desc = p["name"], p["link"], p["headline"] or p["name"], p["description"]
    tags = " ".join(hashtags(p["tags"]))
    if kind in ("mastodon", "bluesky", "x"):
        limit = KINDS[kind]["limit"]
        tail = f"\n\n{link}" + (f"\n{tags}" if tags else "")
        body = shorten(f"{head}\n\n{desc}", limit - len(tail))
        return "", body + tail
    if kind == "devto":
        return f"{name}: {head}", (f"{desc}\n\n## What it does\n\n(Say what it does, in a few lines.)\n\n"
                                   f"## Try it\n\n{link}\n\n*I'm Steve, and I made {name} at Wallisoft. Questions welcome below.*")
    if kind == "facebook":
        return "", f"{head}\n\n{desc}\n\n{link}"
    if kind == "hackernews":
        return shorten(f"Show HN: {name} – {head}", 80), link
    if kind == "reddit":
        return f"I made {name}: {head}", (f"{desc}\n\n{link}\n\nI'm the maker, so happy to answer anything, and "
                                          f"criticism is welcome.")
    if kind == "quora":
        return name, (f"(Answer the question first, honestly and in your own words. Then:)\n\n"
                      f"Full disclosure, I made this, but {name} does exactly that: {desc} It's here: {link}")
    if kind == "linkedin":
        return "", f"{head}\n\n{desc}\n\nI built {name} at Wallisoft. {link}\n\n{tags}"
    return "", f"{head}\n\n{desc}\n\n{link}"


def assisted_where(kind, ch, p):
    q = urllib.parse.quote(p["name"] + " " + (p["headline"] or ""))
    return {
        "quora": "https://www.quora.com/search?q=" + urllib.parse.quote(p["headline"] or p["name"]) + "&type=question",
        "reddit": f"https://www.reddit.com/{(ch['server'] or 'r/software').strip('/')}/submit",
        "hackernews": "https://news.ycombinator.com/submit",
        "linkedin": "https://www.linkedin.com/feed/?shareActive=true",
        "x": "https://x.com/compose/post",
    }.get(kind, "https://www.google.com/search?q=" + q)


# ---------------------------------------------------------------- the commands

def rows(cur):
    return [dict(r) for r in cur.fetchall()]


def public(ch):
    d = dict(ch)
    d["has_secret"] = bool(d.pop("secret", ""))
    d["label"] = KINDS.get(d["kind"], {}).get("label", d["kind"])
    d["assisted"] = KINDS.get(d["kind"], {}).get("assisted", True)
    return d


def main(argv):
    if not argv:
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    con = db()
    if cmd == "kinds":
        return out([{"kind": k, **v} for k, v in KINDS.items()]) or 0
    if cmd == "channels":
        return out([public(c) for c in con.execute("SELECT * FROM channels ORDER BY name")]) or 0
    if cmd == "channel-save":
        c = read(args[0])
        if c.get("kind") not in KINDS:
            return out({"error": "Pick a kind of channel."}) or 1
        fields = {k: str(c.get(k) or "").strip() for k in ("kind", "name", "handle", "server")}
        fields["name"] = fields["name"] or KINDS[c["kind"]]["label"]
        fields["enabled"] = 0 if str(c.get("enabled", "1")).lower() in ("0", "false") else 1
        if c.get("id"):
            sets = ", ".join(f"{k}=?" for k in fields) + (", secret=?" if c.get("secret") else "")
            vals = list(fields.values()) + ([c["secret"]] if c.get("secret") else []) + [int(c["id"])]
            con.execute(f"UPDATE channels SET {sets} WHERE id=?", vals)
            cid = int(c["id"])
        else:
            cur = con.execute("INSERT INTO channels (kind, name, handle, server, enabled, secret, created) VALUES (?,?,?,?,?,?,?)",
                              (*fields.values(), c.get("secret") or "", time.time()))
            cid = cur.lastrowid
        con.commit()
        return out({"id": cid}) or 0
    if cmd == "channel-test":
        ch = con.execute("SELECT * FROM channels WHERE id=?", (int(args[0]),)).fetchone()
        try:
            return out({"ok": True, "said": test(ch)}) or 0
        except Exception as e:
            return out({"ok": False, "said": str(e)}) or 0
    if cmd == "channel-remove":
        con.execute("DELETE FROM channels WHERE id=?", (int(args[0]),))
        con.commit()
        return out({"ok": True}) or 0
    if cmd == "products":
        return out(rows(con.execute("SELECT * FROM products ORDER BY name"))) or 0
    if cmd == "product-save":
        p = read(args[0])
        f = {k: str(p.get(k) or "").strip() for k in ("name", "link", "headline", "description", "tags")}
        if not f["name"]:
            return out({"error": "A product needs a name."}) or 1
        if p.get("id"):
            con.execute("UPDATE products SET name=?, link=?, headline=?, description=?, tags=? WHERE id=?", (*f.values(), int(p["id"])))
            pid = int(p["id"])
        else:
            pid = con.execute("INSERT INTO products (name, link, headline, description, tags, created) VALUES (?,?,?,?,?,?)",
                              (*f.values(), time.time())).lastrowid
        con.commit()
        return out({"id": pid}) or 0
    if cmd == "product-remove":
        con.execute("DELETE FROM products WHERE id=?", (int(args[0]),))
        con.commit()
        return out({"ok": True}) or 0
    if cmd == "draft":
        p = con.execute("SELECT * FROM products WHERE id=?", (int(args[0]),)).fetchone()
        made = []
        for ch in con.execute("SELECT * FROM channels WHERE enabled=1"):
            title, text = draft_for(ch["kind"], p)
            made.append(con.execute("INSERT INTO posts (product_id, channel_id, title, text, status, created) VALUES (?,?,?,?,?,?)",
                                    (p["id"], ch["id"], title, text, "draft", time.time())).lastrowid)
        con.commit()
        return out({"made": len(made), "ids": made}) or 0
    if cmd == "posts":
        q = ("SELECT posts.*, channels.kind, channels.name AS channel, products.name AS product FROM posts "
             "LEFT JOIN channels ON channels.id=posts.channel_id LEFT JOIN products ON products.id=posts.product_id")
        cur = con.execute(q + (" WHERE posts.status=?" if args else "") + " ORDER BY posts.id DESC", tuple(args[:1]))
        res = rows(cur)
        for r in res:
            r["limit"] = KINDS.get(r["kind"] or "", {}).get("limit", 0)
            r["assisted"] = KINDS.get(r["kind"] or "", {}).get("assisted", True)
        return out(res) or 0
    if cmd == "post-save":
        p = read(args[0])
        con.execute("UPDATE posts SET text=?, title=COALESCE(?, title), status='draft' "      # (changed words: approve again)
                    "WHERE id=? AND status IN ('draft','approved','failed')",
                    (p.get("text", ""), p.get("title"), int(p["id"])))
        con.commit()
        return out({"ok": True}) or 0
    if cmd in ("approve", "unapprove"):
        con.execute("UPDATE posts SET status=? WHERE id=? AND status IN ('draft','approved','failed')",
                    ("approved" if cmd == "approve" else "draft", int(args[0])))
        con.commit()
        return out({"ok": True}) or 0
    if cmd == "remove-post":
        con.execute("DELETE FROM posts WHERE id=?", (int(args[0]),))
        con.commit()
        return out({"ok": True}) or 0
    if cmd == "send":
        post = con.execute("SELECT posts.*, products.link, products.tags, products.name AS product_name, products.headline "
                           "FROM posts LEFT JOIN products ON products.id=posts.product_id WHERE posts.id=?", (int(args[0]),)).fetchone()
        if post is None:
            return out({"ok": False, "said": "There's no such post."}) or 1
        if post["status"] != "approved":
            return out({"ok": False, "said": "Approve it first: nothing goes out without your say-so."}) or 0
        ch = con.execute("SELECT * FROM channels WHERE id=?", (post["channel_id"],)).fetchone()
        if KINDS[ch["kind"]]["assisted"]:
            con.execute("UPDATE posts SET status='assisted' WHERE id=?", (post["id"],))
            con.commit()
            p = {"name": post["product_name"] or "", "headline": post["headline"] or ""}
            words = (post["title"] + "\n\n" if post["title"] and ch["kind"] in ("reddit", "hackernews") else "") + post["text"]
            return out({"ok": True, "assisted": True, "open": assisted_where(ch["kind"], ch, p), "copy": words,
                        "said": f"{KINDS[ch['kind']]['label']}: post it yourself (the words are on the clipboard), then Mark posted with its link."}) or 0
        try:
            rid, url = publish(ch, dict(post))
            con.execute("UPDATE posts SET status='posted', posted=?, remote_id=?, url=?, error='' WHERE id=?",
                        (time.time(), rid, url, post["id"]))
            con.commit()
            return out({"ok": True, "url": url, "said": f"Posted to {ch['name']}."}) or 0
        except Exception as e:
            con.execute("UPDATE posts SET status='failed', error=? WHERE id=?", (str(e), post["id"]))
            con.commit()
            return out({"ok": False, "said": f"{ch['name']}: {e}"}) or 0
    if cmd == "mark-posted":
        url = args[1] if len(args) > 1 else ""
        con.execute("UPDATE posts SET status='posted', posted=?, url=? WHERE id=?", (time.time(), url, int(args[0])))
        con.commit()
        return out({"ok": True}) or 0
    if cmd == "stats":
        got, missed = 0, 0
        for post in con.execute("SELECT * FROM posts WHERE status='posted' AND remote_id != ''").fetchall():
            ch = con.execute("SELECT * FROM channels WHERE id=?", (post["channel_id"],)).fetchone()
            if ch is None:
                continue
            try:
                n = numbers(ch, post)
            except Exception:
                n = None
            if n is None:
                missed += 1
                continue
            con.execute("INSERT INTO stats (post_id, at, likes, reposts, replies, views) VALUES (?,?,?,?,?,?)",
                        (post["id"], time.time(), n["likes"], n["reposts"], n["replies"], n["views"]))
            got += 1
        con.commit()
        return out({"counted": got, "missed": missed}) or 0
    if cmd == "report":
        latest = ("SELECT s.* FROM stats s JOIN (SELECT post_id, MAX(at) AS at FROM stats GROUP BY post_id) m "
                  "ON m.post_id=s.post_id AND m.at=s.at")
        posts = rows(con.execute(
            f"SELECT posts.id, posts.url, posts.posted, posts.status, channels.name AS channel, channels.kind, "
            f"products.name AS product, COALESCE(l.likes,0) likes, COALESCE(l.reposts,0) reposts, "
            f"COALESCE(l.replies,0) replies, COALESCE(l.views,0) views FROM posts "
            f"LEFT JOIN channels ON channels.id=posts.channel_id LEFT JOIN products ON products.id=posts.product_id "
            f"LEFT JOIN ({latest}) l ON l.post_id=posts.id WHERE posts.status='posted' ORDER BY posts.posted DESC"))

        def total(key):
            t = {}
            for p in posts:
                k = p[key] or "?"
                a = t.setdefault(k, {"name": k, "posts": 0, "likes": 0, "reposts": 0, "replies": 0, "views": 0})
                a["posts"] += 1
                for f in ("likes", "reposts", "replies", "views"):
                    a[f] += p[f]
            return sorted(t.values(), key=lambda a: -(a["likes"] + a["reposts"] * 2 + a["replies"] * 3))
        return out({"posts": posts, "channels": total("channel"), "products": total("product")}) or 0
    print(f"pat: no command {cmd!r} (pat.py with nothing after it lists them)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
