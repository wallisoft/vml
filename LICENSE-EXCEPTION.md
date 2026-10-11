# Visualised App Exception, version 1.0

Copyright (c) 2024-2026 Steve Wallis / Wallisoft

**Status: a draft, to be checked by a lawyer before it is relied on.** Its purpose is plain: an app you make with
Visualised is yours, to license as you like, even though it carries part of Visualised inside it.

This is an additional permission under section 7 of the GNU General Public License, version 3 ("GPLv3"), which is
the licence of Visualised (see [LICENSE](LICENSE)).

## What it covers

**The Visualised Runtime** is the part of Visualised that is copied into an app, or distributed with one, so that
the app can run:

- the page written by the web export (`vml/html.py`) and the support files it places inside that page
  (`vml/web`, `vml/lua`);
- the Android app in `android/`, and the template built from it, as placed inside an exported `.apk`;
- the compiled program distributed for Windows and Linux, as renamed and placed beside an exported app.

**An App** is what you make with Visualised: forms, projects, scripts, pictures and data (for example `.vml` and
`.vmlproj` files and what they refer to). The Visualised designer itself, and anything derived from it, is not an
App for this purpose.

## The permission

You may copy and distribute an App combined with, or accompanied by, the Visualised Runtime, as a web page, an
Android package or a Windows or Linux program, under terms of your own choosing, provided that:

1. the combination is not offered as a tool for designing Apps, in place of Visualised; and
2. if you change the Visualised Runtime itself, your changed Runtime stays under GPLv3 with this exception, and you
   make its source available as GPLv3 requires. Your App is not affected by this condition.

Your App (your forms, scripts and data) is yours. This licence makes no claim on it.

## Carrying it forward

If you distribute a changed version of Visualised, you may remove this exception from your version. If you do not
remove it, it applies to your version too.
