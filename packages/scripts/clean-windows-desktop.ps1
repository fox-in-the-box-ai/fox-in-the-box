#Requires -Version 5.1
<#
.SYNOPSIS
  Nuclear cleanup for Fox in the Box on Windows — container, image, data, install.

.DESCRIPTION
  Removes everything Fox in the Box puts on a Windows machine, in the right order
  to survive locked LevelDB files, auto-restarting tray processes, and the
  Docker Desktop bind-mount lifecycle. Battle-tested against the v0.7.17 → v0.7.18
  cleanup mess that motivated this rewrite (see GitHub issues #341 + #340).

  Default behavior (no flags) does FULL nuclear cleanup:
    1. Stop every Fox / Electron / @fox-in-the-box process
    2. Stop + remove the `fox-in-the-box` container
    3. Untag every known Fox cloud image (`:stable`, `:v0.7.*`, `:latest`)
    4. Prune dangling Docker volumes
    5. Run the bundled NSIS uninstaller silently if present
    6. Remove `%APPDATA%\@fox-in-the-box` (Electron userData + container bind mount)
    7. Remove `%LOCALAPPDATA%\@fox-in-the-boxelectron-updater` (auto-updater state)
    8. Remove `%LOCALAPPDATA%\Programs\@fox-in-the-boxelectron` (install dir)
    9. Verify clean state and report

  After this script: Fox is GONE from the system. Reinstall fresh from
  https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/latest

  When the in-app "Tray → Reset Fox completely…" menu (v0.7.18+) suffices,
  use that instead — this script is for when Fox won't launch at all or the
  in-app reset failed (e.g. cross-version upgrade gone wrong).

.PARAMETER KeepData
  Skip step 6 — preserve %APPDATA%\@fox-in-the-box (onboarding state, settings,
  conversation history, local models). Useful when you want to reset Docker
  state only but keep your provider keys + chat history.

.PARAMETER KeepInstall
  Skip steps 5 + 8 — leave the Fox application installed. Useful when you
  want to reset state without uninstalling the app itself.

.PARAMETER WhatIf
  Show what WOULD be removed without actually removing anything.

.EXAMPLE
  # Full nuclear cleanup — most common use
  .\clean-windows-desktop.ps1

.EXAMPLE
  # Reset Docker container + image + Fox data, but leave the Fox app installed
  .\clean-windows-desktop.ps1 -KeepInstall

.EXAMPLE
  # Reset Docker only, preserve all Fox app data + the app itself
  .\clean-windows-desktop.ps1 -KeepData -KeepInstall

.EXAMPLE
  # Preview without making changes
  .\clean-windows-desktop.ps1 -WhatIf

.NOTES
  Requires PowerShell 5.1+ (ships with Windows 10/11).
  Requires Docker Desktop installed (`docker` on PATH).
  Does NOT require Administrator privileges.

  Issues #340 + #341 led to this rewrite. The previous version assumed
  Fox was already quit, used the wrong data path (assumed `Fox in the box`
  but Electron actually creates `@fox-in-the-box` because package.json has
  no productName field), and didn't survive auto-restarting tray processes.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
  [switch] $KeepData,
  [switch] $KeepInstall
)

# Native `docker` writes to stderr for benign cases (e.g. missing container).
# Continue so a stop/remove failure doesn't abort the whole script.
$ErrorActionPreference = 'Continue'

$containerName = 'fox-in-the-box'
$imageBase     = 'ghcr.io/fox-in-the-box-ai/cloud'
$dataDir       = Join-Path $env:APPDATA   '@fox-in-the-box'
$updaterDir    = Join-Path $env:LOCALAPPDATA '@fox-in-the-boxelectron-updater'
$installDir    = Join-Path $env:LOCALAPPDATA 'Programs\@fox-in-the-boxelectron'

Write-Host ''
Write-Host '════════════════════════════════════════════════════' -ForegroundColor Cyan
Write-Host '  Fox in the Box — nuclear cleanup for Windows'      -ForegroundColor Cyan
Write-Host '════════════════════════════════════════════════════' -ForegroundColor Cyan
Write-Host ''

