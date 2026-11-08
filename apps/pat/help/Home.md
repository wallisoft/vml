# Pat

Pat is the driver and the accountant for whatever you make. Tell him about it once, and he drafts a post for every channel you're on, each shaped for where it's going. You change what you like and approve it; he sends it. Then he keeps the books: likes, shares, replies and views, per post, per channel and per product.

Nothing goes out without your say-so: a post is sent only once you've approved its exact words, and changing them afterwards sends it back to draft.

## Getting started

1. Open `apps/pat/Pat.vmlproj` (Pat runs from the Visualised repo: `PAT_REPO`, or the `pat_repo` preference, says where it is if it isn't `~/projects/vml-github`).
2. **Products** tab: a name, a link, a line, a few sentences and some tags. The drafts start from these, so the better they are, the less you'll change.
3. **Channels** tab: pick a kind, fill in what it asks for, **Add**, then **Test**: Pat logs in and says who you are there.
4. **Posts** tab: pick the product, **Draft for every channel**. Make each one yours, **Approve**, **Send**.
5. **Books** tab: **Count now** asks every platform for each post's numbers.

## The tabs

| Tab | What it's for |
|---|---|
| **Posts** | Every post, newest first. Pick one to change its words (a count against the channel's limit shows as you type), then Save, Approve, Send, Mark posted, Open or Remove. |
| **Books** | Totals per channel and per product, best first, and each posted post's latest numbers. Double-click a post to open it. |
| **Channels** | Where you post, and how Pat gets in. **Draft for it** switches a channel on or off for new drafts. |
| **Products** | What you're telling the world about. |

## Channels

**Pat posts these for you**

| Kind | What it needs |
|---|---|
| Mastodon | The server (mastodon.social) and an access token: Preferences, Development, New application, with `write:statuses` and `read:statuses`. |
| Bluesky | Your handle (you.bsky.social) and an app password: Settings, Privacy and security, App passwords. Links are made clickable. |
| dev.to | An API key: Settings, Extensions, DEV Community API Keys. Posts go up as articles, with their title and tags. |
| Facebook Page | The Page's id and a Page access token (Meta for Developers). A Page, not your own profile: Facebook lets no app post to a person's timeline. |

**You post these, Pat helps**

Quora, Reddit, Hacker News, LinkedIn and X want people, not bots (or charge for their posting API). For these, **Send** puts the words on your clipboard and opens the right page: a search for questions your product answers on Quora, your subreddit's submit page on Reddit, Show HN's submit page. Post it as yourself, then **Mark posted** with its link so it's in the books.

Pat's drafts for Quora and Reddit say you made the thing: those communities expect it, and it goes down better.

## The books

Pat keeps everything in one SQLite file, `~/.vml/pat/pat.db` (`PAT_DB` to put it elsewhere), readable by you alone, since it holds your channels' keys. Plain tables: `products`, `channels`, `posts`, `stats`. Every **Count now** adds a dated row per post to `stats`, so you can see how a post grew, not just where it ended.

Pat can count only what a platform will tell him: the posts you make by hand are in the books, but without numbers.

## Asking Pat from elsewhere

Pat has an API (see [The apps' API](../../../docs/App-API.md)): `python3 -m vml api pat report` from a terminal, or through TopCat from anywhere. Reading the books, drafting and editing are allowed; **approve** and **send** are "ask" commands, which need your yes each time.

## From a terminal

`tools/pat/pat.py` does the talking to the platforms; run it with nothing after it for its commands (`report`, `posts`, `draft`, `send`, `stats`...). Each answers in JSON.
