# Downloads a PINNED, checksum-verified pixi binary (BSD-3, from prefix.dev)
# into .pixi-bin next to this script. Called by install.bat. Kept as a separate
# file so batch-file caret-escaping doesn't corrupt the PowerShell.
#
# Security: we pin an exact pixi version and its official SHA256. The downloaded
# zip is hashed and compared BEFORE extraction; a mismatch aborts. This protects
# users even where plain HTTPS wouldn't -- e.g. a corporate TLS-intercepting
# proxy, or a compromised "latest" release. To move to a newer pixi, update
# BOTH $version and $expectedSha below (get the hash from the release's
# pixi-x86_64-pc-windows-msvc.zip.sha256 file on GitHub).
$ErrorActionPreference = 'Stop'

$version     = 'v0.71.3'
$expectedSha = 'c2e4e8b72ef189bd7ca9046af0f2dad7572013a610c01da76da1ddacacb0bdc1'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$dst  = Join-Path $here '.pixi-bin'
New-Item -ItemType Directory -Force -Path $dst | Out-Null
$exe = Join-Path $dst 'pixi.exe'
if (Test-Path $exe) { Write-Host 'pixi already present'; exit 0 }

$url = "https://github.com/prefix-dev/pixi/releases/download/$version/pixi-x86_64-pc-windows-msvc.zip"
$zip = Join-Path $env:TEMP "pixi_dl_$version.zip"

Write-Host "Downloading pixi $version ..."
Invoke-WebRequest -UseBasicParsing $url -OutFile $zip

# verify the downloaded bytes match the pinned hash BEFORE extracting anything
$actualSha = (Get-FileHash -Algorithm SHA256 -Path $zip).Hash.ToLower()
if ($actualSha -ne $expectedSha.ToLower()) {
    Remove-Item $zip -ErrorAction SilentlyContinue
    throw ("pixi download failed verification.`n" +
           "  expected SHA256: $expectedSha`n" +
           "  got:             $actualSha`n" +
           "The file did not match the known-good pixi $version. Aborting for " +
           "safety. This can mean a network/proxy tampered with the download, " +
           "or the pinned version/hash in get_pixi.ps1 is out of date.")
}
Write-Host 'Checksum OK.'

Expand-Archive -Force $zip $dst
Remove-Item $zip -ErrorAction SilentlyContinue
if (-not (Test-Path $exe)) { throw 'pixi.exe not found after extraction' }
Write-Host 'pixi ready'
