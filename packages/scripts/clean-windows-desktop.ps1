#Requires -Version 5.1
<#
.SYNOPSIS
  Remove Fox in the Box desktop data and Docker container for a clean reinstall.

.DESCRIPTION
  1. Quit Fox in the Box (tray) and exit the app completely before running.
  2. Optionally uninstall the app from Windows Settings > Apps (this script does not run the uninstaller).
  3. Run this script from PowerShell. Reinstall the app and/or pull the image again afterward.

  The NSIS installer leaves app data on disk by default (deleteAppDataOnUninstall: false).

.PARAMETER RemoveImage
  Also run: docker rmi ghcr.io/fox-in-the-box-ai/cloud:stable

.PARAMETER RemoveFoxintheboxDir
  Also remove %USERPROFILE%\.foxinthebox if present (used by CLI Docker example in README, not the default Electron bind mount).

.EXAMPLE
  .\clean-windows-desktop.ps1
.EXAMPLE
  .\clean-windows-desktop.ps1 -RemoveImage
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
  [switch] $RemoveImage,
  [switch] $RemoveFoxintheboxDir
)

$ErrorActionPreference = 'Stop'
$containerName = 'fox-in-the-box'
$imageRef = 'ghcr.io/fox-in-the-box-ai/cloud:stable'

# Electron userData bind mount (see packages/electron/src/docker-manager.js + main.js setName).
$electronData = Join-Path $env:APPDATA 'Fox in the box'

Write-Host 'Fox in the Box - clean desktop data' -ForegroundColor Cyan
Write-Host 'Ensure the Fox in the box app is fully quit (system tray).' -ForegroundColor Yellow
Write-Host ''

if ($PSCmdlet.ShouldProcess($containerName, 'docker rm -f')) {
  docker rm -f $containerName 2>$null
  if ($LASTEXITCODE -eq 0) { Write-Host "Removed container: $containerName" }
  else { Write-Host "Container $containerName not running or already removed." }
}

if ($RemoveImage) {
  if ($PSCmdlet.ShouldProcess($imageRef, 'docker rmi')) {
    docker rmi $imageRef 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Host "Removed image: $imageRef" }
    else { Write-Host "Image $imageRef not present or in use." }
  }
}

if (Test-Path -LiteralPath $electronData) {
  if ($PSCmdlet.ShouldProcess($electronData, 'Remove-Item -Recurse -Force')) {
    Remove-Item -LiteralPath $electronData -Recurse -Force
    Write-Host "Removed Electron user data: $electronData"
  }
}
else {
  Write-Host "No Electron user data at: $electronData"
}

if ($RemoveFoxintheboxDir) {
  $legacy = Join-Path $env:USERPROFILE '.foxinthebox'
  if (Test-Path -LiteralPath $legacy) {
    if ($PSCmdlet.ShouldProcess($legacy, 'Remove-Item -Recurse -Force')) {
      Remove-Item -LiteralPath $legacy -Recurse -Force
      Write-Host "Removed: $legacy"
    }
  }
}

Write-Host ''
Write-Host 'Next: install a fresh build from releases (or your installer), then start the app so Docker creates a new container.' -ForegroundColor Green
