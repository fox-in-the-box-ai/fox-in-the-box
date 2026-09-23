#Requires -Version 5.1
<#
.SYNOPSIS
  Pester smoke asserting clean-windows-desktop.ps1's path arrays stay in sync
  with the electron config that determines the installed Windows layout (#762).

.DESCRIPTION
  The lint half (#759/#760) proves the cleanup script parses and passes
  PSScriptAnalyzer, but it cannot catch a *semantic* desync: renaming
  productName / executableName / the npm package name, or flipping
  electron-builder's nsis.perMachine, silently moves the installed layout
  while the uninstall script keeps deleting the old directories. That exact
  class of miss shipped twice — the modern userData dir (#754) and the modern
  install dir (#758) were both absent from the script until caught by hand.

  This test re-derives the MODERN userData / updater-cache / NSIS-install
  directory names from packages/electron/{package.json,electron-builder.yml}
  and asserts the script's $dataDirs / $updaterDirs / $installDirs arrays
  still contain them. The modern leaves are DERIVED (never hardcoded) so a
  config change forces this test to move with it. The LEGACY leaves are
  frozen constants from retired configs — back-compat cleanup must keep
  targeting them, so they are asserted literally.

  SAFETY: the script's arrays are read via the PowerShell AST
  ([System.Management.Automation.Language.Parser]::ParseFile) — the script is
  NEVER dot-sourced or invoked, because loading it runs `rd /s /q`,
  `docker rm -f`, and `Stop-Process`. Every derivation contract failure
  (missing config key, renamed/absent array, empty array) throws — the test
  fails loud rather than passing vacuously, mirroring ps1-lint's guard.
#>

# ── Derivation helpers ────────────────────────────────────────────────────
# Defined inside a script-root BeforeAll, NOT as bare top-level functions. In
# Pester v5 the file is executed twice — once for Discovery, once for Run — in
# separate scopes. Bare script-root functions are defined during Discovery but
# are not in scope during Run, so the Describe's BeforeAll and It blocks (which
# execute in the Run phase) fail with CommandNotFoundException. A script-root
# BeforeAll runs in the Run phase before every child container's setup, so these
# helpers are visible to the whole file. The Describe below stores its derived
# values in $script:-scoped variables for the same cross-block visibility reason.

BeforeAll {
  function Get-SanitizedFileName {
    <#
      Replicates electron-updater's sanitizeFileName rule: strip the characters
      that are illegal in a Windows path segment (< > : " / \ | ? *) and keep
      everything else — notably '@', which is why the npm scope '@fox-in-the-box'
      survives into the updater cache dir name.

      KNOWN LIMITATION: this mirrors the upstream rule as of electron-updater 6.x.
      A major electron-updater bump could change the sanitization and silently
      drift this derivation — revisit if the updater cache dir name ever moves.
    #>
    param([Parameter(Mandatory = $true)] [string] $Name)
    return ($Name -replace '[<>:"/\\|?*]', '')
  }

  function Get-ElectronPathConfig {
    <#
      Reads the four config values that determine the Windows install layout.
      Fails loud (throw) on any missing key — a vacuous pass here would defeat
      the whole point of the guard.
    #>
    param([Parameter(Mandatory = $true)] [string] $ElectronDir)

    $pkgPath = Join-Path $ElectronDir 'package.json'
    $ymlPath = Join-Path $ElectronDir 'electron-builder.yml'

    if (-not (Test-Path -LiteralPath $pkgPath)) { throw "package.json not found at $pkgPath" }
    if (-not (Test-Path -LiteralPath $ymlPath)) { throw "electron-builder.yml not found at $ymlPath" }

    $pkg = Get-Content -LiteralPath $pkgPath -Raw | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace($pkg.name))        { throw "package.json is missing 'name'" }
    if ([string]::IsNullOrWhiteSpace($pkg.productName)) { throw "package.json is missing 'productName'" }

    # Targeted regex, not a full YAML parser (none is available by default).
    # Top-level executableName only: the indented `linux:` executableName is a
    # different key, so anchor at column 0 with no leading whitespace.
    $yml = Get-Content -LiteralPath $ymlPath -Raw
    $execMatch = [regex]::Match($yml, '(?m)^executableName:[ \t]*(\S+)[ \t]*$')
    if (-not $execMatch.Success) { throw "electron-builder.yml is missing a top-level 'executableName'" }

    $perMachineMatch = [regex]::Match($yml, '(?m)^[ \t]*perMachine:[ \t]*(true|false)[ \t]*$')
    if (-not $perMachineMatch.Success) { throw "electron-builder.yml is missing 'nsis.perMachine'" }

    return [pscustomobject]@{
      Name           = $pkg.name
      ProductName    = $pkg.productName
      ExecutableName = $execMatch.Groups[1].Value
      PerMachine     = [System.Convert]::ToBoolean($perMachineMatch.Groups[1].Value)
    }
  }

  function Get-DirArrayEntries {
    <#
      Extracts the `Join-Path $env:<ROOT> '<leaf>'` entries of a named array from
      the cleanup script WITHOUT executing it, via the AST. Returns objects with
      Root / Leaf / Key ("<ROOT>|<leaf>"). Throws if the array is renamed,
      removed, no longer an @(...) literal, or empty — any of which means the
      uninstall layout has desynced from the installed one.
    #>
    param(
      [Parameter(Mandatory = $true)] [string] $ScriptPath,
      [Parameter(Mandatory = $true)] [string] $VariableName
    )

    $tokens = $null
    $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$tokens, [ref]$errors)
    if ($errors.Count -gt 0) {
      throw "clean-windows-desktop.ps1 failed to parse: $($errors[0].Message)"
    }

    $assignment = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
        $node.Left -is [System.Management.Automation.Language.VariableExpressionAst] -and
        $node.Left.VariablePath.UserPath -eq $VariableName
      }, $true)
    if (-not $assignment) {
      throw "array `$$VariableName not found in $ScriptPath — array renamed or removed (uninstall layout desynced)"
    }

    $arrayExpr = $assignment.Right.Find({
        param($node)
        $node -is [System.Management.Automation.Language.ArrayExpressionAst]
      }, $true)
    if (-not $arrayExpr) {
      throw "`$$VariableName is no longer an @(...) array literal in $ScriptPath"
    }

    $joinCalls = $arrayExpr.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.CommandElements.Count -gt 0 -and
        $node.CommandElements[0].Value -eq 'Join-Path'
      }, $true)
    if ($joinCalls.Count -eq 0) {
      throw "`$$VariableName contains no Join-Path entries in $ScriptPath"
    }

    $entries = foreach ($call in $joinCalls) {
      $pathArgs = $call.CommandElements[1..($call.CommandElements.Count - 1)]
      $rootVar = $pathArgs | Where-Object {
        $_ -is [System.Management.Automation.Language.VariableExpressionAst]
      } | Select-Object -First 1
      $leaf = $pathArgs | Where-Object {
        $_ -is [System.Management.Automation.Language.StringConstantExpressionAst]
      } | Select-Object -First 1

      if (-not $rootVar -or -not $leaf) {
        throw "a Join-Path entry in `$$VariableName is missing its `$env: root or string leaf"
      }

      # $env:APPDATA -> VariablePath.UserPath == 'env:APPDATA' -> root 'APPDATA'.
      $root = $rootVar.VariablePath.UserPath.Split(':')[-1]
      [pscustomobject]@{
        Root = $root
        Leaf = $leaf.Value
        Key  = "$root|$($leaf.Value)"
      }
    }

    return @($entries)
  }
}

