' Robozinho DrillGeo - abre o robô sem janela preta.
' Procura o Python (pythonw.exe) nos lugares de costume; se não achar, avisa em vez de travar.
Option Explicit
Dim fso, sh, pasta, script, py, base, pastaPy, sub_, cand
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
pasta = fso.GetParentFolderName(WScript.ScriptFullName)
script = pasta & "\robozinho.py"
py = ""

' 1) Gerenciador de instalação do Python (python.org, 3.14+)
cand = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Python\bin\pythonw.exe"
If fso.FileExists(cand) Then py = cand

' 2) Instalações clássicas: %LOCALAPPDATA%\Programs\Python\Python3xx e C:\Program Files\Python3xx
If py = "" Then
  For Each base In Array(sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python", _
                         sh.ExpandEnvironmentStrings("%ProgramFiles%"))
    If fso.FolderExists(base) Then
      For Each sub_ In fso.GetFolder(base).SubFolders
        If LCase(Left(sub_.Name, 7)) = "python3" Then
          If fso.FileExists(sub_.Path & "\pythonw.exe") Then py = sub_.Path & "\pythonw.exe"
        End If
      Next
    End If
  Next
End If

' 3) Lançador "pyw"
If py = "" Then
  For Each cand In Array(sh.ExpandEnvironmentStrings("%WINDIR%") & "\pyw.exe", _
                         sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Launcher\pyw.exe")
    If py = "" And fso.FileExists(cand) Then py = cand
  Next
End If

If py = "" Then
  MsgBox "O Robozinho precisa do Python 3 para funcionar e não encontrei o Python neste computador." & vbCrLf & vbCrLf & _
         "Peça para instalar o Python (gratuito, python.org) e abra o Robozinho de novo.", _
         vbExclamation, "Robozinho DrillGeo"
  WScript.Quit 1
End If

If Not fso.FileExists(script) Then
  MsgBox "Não achei o arquivo robozinho.py em:" & vbCrLf & pasta, vbExclamation, "Robozinho DrillGeo"
  WScript.Quit 1
End If

sh.CurrentDirectory = pasta
sh.Run """" & py & """ """ & script & """", 0, False
