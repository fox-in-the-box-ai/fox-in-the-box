; ── Fox in the Box — NSIS installer customisation ─────────────────────────────
;
; Includes mode-page.nsh (Express / Clean install selection).
; mode-page.nsh declares FitbModePageCreate / FitbModePageLeave Functions and
; the $FitbInstallMode Var at top level — required by NSIS before any Section.
;
; electron-builder inserts this file's content verbatim into the generated
; script header, so top-level declarations here are valid top-level NSIS.
;
; Keep RunOnce value name in sync with windows-run-once.js (VALUE_NAME).
; ─────────────────────────────────────────────────────────────────────────────

!define FITB_APPDATA_DIR "$APPDATA\fox-in-the-box"
!define FITB_CONTAINER   "fox-in-the-box"
!define FITB_IMAGE       "ghcr.io/fox-in-the-box-ai/cloud:stable"

; NSIS warning 6010 ("install function not referenced") fires for FitbModePageCreate
; and FitbModePageLeave during the uninstaller pass — NSIS doesn't count Page custom
; registrations as function references. electron-builder passes -WX, so suppress it.
!pragma warning disable 6010
!include "mode-page.nsh"
!pragma warning default 6010

; Register the mode-selection page after the directory selection page.
; electron-builder calls !insertmacro customPageAfterChangeDir in its
; installSection.nsh template — this is the recognised hook for custom pages.
!macro customPageAfterChangeDir
  Page custom FitbModePageCreate FitbModePageLeave
!macroend

; ── Install: clean wipe if Clean install selected ─────────────────────────────
; customInstall runs inside the install Section (after all pages are navigated),
; so $FitbInstallMode is set by FitbModePageLeave before this macro fires.
; electron-builder calls !insertmacro customInstall in installSection.nsh.
!macro customInstall
  ${If} $FitbInstallMode == "1"
    DetailPrint "Clean install: stopping Fox container..."
    nsExec::ExecToLog 'docker stop ${FITB_CONTAINER}'
    nsExec::ExecToLog 'docker rm -f ${FITB_CONTAINER}'
    DetailPrint "Clean install: removing Fox image..."
    nsExec::ExecToLog 'docker rmi -f ${FITB_IMAGE}'
    DetailPrint "Clean install: removing Fox data..."
    RMDir /r "${FITB_APPDATA_DIR}"
    DetailPrint "Clean install: ready."
  ${EndIf}
!macroend

; ── Pre-install: kill running Fox processes ───────────────────────────────────
!macro customInit
  DetailPrint "Stopping running Fox in the box processes..."
  nsExec::ExecToLog 'taskkill /IM "FoxInTheBox.exe" /F /T'
  nsExec::ExecToLog 'taskkill /IM "Fox in the Box.exe" /F /T'
  nsExec::ExecToLog 'taskkill /IM "fox-in-the-box.exe" /F /T'
  Sleep 1000
!macroend

; ── Uninstall: remove RunOnce key + optional data + Docker cleanup ─────────────
!macro customUnInstall
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\RunOnce" "FoxInTheBoxResumeSetup"

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

    nsExec::ExecToStack 'docker images -q'
    Pop $0
    Pop $1
    ${If} $0 == 0
    ${AndIf} $1 == ""
      MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 \
        "Fox was the only application using Docker on this PC.$\n$\nWould you like to remove Docker Desktop as well?" \
        IDYES fitb_remove_docker IDNO fitb_skip_docker
      fitb_remove_docker:
        IfFileExists "$PROGRAMFILES\Docker\Docker\Docker Desktop Installer.exe" 0 fitb_skip_docker
        nsExec::ExecToLog '"$PROGRAMFILES\Docker\Docker\Docker Desktop Installer.exe" uninstall --quiet'
      fitb_skip_docker:
    ${EndIf}

  fitb_uninstall_skip:
!macroend
