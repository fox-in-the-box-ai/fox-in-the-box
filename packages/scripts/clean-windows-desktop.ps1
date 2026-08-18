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
    6. Remove the data dirs — `%APPDATA%\fox-in-the-box` (v0.7.19+) and
       legacy `%APPDATA%\@fox-in-the-box` (Electron userData + container bind mount)
    7. Remove the auto-updater state (both path generations)
    8. Remove the install dirs (both path generations)
    9. Verify clean state and report

  After this script: Fox is GONE from the system. Reinstall fresh from
  https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/latest

  When the in-app "Tray → Reset Fox completely…" menu (v0.7.18+) suffices,
  use that instead — this script is for when Fox won't launch at all or the
  in-app reset failed (e.g. cross-version upgrade gone wrong).

.PARAMETER KeepData
  Skip step 6 — preserve the data dirs (onboarding state, settings,
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
# Two path generations per dir (#754): v0.7.19 dropped the '@' from the
# userData name (productName fox-in-the-box) and later releases moved the
# updater/install dirs with it. Modern first, legacy second — the script
# removes both; presence of either counts in the final verification.
$dataDirs    = @(
  (Join-Path $env:APPDATA 'fox-in-the-box'),
  (Join-Path $env:APPDATA '@fox-in-the-box')
)
$updaterDirs = @(
  (Join-Path $env:LOCALAPPDATA 'fox-in-the-box-updater'),
  (Join-Path $env:LOCALAPPDATA '@fox-in-the-boxelectron-updater')
)
$installDirs = @(
  (Join-Path $env:LOCALAPPDATA 'Programs\Fox in the Box'),
  (Join-Path $env:LOCALAPPDATA 'Programs\@fox-in-the-boxelectron')
)

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
  foreach ($dir in $installDirs) {
    if (-not $uninstallExe -and (Test-Path -LiteralPath $dir)) {
      $uninstallExe = (Get-ChildItem -LiteralPath $dir -Filter 'Uninstall *.exe' `
          -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
    }
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
  Write-Host '[6/9] Removing data dirs...' -ForegroundColor Cyan
  foreach ($dir in $dataDirs) {
    if (Test-Path -LiteralPath $dir) {
      if ($PSCmdlet.ShouldProcess($dir, 'rd /s /q')) {
        cmd /c "rd /s /q ""$dir""" 2>$null
        if (Test-Path -LiteralPath $dir) {
          Write-Host "      WARNING: $dir partially survived — try `wsl --shutdown` then re-run" -ForegroundColor Yellow
        } else {
          Write-Host "      removed: $dir"
        }
      }
    } else {
      Write-Host "      not present: $dir" -ForegroundColor DarkGray
    }
  }
} else {
  Write-Host '[6/9] -KeepData set — preserving data dirs' -ForegroundColor DarkGray
}

# ─── 7. Remove auto-updater state ─────────────────────────────────────────
Write-Host '[7/9] Removing auto-updater state...' -ForegroundColor Cyan
foreach ($dir in $updaterDirs) {
  if (Test-Path -LiteralPath $dir) {
    if ($PSCmdlet.ShouldProcess($dir, 'rd /s /q')) {
      cmd /c "rd /s /q ""$dir""" 2>$null
      Write-Host "      removed: $dir"
    }
  } else {
    Write-Host "      not present: $dir" -ForegroundColor DarkGray
  }
}

# ─── 8. Remove install dir (unless -KeepInstall) ──────────────────────────
if (-not $KeepInstall) {
  Write-Host '[8/9] Removing install dirs...' -ForegroundColor Cyan
  foreach ($dir in $installDirs) {
    if (Test-Path -LiteralPath $dir) {
      if ($PSCmdlet.ShouldProcess($dir, 'rd /s /q')) {
        cmd /c "rd /s /q ""$dir""" 2>$null
        Write-Host "      removed: $dir"
      }
    } else {
      Write-Host "      not present: $dir" -ForegroundColor DarkGray
    }
  }
} else {
  Write-Host '[8/9] -KeepInstall set — leaving install dirs' -ForegroundColor DarkGray
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
$dataExists    = @($dataDirs    | Where-Object { Test-Path -LiteralPath $_ }).Count -gt 0
$updaterExists = @($updaterDirs | Where-Object { Test-Path -LiteralPath $_ }).Count -gt 0
$installExists = @($installDirs | Where-Object { Test-Path -LiteralPath $_ }).Count -gt 0
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
