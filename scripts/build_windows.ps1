<#
  Builds the Windows package into dist\TubeSnatch (+ a .zip).

  Two flavours:
    (default)     Portable build. Official, PSF-signed CPython runtime + the app, started through a
                  shortcut. Runs on PCs with Smart App Control / WDAC turned on, which block
                  unsigned self-built .exe files (including PyInstaller output).
    -PyInstaller  Classic PyInstaller folder with TubeSnatch.exe. Nicer, but it's an unsigned exe,
                  so Smart App Control blocks it. Use it for PCs without SAC.

  Nothing is installed system-wide. A portable uv.exe goes into .build\tools, CPython comes from
  python.org's NuGet package and FFmpeg from gyan.dev's release builds.

  Usage (PowerShell, or from WSL via scripts/build_windows.sh):
    powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 [-UpdateYtDlp] [-Clean] [-PyInstaller]
#>
param(
    [switch]$UpdateYtDlp,   # pull the newest yt-dlp before building (do this when downloads break)
    [switch]$Clean,         # wipe cached venv / downloads first
    [switch]$PyInstaller    # build a PyInstaller exe instead of the portable package
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root  = Split-Path -Parent $PSScriptRoot
$Build = Join-Path $Root ".build"
$Tools = Join-Path $Build "tools"
$Cache = Join-Path $Build "cache"
$Bin   = Join-Path $Build "bin"
$Dist  = Join-Path $Root "dist"
$App   = Join-Path $Dist "TubeSnatch"
Set-Location $Root

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Magenta }
function Need($code, $what) { if ($code) { throw "$what failed (exit $code)" } }

if ($Clean -and (Test-Path $Build)) { Step "Cleaning .build"; Remove-Item -Recurse -Force $Build }
New-Item -ItemType Directory -Force $Tools, $Cache, $Dist | Out-Null

# --- uv ---------------------------------------------------------------------
$Uv = Join-Path $Tools "uv.exe"
if (-not (Test-Path $Uv)) {
    Step "Downloading uv (https://github.com/astral-sh/uv)"
    $zip = Join-Path $Cache "uv.zip"
    Invoke-WebRequest "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" -OutFile $zip -UseBasicParsing
    Expand-Archive $zip -DestinationPath $Tools -Force
}
& $Uv --version
$env:UV_CACHE_DIR = Join-Path $Cache "uv"
$env:UV_PYTHON_DOWNLOADS = "never"
$env:UV_LINK_MODE = "copy"

# --- signed CPython (python.org NuGet package) -----------------------------
$PyOrgDir = Join-Path $Build "pyorg\tools"
$PyOrg = Join-Path $PyOrgDir "python.exe"
if (-not (Test-Path $PyOrg)) {
    Step "Downloading signed CPython 3.13 (python.org NuGet package)"
    $idx = Invoke-RestMethod "https://api.nuget.org/v3-flatcontainer/python/index.json"
    $pv = $idx.versions | Where-Object { $_ -match '^3\.13\.\d+$' } | Select-Object -Last 1
    $nup = Join-Path $Cache "python.$pv.zip"
    Invoke-WebRequest "https://api.nuget.org/v3-flatcontainer/python/$pv/python.$pv.nupkg" -OutFile $nup -UseBasicParsing
    Expand-Archive $nup -DestinationPath (Join-Path $Build "pyorg") -Force
}

if ($UpdateYtDlp) {
    Step "Upgrading yt-dlp to the latest release"
    & $Uv lock --upgrade-package yt-dlp --upgrade-package yt-dlp-ejs --upgrade-package deno
    Need $LASTEXITCODE "uv lock"
}

# --- FFmpeg (gyan.dev release essentials: widely used, so SAC trusts it) ----
$ffZip = Join-Path $Cache "ffmpeg-gyan-essentials.zip"
$ffDir = Join-Path $Cache "gyan"
if (-not (Test-Path $ffZip)) {
    Step "Downloading FFmpeg (https://www.gyan.dev/ffmpeg/builds/)"
    Invoke-WebRequest "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $ffZip -UseBasicParsing
}
if (-not (Get-ChildItem -Recurse -Filter ffmpeg.exe $ffDir -ErrorAction SilentlyContinue)) {
    Expand-Archive $ffZip -DestinationPath $ffDir -Force
}
$ffBin = (Get-ChildItem -Recurse -Filter ffmpeg.exe $ffDir | Select-Object -First 1).DirectoryName
if (Test-Path $Bin) { Remove-Item -Recurse -Force $Bin }
New-Item -ItemType Directory -Force $Bin | Out-Null
Copy-Item (Join-Path $ffBin "ffmpeg.exe"), (Join-Path $ffBin "ffprobe.exe") $Bin
$ffLicense = Join-Path (Split-Path $ffBin) "LICENSE"
if (Test-Path $ffLicense) { Copy-Item $ffLicense (Join-Path $Build "FFMPEG_LICENSE.txt") }

