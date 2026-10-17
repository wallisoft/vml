# Build Visualised for Windows: run on the Windows box by tools/build-windows.sh, which sends the source here first.
# Same Nuitka command and smoke tests as the Windows job in .github/workflows/release.yml, so a green build here
# means the same thing. Works in ~\vml-build:  src.zip (the source)  ->  src\  ->  out\ (what goes back).
# Windows PowerShell 5.1 is enough: nothing PowerShell 7 only.
param([string]$Version = "0.0.0")
$ErrorActionPreference = "Continue"           # native programs write to stderr in passing: their exit codes decide
$root = Join-Path $HOME "vml-build"
$src = Join-Path $root "src"
$venv = Join-Path $root "venv"
$out = Join-Path $root "out"
$started = Get-Date
function Step($t) { Write-Host "==> $t" }
function Fail($t, $log) {
    Write-Host "FAILED: $t"
    if ($log -and (Test-Path $log)) { Get-Content $log | Select-Object -Last 40 }
    exit 1
}
Step "Visualised ${Version}: Windows build on $env:COMPUTERNAME"

# ---- the tools: Python 3.12 and Inno Setup, installed for this user the first time
function Find-Python {
    foreach ($p in "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe", "$env:ProgramFiles\Python312\python.exe") {
        if (Test-Path $p) { return $p }
    }
    $p = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $p) { return $p.Trim() }
    return $null
}
function Find-Iscc {
    foreach ($p in "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
                   "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") {
        if (Test-Path $p) { return $p }
    }
    return $null
}
$python = Find-Python
if (-not $python) {
    Step "Installing Python 3.12 (first time only)"
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
    $python = Find-Python
    if (-not $python) { Fail "Python 3.12 isn't installed and winget couldn't install it: install it on this PC by hand (python.org), then build again" }
}
$iscc = Find-Iscc
if (-not $iscc) {
    Step "Installing Inno Setup (first time only)"
    winget install -e --id JRSoftware.InnoSetup --silent --accept-package-agreements --accept-source-agreements | Out-Host
    $iscc = Find-Iscc
    if (-not $iscc) { Fail "Inno Setup isn't installed and winget couldn't install it: install it on this PC by hand (jrsoftware.org), then build again" }
}
Write-Host "    python: $python"
Write-Host "    inno setup: $iscc"

# Defender scans every file the C compiler writes, which makes a Nuitka build several times slower: leave the build
# folder and Nuitka's own (its compiler and cache) out of the scan. Needs admin; quietly skipped without.
try { Add-MpPreference -ExclusionPath $root, "$env:LOCALAPPDATA\Nuitka" -ErrorAction Stop } catch { }

# ---- the source
Step "Unpacking the source"
if (Test-Path $src) { Remove-Item -Recurse -Force $src }
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory $src, $out | Out-Null
tar -xf (Join-Path $root "src.zip") -C $src
if ($LASTEXITCODE -ne 0) { Fail "unpacking src.zip" }
Set-Location $src

# ---- the build venv, kept between builds
$vpy = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $vpy)) {
    Step "Making the build venv (first time only)"
    & $python -m venv $venv
    if ($LASTEXITCODE -ne 0) { Fail "making the venv" }
}
Step "Build requirements"
& $vpy -m pip install -q --upgrade pip
& $vpy -m pip install -q -r packaging\build-requirements.txt paramiko wsgidav cheroot
if ($LASTEXITCODE -ne 0) { Fail "installing the build requirements" }
& $vpy -m pip install -q winfspy 2>$null
$winfsp = @()
& $vpy -c "import winfspy" 2>$null
if ($LASTEXITCODE -eq 0) { $winfsp = @("--include-package=winfspy") } else { Write-Host "    (no winfspy: SSH drives will use WebDAV only in this build)" }

# ---- compile
Step "Compiling with Nuitka (the first build fetches its compiler and takes a while; later ones use its cache)"
$numeric = ($Version -split "[-+]")[0]                  # Windows file versions are numbers only: 1.5.0-dev.x -> 1.5.0
& $vpy -m nuitka --standalone --assume-yes-for-downloads --enable-plugin=pyside6 `
    --windows-console-mode=attach --windows-icon-from-ico=packaging/art/vml.ico `
    --include-package=vml --include-package=lupa `
    --include-package=paramiko --include-package=wsgidav --include-package-data=wsgidav --include-package=cheroot @winfsp `
    --include-data-dir=designer=designer --include-data-dir=vml/lua=lua --include-data-dir=vml/web=web `
    --include-data-dir=csharp=csharp `
    --company-name=Wallisoft --product-name=Visualised `
    --file-version=$numeric --product-version=$numeric `
    --output-filename=vml.exe --output-dir=build vml.py
if ($LASTEXITCODE -ne 0 -or -not (Test-Path build\vml.dist\vml.exe)) { Fail "Nuitka" }

