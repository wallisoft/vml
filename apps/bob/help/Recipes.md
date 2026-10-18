# Recipes

**[Home](Home.md)** · **[Getting started](Getting-Started.md)** · **[Machines and SSH](Machines-and-SSH.md)** · **[GitHub](GitHub.md)**

A recipe says what Bob builds for a project, and where. It's VML, read like a form: `recipe.vml` beside a project, or `NAME.recipe.vml` beside an app that shares its folder with others. **New project** writes one for you; **Edit this recipe…** opens it. Paths in it are relative to the recipe's own folder.

## The recipe

```
@Recipe Mountie
Version=Mountie.vml:Version
Project=Mountie.vmlproj
Icon=mountie.png
Company=Wallisoft
```

| Key | What it is |
|---|---|
| `Text` | the name Bob shows, when it isn't the same as the recipe's (spaces and all) |
| `Version` | `file:key`, where the version is read from (`Mountie.vml:Version`), or just a version (`1.0`) |
| `Project` | the `.vmlproj` (or a single `.vml`) |
| `Icon` | a `.png` (or `.svg`): the program's icon and the Store's tiles |
| `Company` | for the Windows program's properties |
| `Launcher` | a Python script to compile instead of the one Bob makes (rarely needed) |
| `Installer` | an Inno Setup script: a setup `.exe` with the Windows build |
| `Pip`, `Pip.Linux`, `Pip.Windows` | more Python packages the build needs, comma-separated |
| `PipOptional.Windows` | `package: --nuitka-flag`; tried, and its flag added only if it installed |
| `Nuitka`, `Nuitka.Linux`, `Nuitka.Windows` | more Nuitka flags (`--include-package=paramiko`) |
| `Extras.Linux`, `Extras.Windows` | files to bring back with the build (`install.sh`) |

## The Store package

```
@Msix Store
Manifest=../../packaging/mountie/AppxManifest.xml
Identity=tiny-web.mountie
Publisher=CN=9D975A63-49FD-4D19-812E-240C9F578F4E
PublisherDisplay=tiny-web
Copy=Mountie.exe > MountieAtBoot.exe
```

The identity and publisher come from Partner Center (your app > Product identity). The Windows build makes the `.msix` when the PC has the Windows SDK (`winget install Microsoft.WindowsSDK.10.0.22621`).

## The builds

Each `@Build` is a card, in the order they're written:

```
@Build Linux
Machine=here
Kind=compiled

@Build Windows
Machine=a8
Kind=compiled

@Build QuickExport
Text=Quick export
Machine=here
Kind=export
Platforms=linux, windows

@Build GitHub
Text=GitHub release
Kind=github
Tag=mountie-v{version}
Workflow=Mountie release
```

| Key | What it is |
|---|---|
| `Text` | the card's name, when it has spaces |
| `Machine` | a machine from machines.vml (`here` is this computer) |
| `Kind` | `compiled`, `export`, `script` or `github` (see [Home](Home.md)) |
| `Platforms` | (export) which: `linux, windows` |
| `Run` | (script) the command, run in the repo: `{host}` the machine's SSH name, `{version}`, `{install}` (empty, or `--no-install` when Bob's *Install it* tick is off) |
| `Results` | (script) where its results go, for the **Builds** button |
| `Tag`, `Workflow` | (github) the tag to make, `{version}` in it, and the Actions workflow it sets off |

## As JSON

Anything that wants JSON can have it: `python3 tools/bob/run.py --json apps/mountie/recipe.vml`. And back: `--to-vml recipe.json`.
