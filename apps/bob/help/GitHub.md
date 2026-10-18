# GitHub

**[Home](Home.md)** · **[Getting started](Getting-Started.md)** · **[Recipes](Recipes.md)** · **[When it goes red](Troubleshooting.md)**

## The GitHub tab

With the `gh` command signed in (`gh auth login`, see [Getting started](Getting-Started.md)), the **GitHub** tab shows your repo's last eight Actions runs: ✓ green, ✗ failed, ● running, ○ waiting, with their tag and when. Under them, the run going now, job by job. Bob looks every ten seconds while something's running and every half minute otherwise; the top line says when he last did.

When a run starts or finishes, Bob comes to the front on the GitHub tab and says so in a notification, whoever started it: you, Bob, or a colleague.

## Releases from Bob

A `github` build in a recipe makes a release:

```
@Build GitHub
Text=GitHub release
Kind=github
Tag=mountie-v{version}
Workflow=Mountie release
```

Press its **Release** button and Bob asks first, then:

1. checks everything's committed (a release is built from what's on GitHub, not what's in your folder),
2. pushes your branch if GitHub hasn't got your latest commits,
3. tags the commit (`mountie-v1.2.4`, from the version in the recipe) and pushes the tag,
4. finds the run the tag starts, and follows it on the card, job by job, till it's green (or red, with a link to it).

**Stop** cancels the run on GitHub. A release is never part of **Build all**: only its own button does it.

## Fixes, without the clean build

A clean build on GitHub takes a quarter of an hour, and a fix (1.5.1) rarely needs one: you've built and tried it here already. Name the builds whose results should go up, and a fix is released from them:

```
@Build GitHub
Text=GitHub release
Kind=github
Tag=v{version}
Workflow=Release
Assets=Linux, Windows
AssetsRepo=wallisoft/vml-releases
AssetFiles=packaging/install.sh
```

Raise the version to 1.5.1, commit, press **Build all**, then **Release**. Bob checks each named build is newer than your last commit, tags `v1.5.1`, and publishes those files as a **pre-release**. Apps find it (a fix shows in their About box, with Install); the website's downloads, which follow GitHub's *latest* release, stay on the last clean one. A version ending in .0 still goes the clean way, through the workflow.

## Good to know

- **Raise the version first.** A tag is made once: if GitHub has the tag already, Bob follows its run rather than making another. If the tag is in your folder but not on GitHub (an old one), Bob says so: remove it (`git tag -d mountie-v1.2.3`) or raise the version.
- **Which workflow**: the one whose `on: push: tags:` matches the tag. `Workflow=` is its `name:`.
