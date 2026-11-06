param(
    [switch]$SkipTests,
    [switch]$Installer,
    [string]$ReleaseTag,
    [string]$Notes = "",
    [string]$SigningCertificateThumbprint,
    [string]$SignTool = "signtool.exe",
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [string]$OutputDir
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputDir) { $OutputDir = Join-Path $root "dist" }
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)

function Invoke-CodeSign([string]$Path) {
    if (-not $SigningCertificateThumbprint) { return }
    & $SignTool sign /sha1 $SigningCertificateThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $Path
    if ($LASTEXITCODE -ne 0) { throw "code signing failed: $Path" }
    & $SignTool verify /pa /all $Path
    if ($LASTEXITCODE -ne 0) { throw "signature verification failed: $Path" }
}

Push-Location $root

try {
    $runningOutput = Get-Process -Name Playgrounds -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq "$OutputDir\Playgrounds\Playgrounds.exe" }
    if ($runningOutput) {
        throw "The output application is running. Close it first or choose a different -OutputDir."
    }

    if ($Installer) {
        $wixCommand = Get-Command wix -CommandType Application -ErrorAction SilentlyContinue
        $wix = if ($wixCommand) { $wixCommand.Source } else {
            Join-Path $env:USERPROFILE ".dotnet\tools\wix.exe"
        }
        if (-not (Test-Path -LiteralPath $wix -PathType Leaf)) {
            throw "WiX Toolset v5+ (wix.exe) is required. Release CI uses: dotnet tool install --global wix --version 5.0.2"
        }
    }

    $releaseArgs = @()
    if ($ReleaseTag) { $releaseArgs += @("--release-tag", $ReleaseTag, "--check-source") }
    $version = python build\release.py @releaseArgs
    if ($LASTEXITCODE -ne 0) { throw "invalid release version or tag" }

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
    if ($LASTEXITCODE -ne 0) { throw "icon generation failed" }

    Write-Host "==> pyinstaller (onedir)"
    python -m PyInstaller --noconfirm --clean --distpath $OutputDir build\playgrounds.spec
    if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }

    Invoke-CodeSign "$OutputDir\Playgrounds\Playgrounds.exe"

    Write-Host "==> smoke test packaged exe"
    foreach ($mode in @("--smoke", "--smoke-native")) {
        python -c "import subprocess, sys; code = subprocess.run([sys.argv[1], sys.argv[2]], timeout=30).returncode; print(sys.argv[2], 'exit:', code); sys.exit(code)" "$OutputDir\Playgrounds\Playgrounds.exe" $mode
        if ($LASTEXITCODE -ne 0) { throw "packaged smoke test failed ($mode)" }
    }

    Write-Host "Built $OutputDir\Playgrounds\Playgrounds.exe"

    if ($Installer) {
        Write-Host "==> msi ($version)"
        & $wix build `
            -arch x64 `
            -d "SourceDir=$OutputDir\Playgrounds" `
            -d "Version=$version" `
            -o "$OutputDir\Playgrounds-$version-x64.msi" `
            "$root\build\installer\Product.wxs"
        if ($LASTEXITCODE -ne 0) { throw "wix build failed" }

        Invoke-CodeSign "$OutputDir\Playgrounds-$version-x64.msi"

        $manifestArgs = @("--asset", "$OutputDir\Playgrounds-$version-x64.msi", "--output", "$OutputDir\update.json")
        if ($Notes) { $manifestArgs += @("--notes", $Notes) }
        if ($ReleaseTag) { $manifestArgs += @("--package-release", "--release-dir", "$OutputDir\release") }
        python build\release.py @releaseArgs @manifestArgs
        if ($LASTEXITCODE -ne 0) { throw "update manifest generation failed" }

        Write-Host "Built $OutputDir\Playgrounds-$version-x64.msi"
        if ($ReleaseTag) {
            Write-Host "Release assets: $OutputDir\release\ (final hashes; do not modify or sign afterwards)"
        } else {
            Write-Host "Generated $OutputDir\update.json"
        }
    }
}
finally {
    Pop-Location
}
