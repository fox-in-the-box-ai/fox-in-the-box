# Fox in the box — Windows desktop notes

## After uninstall — manual cleanup

Since v0.7.26 the NSIS uninstaller offers to remove Fox data and (since v0.7.27)
Docker Desktop if no other images remain. If you declined those prompts or are
on an older version, the items below may need manual cleanup.

| What                                     | Typical location                                            | Action                                       |
| ---------------------------------------- | ----------------------------------------------------------- | -------------------------------------------- |
| Electron user data (logs, updater cache) | `%APPDATA%\fox-in-the-box\`                                 | Delete folder if you want a clean slate      |
| Docker named volume / bind data          | `%USERPROFILE%` path passed to Docker as `/data` host mount | Remove only if you know your install used it |
| `Fox in the box` Start menu shortcut     | Start menu → right‑click → Unpin / delete                   | Optional cosmetic cleanup                    |

To also wipe app state that NSIS can remove in one go, the installer can be
built with `deleteAppDataOnUninstall: true` in `electron-builder.yml` (currently
`false` so upgrades keep user data).

## Shell icon shows Electron instead of the fox (Start menu / Settings → Apps)

v0.7.60 shipped the canonical Fox icon set (multi-size `.ico`, macOS/Linux
icons, favicons, PWA titles) — the multi-size rebuild below is done work.
Users upgrading to v0.7.60+ may still need the icon-cache refresh once for
the shell to pick up the new icons.

1. Reinstall so the installer can refresh **installer / uninstaller / shortcut**
   icons (`electron-builder.yml` sets `nsis.installerIcon` and
   `nsis.uninstallerIcon` from `assets/icon.ico`).
2. **Refresh the Windows icon cache** (run in an elevated **cmd** or PowerShell,
   then sign out or reboot):

```bat
ie4uinit.exe -show
```

On some builds you can instead restart Explorer:

```bat
taskkill /f /im explorer.exe & start explorer.exe
```

If the shortcut still points at an old path, delete the Start menu shortcut and
let the installer recreate it on next install.

## First-run browser URL

The desktop app opens **`http://127.0.0.1:8787/`** (the WebUI root) after the
container is healthy; first-run setup is the native hermes-webui flow. The
former Fox custom setup wizard and its `/setup` route were removed in favor
of the native flow.

## Resolved desktop issues (fixed on main, ship with the next release)

- **#748** — launching the packaged app from a terminal whose stdout closes
  no longer crashes with an `EPIPE` dialog; stream errors are guarded before
  the first log write.
- **#749** — guided setup on macOS never touches Homebrew when Docker
  Desktop is already installed: a present-but-stopped Docker is started,
  not (re)installed or upgraded.
