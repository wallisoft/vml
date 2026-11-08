# Bob

**[Getting started](Getting-Started.md)** · **[Machines and SSH](Machines-and-SSH.md)** · **[Recipes](Recipes.md)** · **[GitHub](GitHub.md)** · **[Away from desk](Away-From-Desk.md)** · **[When it goes red](Troubleshooting.md)**

Bob builds your Visualised projects: Visualised itself, Mountie, Clever Clogs, anything with a recipe. One card for each build, on this computer or on any other machine you can reach over SSH: a Windows PC under the desk, a Linux box in the loft, a Mac. Press **Build** on one, or **Build all**, and watch each light go amber, then green.

## What you see

- **The project button** (top right, *Mountie ▾*): the projects Bob knows, and below them **New project**, **Edit this recipe…**, **Machines…** and **Set up…**.
- **The cards**: one per build. Its light, where it's built, the stage it's at, the last thing it said, and how long it's taken.
- **The tabs**: **GitHub** first (what's running in your repo's Actions, live), then a log for each build, a line at a time.
- **Builds** opens the folders the results are in. **Stop** stops whatever is building, on whichever machine it's on.
- **Away from desk** locks this computer and your Windows machines, and logs how long you were away.

## The kinds of build

| Kind | What it makes | Where |
|---|---|---|
| **compiled** | A program of its own, with its name and icon: a `.tar.gz` on Linux; on Windows a zip, a setup `.exe` and a Store `.msix` | the machine you name |
| **export** | The Visualised runtime with your project's files beside it, as the designer's Export makes. Seconds, no compiler | any machine, for any platform |
| **script** | A command of the project's own (Visualised builds itself this way) | this computer |
| **github** | A release on GitHub: tags the commit, pushes the tag, and follows the run live | GitHub Actions |

One build at a time on each machine: press two that want the same machine and the second waits its turn, saying so on its card.

Next: **[Getting started](Getting-Started.md)**.