# --- icon -------------------------------------------------------------------
$version = (Select-String -Path "src\tubesnatch\__init__.py" -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
$Icon = Join-Path $Build "icon.ico"

if (Test-Path $App) { Remove-Item -Recurse -Force $App }

if (-not $PyInstaller) {
    # ======================= portable (default) ============================
    Step "Creating portable runtime (signed CPython $(& $PyOrg -c 'import platform;print(platform.python_version())'))"
    $Runtime = Join-Path $App "runtime"
    New-Item -ItemType Directory -Force $App | Out-Null
    Copy-Item -Recurse $PyOrgDir $Runtime
    $RtPy = Join-Path $Runtime "python.exe"

    Step "Installing app + dependencies into the runtime"
    $req = Join-Path $Build "requirements.txt"
    & $Uv export --frozen --no-dev --no-hashes --no-emit-project --format requirements-txt -o $req | Out-Null
    Need $LASTEXITCODE "uv export"
    & $Uv pip install --python $RtPy --break-system-packages --no-deps -r $req
    Need $LASTEXITCODE "uv pip install (deps)"
    & $Uv pip install --python $RtPy --break-system-packages --no-deps --reinstall-package tubesnatch .
    Need $LASTEXITCODE "uv pip install (app)"

    & $RtPy scripts\make_icon.py $Icon
    Need $LASTEXITCODE "icon"

    # deno.exe from the `deno` wheel lands in runtime\Scripts; move it next to ffmpeg
    Copy-Item (Join-Path $Runtime "Scripts\deno.exe") $Bin -Force

    Step "Trimming runtime"
    $trim = @("Lib\test", "Lib\idlelib", "Lib\tkinter", "Lib\turtledemo", "Lib\ensurepip", "Lib\lib2to3",
              "Lib\site-packages\pip", "include", "libs", "Scripts")
    foreach ($t in $trim) { $p = Join-Path $Runtime $t; if (Test-Path $p) { Remove-Item -Recurse -Force $p } }
    $pyside = Join-Path $Runtime "Lib\site-packages\PySide6"
    # Qt pieces this app never loads (keeps the folder ~40% smaller)
    Get-ChildItem $pyside -Include "Qt6Quick*", "Qt6Qml*", "Qt6Pdf*", "Qt6Designer*", "Qt6Help*", "Qt6Multimedia*",
        "Qt6ShaderTools*", "Qt6Sql*", "Qt6Test*", "Qt6OpenGL*", "Qt6Concurrent*", "Qt6Xml*", "Qt6VirtualKeyboard*",
        "QtQuick*", "QtQml*", "QtPdf*", "QtDesigner*", "QtHelp*", "QtMultimedia*", "QtSql*", "QtTest*",
        "QtOpenGL*", "QtConcurrent*", "QtXml*", "QtUiTools*", "QtDesigner*", "designer.exe", "linguist.exe",
        "assistant.exe", "lupdate.exe", "lrelease.exe", "qmlls.exe", "qmlformat.exe", "qmllint.exe", "balsam.exe",
        "balsamui.exe", "qsb.exe", "uic.exe", "rcc.exe", "opengl32sw.dll" -Recurse -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    foreach ($d in "qml", "translations", "metatypes", "include", "typesystems", "glue", "scripts", "examples") {
        $p = Join-Path $pyside $d; if (Test-Path $p) { Remove-Item -Recurse -Force $p }
    }
    & $RtPy -m compileall -q -j 0 (Join-Path $Runtime "Lib") | Out-Null

    Copy-Item -Recurse $Bin (Join-Path $App "bin")

    Step "Verifying runtime"
    & $RtPy -c "import tubesnatch, yt_dlp, PySide6.QtWidgets, PySide6.QtSvg, PySide6.QtNetwork; from tubesnatch import paths; print('yt-dlp', yt_dlp.version.__version__, '| ffmpeg', paths.ffmpeg_dir(), '| deno', paths.deno_path()); assert paths.ffmpeg_dir() and paths.deno_path()"
    Need $LASTEXITCODE "runtime check"
    Copy-Item $Icon (Join-Path $App "TubeSnatch.ico")

    # Launchers: a shortcut (nice icon) + a .cmd fallback + a helper to (re)create shortcuts
    @"
@echo off
rem Starts TubeSnatch with its bundled, signed Python runtime.
start "" "%~dp0runtime\pythonw.exe" -m tubesnatch %*
"@ | Set-Content -Encoding ascii (Join-Path $App "TubeSnatch.cmd")

    @'
@echo off
rem Creates "TubeSnatch" shortcuts here, on the Desktop and in the Start menu.
rem Run this again if you move the TubeSnatch folder.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d='%~dp0'.TrimEnd('\'); $ws=New-Object -ComObject WScript.Shell;" ^
  "foreach($p in @($d, [Environment]::GetFolderPath('Desktop'), (Join-Path ([Environment]::GetFolderPath('Programs')) ''))){" ^
  " $s=$ws.CreateShortcut((Join-Path $p 'TubeSnatch.lnk')); $s.TargetPath=(Join-Path $d 'runtime\pythonw.exe');" ^
  " $s.Arguments='-m tubesnatch'; $s.WorkingDirectory=$d; $s.IconLocation=(Join-Path $d 'TubeSnatch.ico');" ^
  " $s.Description='TubeSnatch - video and playlist downloader'; $s.Save() }"
echo Shortcuts created. You can start TubeSnatch from the Desktop or the Start menu.
pause
'@ | Set-Content -Encoding ascii (Join-Path $App "Create shortcuts.cmd")

    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut((Join-Path $App "TubeSnatch.lnk"))
    $lnk.TargetPath = Join-Path $Runtime "pythonw.exe"
    $lnk.Arguments = "-m tubesnatch"
    $lnk.WorkingDirectory = $App
    $lnk.IconLocation = Join-Path $App "TubeSnatch.ico"
    $lnk.Description = "TubeSnatch - video and playlist downloader"
    $lnk.Save()
    $flavour = "portable"
}
else {
    # ======================= PyInstaller ===================================
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $Build "venv-win"
    Step "Syncing build virtualenv"
    & $Uv sync --group build --python $PyOrg --frozen
    Need $LASTEXITCODE "uv sync"
    $Py = Join-Path $env:UV_PROJECT_ENVIRONMENT "Scripts\python.exe"
    & $Py scripts\make_icon.py $Icon
    $deno = & $Py -c "import deno; print(deno.find_deno_bin())"
    Copy-Item $deno (Join-Path $Bin "deno.exe")
    $v = ($version.Split(".") + @("0", "0", "0", "0"))[0..3] -join ", "
    $versionInfo = @"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($v), prodvers=($v)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('ProductName', 'TubeSnatch'),
    StringStruct('FileDescription', 'TubeSnatch - video and playlist downloader (yt-dlp GUI)'),
    StringStruct('FileVersion', '$version'),
    StringStruct('ProductVersion', '$version'),
    StringStruct('LegalCopyright', 'Built on yt-dlp, FFmpeg, Deno and Qt for Python - see THIRD_PARTY_NOTICES.md'),
    StringStruct('OriginalFilename', 'TubeSnatch.exe')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
"@
    [IO.File]::WriteAllText((Join-Path $Build "version_info.txt"), $versionInfo, (New-Object Text.UTF8Encoding $false))
    Step "Running PyInstaller"
    & $Py -m PyInstaller tubesnatch.spec --noconfirm --clean --log-level WARN --distpath $Dist --workpath (Join-Path $Build "pyi")
    Need $LASTEXITCODE "PyInstaller"
    $flavour = "pyinstaller"
}

foreach ($f in "README.md", "THIRD_PARTY_NOTICES.md") { Copy-Item $f $App }
if (Test-Path (Join-Path $Build "FFMPEG_LICENSE.txt")) { Copy-Item (Join-Path $Build "FFMPEG_LICENSE.txt") $App }

Step "Zipping"
$zipOut = Join-Path $Dist "TubeSnatch-$version-win64-$flavour.zip"
if (Test-Path $zipOut) { Remove-Item $zipOut }
Compress-Archive -Path $App -DestinationPath $zipOut -CompressionLevel Optimal

$appMB = "{0:N0} MB" -f ((Get-ChildItem -Recurse $App | Measure-Object Length -Sum).Sum / 1MB)
$zipMB = "{0:N0} MB" -f ((Get-Item $zipOut).Length / 1MB)
Write-Host "`nDone! ($flavour) $App  [$appMB]  ->  $zipOut [$zipMB]" -ForegroundColor Green