# ---- smoke tests (the release job's)
Step "Smoke tests"
$env:QT_QPA_PLATFORM = "offscreen"
$t = Join-Path $root "smoke"
if (Test-Path $t) { Remove-Item -Recurse -Force $t }
New-Item -ItemType Directory $t | Out-Null
$exe = (Resolve-Path build\vml.dist\vml.exe).Path
function Shot($what, $exePath, $argList, $png) {
    $log = Join-Path $t "$png.log"
    $p = Start-Process $exePath -ArgumentList ($argList + @("--shot", (Join-Path $t $png))) -NoNewWindow -PassThru `
        -RedirectStandardError $log -RedirectStandardOutput "$log.out"
    if (-not $p.WaitForExit(120000)) { $p.Kill(); Fail "$what (still running after 2 minutes)" $log }
    if (-not (Test-Path (Join-Path $t $png))) { Fail $what $log }
}
Start-Process $exe -ArgumentList "parse", "tests\step1.vml" -Wait -NoNewWindow -RedirectStandardOutput "$t\parse.txt"
if (-not (Select-String -Path "$t\parse.txt" -Pattern "INSERT INTO ui_tree" -Quiet)) {
    Fail "parse (if Windows said it blocked vml.exe, Smart App Control is on: Windows Security, App & browser control)" "$t\parse.txt"
}
Shot "opening a form" $exe @("tests\step1.vml") "form.png"
Shot "opening the designer" $exe @() "designer.png"
Shot "a form that runs a script" $exe @("build\vml.dist\designer\databases.vml") "script.png"
Copy-Item -Recurse build\vml.dist "$t\app"
Rename-Item "$t\app\vml.exe" SmokeApp.exe
Copy-Item tests\step1.vml "$t\app\SmokeApp.vml"
$env:VML_DEBUG = "1"
Shot "an exported app running its own form" "$t\app\SmokeApp.exe" @() "app.png"
if (-not (Select-String -Path "$t\app.png.log" -Pattern "SmokeApp.vml: Parsed" -Quiet)) { Fail "an exported app running its own form" "$t\app.png.log" }
Remove-Item Env:VML_DEBUG
Shot "running a project" $exe @("tests\project\Demo.vmlproj") "proj.png"
if (Select-String -Path "$t\proj.png.log" -Pattern "module helpers.lua" -Quiet) { Fail "the project's module didn't load" "$t\proj.png.log" }
Remove-Item Env:QT_QPA_PLATFORM
$d = "build\vml.dist"
foreach ($f in "csharp\VmlCSharpHost\VmlCSharpHost.csproj", "designer\importers\winforms.vml", "designer\importers\vb6.vml",
               "designer\importers\lib\importkit.lua", "designer\Designer.vmlproj", "designer\designer.vml",
               "designer\databases.vml", "designer\modules\files.lua", "designer\modules\project.lua",
               "designer\modules\app.lua", "web\android-template.apk") {
    if (-not (Test-Path "$d\$f")) { Fail "missing from the build: $f" }
}
Write-Host "    all passed"

# ---- the installer, the portable zip, and the Store package if this PC can make one
Step "Visualised-Setup.exe"
& $iscc /Q "/DAppVersion=$Version" packaging\vml.iss
if ($LASTEXITCODE -ne 0) { Fail "Inno Setup" }
Copy-Item packaging\Output\Visualised-Setup.exe $out

Step "vml-windows-x64.zip"
$stage = Join-Path $root "stage"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory $stage | Out-Null
Copy-Item -Recurse build\vml.dist "$stage\vml"
Copy-Item packaging\THIRD-PARTY-NOTICES.txt "$stage\vml\"
Copy-Item LICENSE "$stage\vml\LICENSE.txt"; Copy-Item LICENSE-EXCEPTION.md "$stage\vml\"
tar -a -cf "$out\vml-windows-x64.zip" -C $stage vml
if ($LASTEXITCODE -ne 0) { Fail "the zip" }

$msix = Join-Path $root "msix.json"
$makeappx = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\makeappx.exe" -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not (Test-Path $msix)) {
    Write-Host "==> (no Store package: the MSIX names weren't sent)"
} elseif (-not $makeappx) {
    Write-Host "==> (no Store package: this PC has no makeappx. winget install Microsoft.WindowsSDK.10.0.26100 adds it)"
} else {
    Step "Visualised.msix"
    $m = Get-Content $msix -Raw | ConvertFrom-Json
    $p = @($numeric.Split(".")); while ($p.Count -lt 3) { $p += "0" }
    $v = "$($p[0]).$($p[1]).$($p[2]).0"
    $pk = Join-Path $root "msix-stage"
    if (Test-Path $pk) { Remove-Item -Recurse -Force $pk }
    New-Item -ItemType Directory "$pk\Assets" -Force | Out-Null
    Copy-Item -Recurse build\vml.dist\* $pk
    Copy-Item packaging\THIRD-PARTY-NOTICES.txt $pk
    Copy-Item LICENSE "$pk\LICENSE.txt"; Copy-Item LICENSE-EXCEPTION.md $pk
    & $vpy packaging/make_icon.py "$pk\Assets\Square150x150Logo.png" 150
    & $vpy packaging/make_icon.py "$pk\Assets\Square44x44Logo.png" 44
    & $vpy packaging/make_icon.py "$pk\Assets\StoreLogo.png" 50
    $x = Get-Content packaging\AppxManifest.xml -Raw
    $x = $x.Replace("@IDENTITY_NAME@", $m.id).Replace("@PUBLISHER@", $m.publisher).Replace("@PUBLISHER_DISPLAY@", $m.publisher_display)
    $x = $x.Replace("@DISPLAY_NAME@", $m.name).Replace("@VERSION@", $v)
    [IO.File]::WriteAllText("$pk\AppxManifest.xml", $x)          # (UTF-8, no BOM, as the release job writes it)
    & $makeappx.FullName pack /d $pk /p "$out\Visualised.msix" /o | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "makeappx" }
}

$took = (Get-Date) - $started
Step ("Built in {0}m {1}s" -f [int][math]::Floor($took.TotalMinutes), $took.Seconds)
