# Full reset — clean install

Use this when you want a new container, fresh on-disk data, and optionally a fresh image (for example after changing Docker options like `/dev/net/tun`).

## Windows

1. **Quit Fox in the Box completely**, including the system-tray icon.
2. **Uninstall the app** from *Settings → Apps → Installed apps* if you also want the program files removed. The installer does not delete your data folder by default.
3. **Remove the container and data** — pick one:

   **Script (recommended).** In PowerShell, from the repo (or copy the script elsewhere):

   ```powershell
   cd packages\scripts
   .\clean-windows-desktop.ps1
   ```

   To also delete the cached Linux image (the next app start will `docker pull` again):

   ```powershell
   .\clean-windows-desktop.ps1 -RemoveImage
   ```

   If you ever ran the CLI Docker one-liner with `-v ~/.foxinthebox:/data`, add `-RemoveFoxintheboxDir` to remove `%USERPROFILE%\.foxinthebox` as well.

   **Manual.**

   ```powershell
   docker rm -f fox-in-the-box
   Remove-Item -Recurse -Force "$env:APPDATA\Fox in the box"
   docker rmi ghcr.io/fox-in-the-box-ai/cloud:stable   # optional
   ```

4. **Reinstall** from the [latest release](https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/latest) and start the app once so it recreates the container.

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

4. **Remove your data** at the path you chose during install (default: `~/Library/Application Support/Fox in the Box`):

   ```bash
   rm -rf "$HOME/Library/Application Support/Fox in the Box"
   ```

5. **Optionally remove the cached image** so the next install pulls fresh:

   ```bash
   docker rmi ghcr.io/fox-in-the-box-ai/cloud:stable
   ```

6. **Reinstall** by re-running the [install script](../README.md#linux--macos-install-script) or the Docker one-liner.

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
