# How To Ship Updates to Your Users

## Introduction

Every Visualised app can tell its users when a newer version is out, and install it for them. It takes a few lines on the app's `@Window`: no server of your own, and no build step for apps that are a single `.vml` file. Users see a red or yellow ⚠ for releases that matter, can pick up the latest fixes from About, and can always go back.

## Prerequisites

- An app with a `Version=` on its `@Window` (use numbers like `1.4.0`).
- Somewhere for new versions to live: a public GitHub repository (recommended), or any website.

## Step 1: Add the app bar

```
@Window MyApp
Title=My App
Version=1.4.0
AppBar=true
Terms=https://example.com/terms
About=One or two lines about the app, shown in its About box.
UpdateFrom=github:you/myapp/MyApp.vml
```

`AppBar=true` puts a slim bar along the foot of the window: **Terms · About · v1.4.0**. If the form has a control called `StatusBar`, the pieces sit at its right-hand end instead of in a strip of their own. `Terms` and `About` are optional.

When a newer version is out, a ⚠ appears in the bar:

| What came out | Example (you have 1.4.0) | The bar |
|---|---|---|
| A new **major** version | 2.0.0 | red ⚠ 2.0.0 |
| A new **minor** version | 1.5.0 | yellow ⚠ 1.5.0 |
| A **fix** | 1.4.1 | nothing: About offers it |

Clicking the ⚠ installs it, after asking. About always lists what's on offer.

## Step 2: Say where updates come from (`UpdateFrom`)

### Option A: a .vml app kept on GitHub (recommended)

```
UpdateFrom=github:you/myapp/MyApp.vml
UpdateFrom=github:you/myapp/apps/MyApp.vml@stable      (a branch other than main)
```

The repo must be **public**. Two channels come from it:

- **Stable: your release tags.** Tag a release `v1.5.0` and every copy of the app sees it on its next start: red or yellow as above. Installing it takes that tag's copy of the file.
- **Edge: the newest file on the branch.** If the file on `main` has a higher `Version=` than any tag, About offers it as *Latest from main (not a release yet)*. It never turns the bar red or yellow: it's there for you, testers and keen users.

So: push a commit with `Version=1.5.1` and it's offered in About straight away (GitHub's cache can take a few minutes). Tag it `v1.5.1` when you're happy, and it becomes the stable fix. **Bump `Version=` in every commit you want offered**: it's how the app knows it's newer.

### Option B: an app with installers on GitHub releases

```
UpdateFrom=github:you/myapp-releases
```

For apps you package (a Windows installer, a Linux install script). The newest release is found from where its download points, so there's no API limit. Clicking the ⚠ downloads and runs that release's installer for this computer:

- Windows: `NAME-Setup.exe` (NAME is the app's `@Window` name), run quietly; the app closes.
- Linux: `install.sh`, then the app opens again.
- Phone or web: the release page (or `UpdateApk=` if you give one).

A handy pattern: keep the source private, and put just the installers in a public `-releases` repo.

### Option C: a .vml file on any website

```
UpdateFrom=https://example.com/downloads/MyApp.vml
UpdateApk=https://example.com/downloads/MyApp.apk
```

Only the start of the file is read to find its `Version=`. Installing downloads the whole file.

## Step 3: Release, and let users go back

Release a version by tagging it (Options A and B) or uploading the new file (Option C). Users see it the next time they start the app.


Every update keeps the previous copy beside the app as `MyApp.vml.bak`. About then offers **Go back to 1.4.0**. Going back swaps the two, so it can be undone as well.

## Good to know

- An app run from its source (`python3 vml.py MyApp.vml`) shows the ⚠ but won't overwrite your checkout: update it with git.
- Apps from the Microsoft Store are kept up to date by the Store; their ⚠ never shows.
- On a phone and on the web, the app follows the stable channel and opens the download; the edge channel and Go back are on the desktop.
- Version numbers are compared number by number: `1.10.0` is newer than `1.9.3`.

## Visualised itself

Visualised follows the same rules. Major and minor releases go to the Microsoft Store by themselves. Fixes reach everyone else at once through the designer's own bar, and the Store at its next minor release.

## Conclusion

Tags are your stable channel, the latest file on your branch is the edge channel that only keen users pick up, and every update can be undone. For phones, also see [How To Turn Your App into an Android App](How-To-Turn-Your-App-into-an-Android-App).
