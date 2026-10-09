$ErrorActionPreference = "Stop"
$pythonExecutable = (Get-Command python -ErrorAction Stop).Source
$pythonDirectory = Split-Path $pythonExecutable
$originalPath = $env:PATH
$originalQtPluginPath = $env:QT_PLUGIN_PATH
$originalQmlImportPath = $env:QML2_IMPORT_PATH

Push-Location $PSScriptRoot
try {
    $version = & $pythonExecutable -c "from ytdlp_gui import __version__; print(__version__)"
    if ($LASTEXITCODE -ne 0) { throw "Could not determine application version" }
    $applicationName = "yt-dlp-gui-v$version"
    # PyInstaller resolves DLLs through PATH. Foreign ICU/Qt DLLs can silently
    # replace Windows dependencies and produce an executable that cannot start.
    $env:PATH = "$pythonDirectory;$pythonDirectory\Scripts;$env:SystemRoot\System32;$env:SystemRoot"
    $env:QT_PLUGIN_PATH = $null
    $env:QML2_IMPORT_PATH = $null
    & $pythonExecutable -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --noupx `
        --name $applicationName `
        "run_gui.py"

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }

    & $pythonExecutable scripts\verify_packaged.py "dist\$applicationName.exe"
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged application failed its startup check; do not publish this executable"
    }
    Write-Host "Built and verified: $PSScriptRoot\dist\$applicationName.exe"
}
finally {
    Pop-Location
    $env:PATH = $originalPath
    $env:QT_PLUGIN_PATH = $originalQtPluginPath
    $env:QML2_IMPORT_PATH = $originalQmlImportPath
}
