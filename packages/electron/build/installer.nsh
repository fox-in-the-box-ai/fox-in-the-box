!macro customInit
  DetailPrint "Stopping running Fox in the box processes..."
  nsExec::ExecToLog 'taskkill /IM "FoxInTheBox.exe" /F /T'
  nsExec::ExecToLog 'taskkill /IM "Fox in the Box.exe" /F /T'
  nsExec::ExecToLog 'taskkill /IM "fox-in-the-box.exe" /F /T'
  Sleep 1000
!macroend

; Keep value name in sync with packages/electron/src/windows-run-once.js (VALUE_NAME).
!macro customUnInstall
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\RunOnce" "FoxInTheBoxResumeSetup"
!macroend
