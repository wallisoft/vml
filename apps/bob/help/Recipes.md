# Recipes

**[Home](Home.md)** · **[Getting started](Getting-Started.md)** · **[Machines and SSH](Machines-and-SSH.md)** · **[GitHub](GitHub.md)**

A recipe says what Bob builds for a project, and where. It's VML, read like a form: `recipe.vml` beside a project, or `NAME.recipe.vml` beside an app that shares its folder with others. **New project** writes one for you (for a Visualised project, or any project folder); **Recipe and build files…** opens it, with the scripts it uses. Paths in it are relative to the recipe's own folder.

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
| `Kind` | `compiled`, `export`, `command`, `script` or `github` (see [Home](Home.md)) |
| `Platforms` | (export) which: `linux, windows` |
| `Run` | (command) what builds it, run in the project's folder on the build's machine; `Run.Windows` / `Run.Linux` for one OS only. (script) a command run here, in the repo: `{host}` the machine's SSH name, `{version}`, `{install}` (empty, or `--no-install` when Bob's *Install it* tick is off) |
| `Results` | (command) what it made, from the project's folder: files or folders, commas between, wildcards fine (`dist`, `target/release/app`); `Results.Windows` too. (script) where its results go, for the **Builds** button |
| `Tag`, `Workflow` | (github) the tag to make, `{version}` in it, and the Actions workflow it sets off |

## Any framework

Bob isn't only for Visualised. A `command` build runs any build tool: Bob sends the project (what git tracks, and anything new it isn't told to ignore) to the machine, runs the command in its folder, and brings back what `Results` names.

```
@Recipe Shop
Version=package.json:version

@Build Linux
Machine=here
Kind=command
Run=npm ci && npm run build
Results=dist

@Build Windows
Machine=a8
Kind=command
Run=npm ci && npm run build
Results=dist
```

**Project ▾ > New project > From a folder…** looks at a folder and writes a recipe like that for you:

| It finds | It builds with | And brings back |
|---|---|---|
| `package.json` | `npm ci && npm run build` | `dist` |
| `Cargo.toml` | `cargo build --release` | the program from `target/release` |
| `go.mod` | `go build -o out/ ./...` | `out` |
| a `.csproj` or `.sln` | `dotnet publish -c Release -o out` | `out` |
| `pubspec.yaml` | `flutter build linux` / `flutter build windows` | the bundle |
| `pyproject.toml` or `setup.py` | `python -m build` | `dist` |
| a `Makefile` | `make` | `build` |
| a `.vmlproj` | Visualised's own builds | |

The version comes from where that framework keeps it (`package.json:version`, `Cargo.toml:version`...). It's a starting point: change `Run` and `Results` to suit. The machine needs the build tool itself (Node, Rust, the .NET SDK...): Bob brings the project, not the tools.

On Windows the command runs in PowerShell; `&&` works there too (Bob runs each part and stops at the first that fails).

## The recipe editor

**Project ▾ > Recipe and build files…** opens the recipe beside everything its builds use: the scripts `Run` names, and the files those scripts name in turn (for Visualised: `build-local.sh`, `build-windows.sh`, `build-windows.ps1`, `build-requirements.txt`, the installer...), and the project's own build file (`package.json`, `Makefile`...). Change any of them, then **Save**, or **Save, then Build all** to see it work at once. Saving the recipe, Bob reads it again straight away.

**Clear its build environment…** starts a machine afresh: Bob's Python environment and build folders there are deleted, and the next build makes them again (taking longer, the once). For when an upgrade (a new Python, a new Nuitka) leaves a machine in a muddle. Your project isn't touched.

## As JSON

Anything that wants JSON can have it: `python3 tools/bob/run.py --json apps/mountie/recipe.vml`. And back: `--to-vml recipe.json`.
