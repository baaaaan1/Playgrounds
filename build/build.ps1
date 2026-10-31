param(
    [switch]$SkipTests,
    [switch]$Installer
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

try {
    if (-not $SkipTests) {
        Write-Host "==> tests"
        python -m pytest
        if ($LASTEXITCODE -ne 0) { throw "tests failed" }
        Write-Host "==> lint"
        python -m ruff check .
        if ($LASTEXITCODE -ne 0) { throw "lint failed" }
    }

    Write-Host "==> icon"
    python build\make_icon.py

    Write-Host "==> pyinstaller (onedir)"
    python -m PyInstaller --noconfirm --clean build\playgrounds.spec
    if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }

    Write-Host "==> smoke test packaged exe"
    & "$root\dist\Playgrounds\Playgrounds.exe" --smoke
    if ($LASTEXITCODE -ne 0) { throw "packaged smoke test failed" }

    Write-Host "Built dist\Playgrounds\Playgrounds.exe"

    if ($Installer) {
        $wix = Get-Command wix -ErrorAction SilentlyContinue
        if (-not $wix) {
            throw "WiX Toolset v4+ (wix.exe) is required. Install with: dotnet tool install --global wix"
        }
        $version = python -c "import app; print(app.__version__)"
        if ($LASTEXITCODE -ne 0) { throw "cannot read version" }

        Write-Host "==> msi ($version)"
        & wix build `
            -arch x64 `
            -d "SourceDir=$root\dist\Playgrounds" `
            -d "Version=$version" `
            -o "$root\dist\Playgrounds-$version-x64.msi" `
            "$root\build\installer\Product.wxs"
        if ($LASTEXITCODE -ne 0) { throw "wix build failed" }

        Write-Host "Built dist\Playgrounds-$version-x64.msi"
    }
}
finally {
    Pop-Location
}
