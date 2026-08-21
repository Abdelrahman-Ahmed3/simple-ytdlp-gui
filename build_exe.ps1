$ErrorActionPreference = "Stop"
$buildDirectory = Join-Path $PSScriptRoot "build"
$specFile = Join-Path $PSScriptRoot "yt-dlp-gui-v0.1.4.spec"

Push-Location $PSScriptRoot
try {
    python -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --name "yt-dlp-gui-v0.1.4" `
        "run_gui.py"

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }

    Write-Host "Built: $PSScriptRoot\dist\yt-dlp-gui-v0.1.4.exe"
}
finally {
    Pop-Location
    if (Test-Path -LiteralPath $buildDirectory) {
        Remove-Item -LiteralPath $buildDirectory -Recurse -Force
    }
    if (Test-Path -LiteralPath $specFile) {
        Remove-Item -LiteralPath $specFile -Force
    }
}
