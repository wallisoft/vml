# When it goes red

**[Home](Home.md)** · **[Machines and SSH](Machines-and-SSH.md)** · **[Recipes](Recipes.md)** · **[GitHub](GitHub.md)**

A red card says why on its second line, and its log tab has every line. The logs are kept too, in `~/.cache/bob/logs`.

| It says | What to do |
|---|---|
| *can't reach a8 over SSH* | The machine's asleep or off, or SSH asks for a password: `ssh a8 hostname` should answer without one ([Machines and SSH](Machines-and-SSH.md)) |
| *Waiting: Mountie Linux is building on here* | Not an error: one build at a time on each machine, and this one's next |
| *making the venv* | On Ubuntu: `sudo apt install python3-venv python3-dev` |
| *requires 'patchelf'* | `sudo apt install patchelf` (Bob uses the pip one when there's none, so this is rare) |
| *didn't open its window* | The program built, but failed as it started: the log's last lines say why (a missing package: add it to `Pip` and `Nuitka` in the recipe) |
| *no Inno Setup / no Windows SDK* | Not an error: the zip is made, the setup `.exe` or `.msix` isn't. Install them on the PC (`winget install JRSoftware.InnoSetup`, `winget install Microsoft.WindowsSDK.10.0.22621`) |
| *changes not committed yet* | A GitHub release builds what's on GitHub: commit first |
| *the tag … is here but not on GitHub* | An old tag: `git tag -d` it, or raise the version |
| *GitHub isn't answering Bob* (GitHub tab) | `gh auth login`, or `sudo apt install gh` |

Still red? **Stop**, then build again: a first build on a new machine sometimes needs a second go while Windows finishes installing what it fetched.