# ── Assertions ────────────────────────────────────────────────────────────

Describe 'clean-windows-desktop.ps1 path derivations (#762)' {
  BeforeAll {
    $electronDir = Join-Path (Split-Path $PSScriptRoot -Parent) 'electron'
    $script:scriptPath = Join-Path $PSScriptRoot 'clean-windows-desktop.ps1'
    $cfg = Get-ElectronPathConfig -ElectronDir $electronDir

    # MODERN leaves — re-derived from config, deliberately not hardcoded.
    # userData follows productName under %APPDATA%.
    $script:derivedDataKey = "APPDATA|$($cfg.ProductName)"

    # electron-updater cache follows sanitizeFileName(package.json name)+'-updater'
    # under %LOCALAPPDATA%.
    $updaterLeaf = "$(Get-SanitizedFileName $cfg.Name)-updater"
    $script:derivedUpdaterKey = "LOCALAPPDATA|$updaterLeaf"

    # NSIS install root depends on perMachine: per-user installs land in
    # %LOCALAPPDATA%\Programs\<exe>; per-machine installs land in
    # %PROGRAMFILES%\<exe>.
    if ($cfg.PerMachine) {
      $script:derivedInstallKey = "PROGRAMFILES|$($cfg.ExecutableName)"
    } else {
      $script:derivedInstallKey = "LOCALAPPDATA|Programs\$($cfg.ExecutableName)"
    }

    # LEGACY leaves — frozen from retired configs; cleanup must keep targeting
    # them, so they are asserted as literal back-compat constants.
    $script:legacyDataKey    = 'APPDATA|@fox-in-the-box'
    $script:legacyInstallKey = 'LOCALAPPDATA|Programs\@fox-in-the-boxelectron'

    $script:dataEntries    = @((Get-DirArrayEntries -ScriptPath $script:scriptPath -VariableName 'dataDirs').Key)
    $script:updaterEntries = @((Get-DirArrayEntries -ScriptPath $script:scriptPath -VariableName 'updaterDirs').Key)
    $script:installEntries = @((Get-DirArrayEntries -ScriptPath $script:scriptPath -VariableName 'installDirs').Key)
  }

  Context '$dataDirs (Electron userData)' {
    It 'contains the modern userData dir re-derived from productName (#754)' {
      $script:dataEntries | Should -Contain $script:derivedDataKey
    }

    It 'still contains the frozen legacy @fox-in-the-box userData dir' {
      $script:dataEntries | Should -Contain $script:legacyDataKey
    }
  }

  Context '$updaterDirs (electron-updater cache)' {
    It 'has exactly one entry' {
      $script:updaterEntries.Count | Should -Be 1
    }

    It 'matches sanitizeFileName(name)-updater under %LOCALAPPDATA%' {
      $script:updaterEntries | Should -Contain $script:derivedUpdaterKey
    }
  }

  Context '$installDirs (NSIS install)' {
    It 'contains the modern install dir re-derived from executableName + perMachine (#758)' {
      $script:installEntries | Should -Contain $script:derivedInstallKey
    }

    It 'still contains the frozen legacy Programs\@fox-in-the-boxelectron install dir' {
      $script:installEntries | Should -Contain $script:legacyInstallKey
    }
  }
}
