; ── Fox in the Box — NSIS installer customisation ────────────────────────────
;
; Provides:
;   1. customInit      — kill running Fox processes before install begins
;   2. customUnInstall — remove RunOnce key + optional container/data cleanup
;
; Note: The Express/Clean install mode-selection dialog (#353) requires
; nsDialogs and a forward-declared Function, which cannot be safely embedded
; in a customInit macro with electron-builder's NSIS 3.x bundled build.
; Filed for a proper NSIS custom page implementation in v0.7.32+.
;
; Keep value names in sync with packages/electron/src/windows-run-once.js.
; ─────────────────────────────────────────────────────────────────────────────

!define FITB_APPDATA_DIR "$APPDATA\fox-in-the-box"
!define FITB_CONTAINER   "fox-in-the-box"
!define FITB_IMAGE       "ghcr.io/fox-in-the-box-ai/cloud:stable"

; ── Pre-install: kill running Fox processes ───────────────────────────────────
!macro customInit
  DetailPrint "Stopping running Fox in the box processes..."
  nsExec::ExecToLog 'taskkill /IM "FoxInTheBox.exe" /F /T'
  nsExec::ExecToLog 'taskkill /IM "Fox in the Box.exe" /F /T'
  nsExec::ExecToLog 'taskkill /IM "fox-in-the-box.exe" /F /T'
  Sleep 1000
!macroend

; ── Uninstall: remove RunOnce key + optional data cleanup ─────────────────────
!macro customUnInstall
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\RunOnce" "FoxInTheBoxResumeSetup"

  ; Ask whether to remove container, image, and data. Default = No (safe).
  MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 \
    "Also remove Fox data, conversations, and AI models?$\n$\nThis deletes the Fox container, image, and all saved data. Cannot be undone.$\n$\nChoose No to keep your data (you can reinstall later and pick up where you left off)." \
    IDYES fitb_uninstall_data IDNO fitb_uninstall_skip

  fitb_uninstall_data:
    DetailPrint "Uninstall: stopping Fox container..."
    nsExec::ExecToLog 'docker stop ${FITB_CONTAINER}'
    nsExec::ExecToLog 'docker rm -f ${FITB_CONTAINER}'
    DetailPrint "Uninstall: removing Fox image..."
    nsExec::ExecToLog 'docker rmi -f ${FITB_IMAGE}'
    DetailPrint "Uninstall: removing Fox data..."
    RMDir /r "${FITB_APPDATA_DIR}"

    ; Offer Docker Desktop removal if Fox was its only consumer.
    ; Check for non-Fox images via `docker images -q`. If daemon is running
    ; and output is empty, Docker has nothing left to serve.
    nsExec::ExecToStack 'docker images -q'
    Pop $0  ; exit code
    Pop $1  ; stdout
    ${If} $0 == 0
    ${AndIf} $1 == ""
      MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 \
        "Fox was the only application using Docker on this PC.$\n$\nWould you like to remove Docker Desktop as well?" \
        IDYES fitb_remove_docker IDNO fitb_skip_docker

      fitb_remove_docker:
        DetailPrint "Uninstall: removing Docker Desktop..."
        IfFileExists "$PROGRAMFILES\Docker\Docker\Docker Desktop Installer.exe" 0 fitb_skip_docker
        nsExec::ExecToLog '"$PROGRAMFILES\Docker\Docker\Docker Desktop Installer.exe" uninstall --quiet'

      fitb_skip_docker:
    ${EndIf}

  fitb_uninstall_skip:
!macroend
