# Full reset — clean install

Use this when you want a new container, fresh on-disk data, and optionally a fresh image. Common reasons: a botched upgrade, switching machines, or you just want to start over.

## Recommended path (v0.7.18+)

The simplest reset uses Fox's own UI:

1. Right-click the **system tray icon** (Windows) or **menu-bar icon** (macOS).
2. Click **"Reset Fox completely…"**.
3. Confirm the destructive action.

Fox stops its container, removes the image, deletes all user data, then quits. Relaunch from the Start Menu / Applications folder to begin fresh. No PowerShell or terminal needed.

If the in-app reset isn't available (older Fox version) or Fox won't launch at all, use the platform-specific manual instructions below.

---

## Windows — script

In PowerShell, from a clone of this repo (or just download the `.ps1` file):

```powershell
cd packages\scripts
.\clean-windows-desktop.ps1
```

That does the full nuclear cleanup: stops every Fox / Electron process, removes the container, untags every Fox image variant (`:stable`, `:v0.7.*`, `:latest`), prunes dangling volumes, runs the bundled NSIS uninstaller silently, deletes the `%APPDATA%\@fox-in-the-box` data dir + `%LOCALAPPDATA%\@fox-in-the-boxelectron-updater` + install dir, and verifies clean state at the end.

**Options:**

- `-KeepData` — leave `%APPDATA%\@fox-in-the-box` alone (preserve onboarding state, settings, conversation history, local models). Useful for "reset Docker only."
- `-KeepInstall` — don't run the uninstaller or delete the install dir. Useful for "reset data only."
- `-WhatIf` — preview what would change without changing anything.

```powershell
# Reset Docker container + image, preserve all Fox data and app
.\clean-windows-desktop.ps1 -KeepData

# Reset all data, but leave Fox app installed
.\clean-windows-desktop.ps1 -KeepInstall

# Preview only
.\clean-windows-desktop.ps1 -WhatIf
```

After the script: reinstall from the [latest release](https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/latest) (or relaunch if you used `-KeepInstall`).

### Windows — when the script reports "did not remove cleanly"

Usually means Docker Desktop's WSL2 backend has a bind-mount lock on the data dir. Fix:

```powershell
wsl --shutdown
.\clean-windows-desktop.ps1
```

Or a Fox/Electron process is still alive — check Task Manager → end any `fox*` / `electron*` process → re-run the script.

### Windows — manual fallback (no script)

```powershell
docker rm -f fox-in-the-box
docker rmi -f ghcr.io/fox-in-the-box-ai/cloud:stable
cmd /c "rd /s /q ""$env:APPDATA\@fox-in-the-box"""
cmd /c "rd /s /q ""$env:LOCALAPPDATA\@fox-in-the-boxelectron-updater"""
```

Then uninstall the app via Settings → Apps if you want the program files gone too.

---

## macOS

1. **Quit Fox in the Box** from the menu-bar icon (or stop the container directly: `docker stop fox-in-the-box`).
2. **Remove the container.**

   ```bash
   docker rm -f fox-in-the-box
   ```

3. **If you used the install script**, unload the launchd agent so it stops auto-starting:

   ```bash
   launchctl unload ~/Library/LaunchAgents/io.foxinthebox.plist
   rm ~/Library/LaunchAgents/io.foxinthebox.plist   # only if you no longer want auto-start
   ```

4. **Remove your data.** Default Electron path is `~/Library/Application Support/@fox-in-the-box`. If you used the Docker one-liner with `-v ~/.foxinthebox:/data`, also remove that.

   ```bash
   rm -rf "$HOME/Library/Application Support/@fox-in-the-box"
   rm -rf "$HOME/.foxinthebox"   # only if you used the Docker one-liner path
   ```

5. **Optionally remove the cached image** so the next install pulls fresh:

   ```bash
   docker rmi ghcr.io/fox-in-the-box-ai/cloud:stable
   ```

6. **Drag Fox in the Box.app to the Trash** if you want to fully uninstall the desktop app.

7. **Reinstall** by re-running the [install script](../README.md#linux--macos-install-script) or downloading the latest DMG.

---

## Linux

1. Stop and remove the container:
   ```bash
   docker rm -f fox-in-the-box
   ```
2. If you installed the systemd unit, disable + remove it:
   ```bash
   sudo systemctl disable --now foxinthebox.service foxinthebox-updater.service foxinthebox-updater.path
   sudo rm /etc/systemd/system/foxinthebox*
   sudo systemctl daemon-reload
   ```
3. Remove your data directory (default: `~/.foxinthebox`):
   ```bash
   rm -rf ~/.foxinthebox
   ```
4. Optionally clear the image:
   ```bash
   docker rmi ghcr.io/fox-in-the-box-ai/cloud:stable
   ```
5. Reinstall via `bash packages/scripts/install.sh` or the Docker one-liner.