# ─── 1. Stop Fox processes ─────────────────────────────────────────────────
# Single Stop-Process call so PowerShell's argument parser doesn't split
# `-ErrorAction SilentlyContinue` across a line break (a real failure mode
# when these commands are pasted into an interactive shell).
if ($PSCmdlet.ShouldProcess('Fox / Electron processes', 'Stop-Process')) {
  Write-Host '[1/9] Stopping Fox / Electron processes...' -ForegroundColor Cyan
  Stop-Process -Name 'fox*','electron*','@fox*' -Force -ErrorAction SilentlyContinue
  Get-Process -ErrorAction SilentlyContinue | Where-Object {
    ($_.Path -and $_.Path -like "*@fox*") -or
    ($_.MainWindowTitle -and $_.MainWindowTitle -like "*Fox in the box*")
  } | Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 3
}

# ─── 2. Stop + remove the container ───────────────────────────────────────
if ($PSCmdlet.ShouldProcess($containerName, 'docker rm -f')) {
  Write-Host '[2/9] Removing Docker container...' -ForegroundColor Cyan
  docker stop $containerName 2>$null | Out-Null
  docker rm -f $containerName 2>$null | Out-Null
  Write-Host "      container '$containerName' removed (or wasn't running)"
}

# ─── 3. Untag every known image variant ───────────────────────────────────
if ($PSCmdlet.ShouldProcess($imageBase, 'docker rmi')) {
  Write-Host '[3/9] Untagging Fox container images...' -ForegroundColor Cyan
  $tags = @('stable','latest','dev')
  # All versioned tags currently known (extend as releases ship)
  for ($minor = 5; $minor -le 30; $minor++) {
    $tags += "v0.7.$minor"
  }
  foreach ($tag in $tags) {
    docker rmi -f "${imageBase}:${tag}" 2>$null | Out-Null
  }
  Write-Host "      images untagged (some may not have been present)"
}

# ─── 4. Prune dangling Docker volumes ─────────────────────────────────────
if ($PSCmdlet.ShouldProcess('docker volumes', 'docker volume prune -f')) {
  Write-Host '[4/9] Pruning dangling Docker volumes...' -ForegroundColor Cyan
  docker volume prune -f 2>$null | Out-Null
}

