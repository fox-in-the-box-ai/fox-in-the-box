; ── Fox in the Box — NSIS installer customisation ────────────────────────────
;
; Provides:
;   1. customInit       — kill running Fox, detect existing install, show mode dialog
;   2. customInstallMode — clean-wipe before install when mode=1 selected
;   3. customUnInstall  — remove RunOnce key + optional container/data cleanup (#353)
;
; Branding: electron-builder.yml references assets/installer/header.bmp (150x57)
; and assets/installer/sidebar.bmp (164x314) for the wizard chrome (#323).
;
; Keep customUnInstall's label names in sync with:
;   packages/electron/src/windows-run-once.js (VALUE_NAME = "FoxInTheBoxResumeSetup")
; ─────────────────────────────────────────────────────────────────────────────

!define FITB_APPDATA_DIR "$APPDATA\fox-in-the-box"
!define FITB_CONTAINER   "fox-in-the-box"
!define FITB_IMAGE       "ghcr.io/fox-in-the-box-ai/cloud:stable"

; Install mode: 0=Express upgrade (default), 1=Clean install
Var /GLOBAL FitbInstallMode

; ── Pre-install: kill running processes + detect existing install ─────────────
!macro customInit
  DetailPrint "Stopping running Fox in the box processes..."
  nsExec::ExecToLog 'taskkill /IM "FoxInTheBox.exe" /F /T'
  nsExec::ExecToLog 'taskkill /IM "Fox in the Box.exe" /F /T'
  nsExec::ExecToLog 'taskkill /IM "fox-in-the-box.exe" /F /T'
  Sleep 1000

  StrCpy $FitbInstallMode "0"

  ; Show mode dialog only when a prior install is detected
  IfFileExists "${FITB_APPDATA_DIR}\*.*" fitb_existing_install
  IfFileExists "$LOCALAPPDATA\Programs\fox-in-the-box\FoxInTheBox.exe" fitb_existing_install
  Goto fitb_init_done

  fitb_existing_install:
    Call FitbShowModeDialog

  fitb_init_done:
!macroend

; Mode selection dialog — Express upgrade (default) vs Clean install
Function FitbShowModeDialog
  nsDialogs::Create 1018
  Pop $0
  ${If} $0 == error
    Return
  ${EndIf}

  ${NSD_CreateLabel} 0 0 100% 20u "An existing Fox in the Box installation was found."
  Pop $0
  ${NSD_CreateLabel} 0 22u 100% 12u "How would you like to install?"
  Pop $0

  ${NSD_CreateRadioButton} 10u 38u 100% 14u "Express upgrade — keep my data, conversations, and AI models"
  Pop $1
  ${NSD_SetState} $1 ${BST_CHECKED}

  ${NSD_CreateRadioButton} 10u 56u 100% 14u "Clean install — remove everything and start fresh"
  Pop $2

  ${NSD_CreateLabel} 22u 72u 90% 20u "Warning: deletes all Fox data, settings, conversations, and local AI models. Cannot be undone."
  Pop $0
  SetCtlColors $0 FF4444 transparent

  nsDialogs::Show

  ${NSD_GetState} $2 $3
  ${If} $3 == ${BST_CHECKED}
    StrCpy $FitbInstallMode "1"
  ${Else}
    StrCpy $FitbInstallMode "0"
  ${EndIf}
FunctionEnd

; ── Clean install pre-wipe ────────────────────────────────────────────────────
!macro customInstallMode
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

    ; #153: offer Docker Desktop removal if Fox was its only consumer.
    ; Check for non-Fox images via `docker images -q`. If the daemon is
    ; running and the output is empty, Docker has nothing left to serve.
    ; If the daemon is down or the check fails, we skip the prompt (fail safe).
    Var /GLOBAL FitbDockerImages
    nsExec::ExecToStack 'docker images -q'
    Pop $0  ; exit code
    Pop $1  ; stdout
    StrCpy $FitbDockerImages $1
    ${If} $0 == 0
    ${AndIf} $FitbDockerImages == ""
      MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 \
        "Fox was the only application using Docker on this PC.$\n$\nWould you like to remove Docker Desktop as well?" \
        IDYES fitb_remove_docker IDNO fitb_skip_docker

      fitb_remove_docker:
        DetailPrint "Uninstall: removing Docker Desktop..."
        ; Docker Desktop ships its own uninstaller at a known path
        IfFileExists "$PROGRAMFILES\Docker\Docker\Docker Desktop Installer.exe" 0 fitb_skip_docker
        nsExec::ExecToLog '"$PROGRAMFILES\Docker\Docker\Docker Desktop Installer.exe" uninstall --quiet'

      fitb_skip_docker:
    ${EndIf}

  fitb_uninstall_skip:
!macroend
