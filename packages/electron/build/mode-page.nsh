; ── Fox in the Box — Install mode selection page ──────────────────────────────
;
; Registered as `Page custom FitbModePageCreate FitbModePageLeave` in
; installer.nsh. Only shown when a prior Fox install is detected.
; Sets $FitbInstallMode: "0" = Express (default), "1" = Clean install.
; ─────────────────────────────────────────────────────────────────────────────

!include "nsDialogs.nsh"
!include "LogicLib.nsh"

Var FitbInstallMode
Var FitbDlg
Var FitbRadioExpress
Var FitbRadioClean
Var FitbWarnLabel

Function FitbModePageCreate
  ; Only show this page when a prior install exists.
  ${IfNot} ${FileExists} "$APPDATA\fox-in-the-box\*.*"
    Abort   ; skip this page — fresh install
  ${EndIf}

  nsDialogs::Create 1018
  Pop $FitbDlg
  ${If} $FitbDlg == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0 0 100% 16u "How would you like to install?"
  Pop $0

  ${NSD_CreateRadioButton} 0 22u 100% 14u "Express upgrade  —  keep my data, conversations, and AI models"
  Pop $FitbRadioExpress
  ${NSD_SetState} $FitbRadioExpress ${BST_CHECKED}

  ${NSD_CreateRadioButton} 0 40u 100% 14u "Clean install  —  wipe everything and start fresh"
  Pop $FitbRadioClean

  ${NSD_CreateLabel} 14u 56u 90% 24u "Warning: deletes all Fox data, settings, conversations, and AI models. This cannot be undone."
  Pop $FitbWarnLabel
  SetCtlColors $FitbWarnLabel "FF4444" transparent

  nsDialogs::Show
FunctionEnd

Function FitbModePageLeave
  ${NSD_GetState} $FitbRadioClean $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $FitbInstallMode "1"
  ${Else}
    StrCpy $FitbInstallMode "0"
  ${EndIf}
FunctionEnd
