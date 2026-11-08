# Getting started with Bob

**[Home](Home.md)** · **[Machines and SSH](Machines-and-SSH.md)** · **[Recipes](Recipes.md)** · **[GitHub](GitHub.md)**

## Introduction

Ten minutes: tell Bob where your projects are, make a recipe for one, and build it on this computer. Then, if you like, sign in to GitHub so Bob can watch your Actions and make releases.

## Prerequisites

- Visualised, and the folder your projects live in (a git repo, usually). Bob's tools are in its `tools/bob` folder.
- Python 3.10 or later (`python3 --version`). On Ubuntu, also `sudo apt install python3-venv python3-dev patchelf` for compiled builds.

## Step 1: Where your projects are

Open Bob. If the project button says *no projects*, click it, choose **Set up…**, and give the folder with `tools/bob` in it (`~/projects/vml-github` unless you say otherwise).

## Step 2: A recipe for a project

Click the project button, then **New project**: it lists every project (`.vmlproj`) and every app (a `.vml` with a window and a version) that hasn't a recipe yet. Pick one. Bob writes its recipe beside it, with three builds:

- **Linux**, compiled, on this computer
- **Windows**, compiled, on your first Windows machine (see [Machines and SSH](Machines-and-SSH.md))
- **Quick export**, for Linux and Windows

**Edit this recipe…** opens it in your text editor. It's VML, like a form: [Recipes](Recipes.md) has everything that can go in it.

## Step 3: Build

Press **Build** on the **Quick export** card. The light goes amber, the stage changes as it goes (the first time it downloads the runtimes), and in under a minute it's green. **Builds** opens the folder: a zip for Windows, a `.tar.gz` for Linux, each ready to hand to someone.

A **compiled** build takes longer (the first one makes its own build tools, a few minutes; after that the compiler's cache makes it quicker) and gives a real program of its own, smoke-tested: it's opened once, out of sight, to be sure it starts.

## Step 4: GitHub (optional)

Bob watches your repo's GitHub Actions with the `gh` command, and can make releases. Install it and sign in once:

```
sudo apt install gh
gh auth login
```

Choose **GitHub.com**, **SSH** (or HTTPS), and **Login with a web browser**. Then the **GitHub** tab fills within half a minute. More in [GitHub](GitHub.md).

## Conclusion

That's Bob: a recipe per project, a card per build. Add another computer to build on in [Machines and SSH](Machines-and-SSH.md).
