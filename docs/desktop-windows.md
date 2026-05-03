# Fox in the box — Windows desktop notes

## After uninstall — manual cleanup

The NSIS uninstaller removes application files and the **RunOnce** resume entry
(`FoxInTheBoxResumeSetup`). It does **not** remove Docker images/containers or
the Fox data directory used by the container.

| What | Typical location | Action |
|------|------------------|--------|
| Electron user data (logs, updater cache) | `%APPDATA%\@fox-in-the-box\` | Delete folder if you want a clean slate |
| Docker named volume / bind data | `%USERPROFILE%` path passed to Docker as `/data` host mount | Remove only if you know your install used it |
| `Fox in the box` Start menu shortcut | Start menu → right‑click → Unpin / delete | Optional cosmetic cleanup |

To also wipe app state that NSIS can remove in one go, the installer can be
built with `deleteAppDataOnUninstall: true` in `electron-builder.yml` (currently
`false` so upgrades keep user data).

## Shell icon shows Electron instead of the fox (Start menu / Settings → Apps)

1. **Rebuild the `.ico`** with multiple embedded sizes (16, 32, 48, 256). A
   single-size icon often shows correctly in the window title but not in
   shell shortcuts or “Apps & features”.
2. Reinstall so the installer can refresh **installer / uninstaller / shortcut**
   icons (`electron-builder.yml` sets `nsis.installerIcon` and
   `nsis.uninstallerIcon` from `assets/icon.ico`).
3. **Refresh the Windows icon cache** (run in an elevated **cmd** or PowerShell,
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

The desktop app opens **`http://127.0.0.1:8787/setup`** after the container is
healthy so you land on the **Fox** setup wizard (task 05b), not only the
Hermes WebUI root page (which has its own first-run flow).