# ─── 5. Run NSIS uninstaller (if installed and not -KeepInstall) ──────────
if (-not $KeepInstall) {
  $uninstallExe = $null
  if (Test-Path -LiteralPath $installDir) {
    $uninstallExe = (Get-ChildItem -LiteralPath $installDir -Filter 'Uninstall *.exe' `
        -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
  }
  if ($uninstallExe) {
    if ($PSCmdlet.ShouldProcess($uninstallExe, 'Run uninstaller silently')) {
      Write-Host '[5/9] Running NSIS uninstaller (silent)...' -ForegroundColor Cyan
      Start-Process $uninstallExe -ArgumentList '/S' -Wait
      Start-Sleep -Seconds 2
      Write-Host "      uninstalled via $uninstallExe"
    }
  } else {
    Write-Host '[5/9] No NSIS uninstaller found — skipping' -ForegroundColor DarkGray
  }
} else {
  Write-Host '[5/9] -KeepInstall set — skipping uninstaller' -ForegroundColor DarkGray
}

# ─── 6. Remove data dir (unless -KeepData) ────────────────────────────────
# cmd /c rd /s /q is more aggressive than Remove-Item against locked files;
# we use it because Chromium's LevelDB store inside userData sometimes
# survives process kill by a few hundred ms.
if (-not $KeepData) {
  if (Test-Path -LiteralPath $dataDir) {
    if ($PSCmdlet.ShouldProcess($dataDir, 'rd /s /q')) {
      Write-Host '[6/9] Removing data dir...' -ForegroundColor Cyan
      cmd /c "rd /s /q ""$dataDir""" 2>$null
      if (Test-Path -LiteralPath $dataDir) {
        Write-Host "      WARNING: $dataDir partially survived — try `wsl --shutdown` then re-run" -ForegroundColor Yellow
      } else {
        Write-Host "      removed: $dataDir"
      }
    }
  } else {
    Write-Host '[6/9] No data dir present — skipping' -ForegroundColor DarkGray
  }
} else {
  Write-Host '[6/9] -KeepData set — preserving data dir' -ForegroundColor DarkGray
}

# ─── 7. Remove auto-updater state ─────────────────────────────────────────
if (Test-Path -LiteralPath $updaterDir) {
  if ($PSCmdlet.ShouldProcess($updaterDir, 'rd /s /q')) {
    Write-Host '[7/9] Removing auto-updater state...' -ForegroundColor Cyan
    cmd /c "rd /s /q ""$updaterDir""" 2>$null
    Write-Host "      removed: $updaterDir"
  }
} else {
  Write-Host '[7/9] No auto-updater state present — skipping' -ForegroundColor DarkGray
}

# ─── 8. Remove install dir (unless -KeepInstall) ──────────────────────────
if (-not $KeepInstall) {
  if (Test-Path -LiteralPath $installDir) {
    if ($PSCmdlet.ShouldProcess($installDir, 'rd /s /q')) {
      Write-Host '[8/9] Removing install dir...' -ForegroundColor Cyan
      cmd /c "rd /s /q ""$installDir""" 2>$null
      Write-Host "      removed: $installDir"
    }
  } else {
    Write-Host '[8/9] No install dir present — skipping' -ForegroundColor DarkGray
  }
} else {
  Write-Host '[8/9] -KeepInstall set — leaving install dir' -ForegroundColor DarkGray
}

# ─── 9. Verify ────────────────────────────────────────────────────────────
Write-Host '[9/9] Verifying clean state...' -ForegroundColor Cyan
Write-Host ''
Write-Host '── Docker containers (should be empty) ──' -ForegroundColor DarkGray
docker ps -a --filter "name=$containerName"
Write-Host ''
Write-Host '── Docker images (should be empty) ──' -ForegroundColor DarkGray
docker images $imageBase
Write-Host ''
$dataExists    = Test-Path -LiteralPath $dataDir
$updaterExists = Test-Path -LiteralPath $updaterDir
$installExists = Test-Path -LiteralPath $installDir
Write-Host "Data dir present:    $dataExists $(if ($dataExists -and -not $KeepData) {'  ← UNEXPECTED'})" `
  -ForegroundColor $(if ($dataExists -and -not $KeepData) {'Yellow'} else {'Green'})
Write-Host "Updater dir present: $updaterExists $(if ($updaterExists) {'  ← UNEXPECTED'})" `
  -ForegroundColor $(if ($updaterExists) {'Yellow'} else {'Green'})
Write-Host "Install dir present: $installExists $(if ($installExists -and -not $KeepInstall) {'  ← UNEXPECTED'})" `
  -ForegroundColor $(if ($installExists -and -not $KeepInstall) {'Yellow'} else {'Green'})
Write-Host ''

$unexpected = ($dataExists -and -not $KeepData) -or
              $updaterExists -or
              ($installExists -and -not $KeepInstall)
if ($unexpected) {
  Write-Host '⚠  Some directories did not remove cleanly.' -ForegroundColor Yellow
  Write-Host '   Common causes:' -ForegroundColor Yellow
  Write-Host '   • Docker Desktop''s WSL2 backend has a bind-mount lock on the data dir' -ForegroundColor Yellow
  Write-Host '     Fix: run `wsl --shutdown` then re-run this script' -ForegroundColor Yellow
  Write-Host '   • A Fox / Electron process is still alive somewhere' -ForegroundColor Yellow
  Write-Host '     Fix: check Task Manager → end any *fox* / *electron* processes' -ForegroundColor Yellow
} else {
  Write-Host '✓ Clean. Reinstall Fox from:' -ForegroundColor Green
  Write-Host '  https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/latest' -ForegroundColor Green
}
Write-Host ''
