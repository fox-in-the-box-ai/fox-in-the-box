!macro customInit
  DetailPrint "Stopping running Fox in the box processes..."
  nsExec::ExecToLog 'taskkill /IM "FoxInTheBox.exe" /F /T'
  nsExec::ExecToLog 'taskkill /IM "Fox in the Box.exe" /F /T'
  nsExec::ExecToLog 'taskkill /IM "fox-in-the-box.exe" /F /T'
  Sleep 1000
!macroend
