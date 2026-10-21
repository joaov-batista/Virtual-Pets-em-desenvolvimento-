# Escolhe o certificado na janela "Selecionar um certificado para autenticacao" do Edge do robo eSocial.
# Nao aperta teclas: usa a acessibilidade do Windows (UI Automation) so na janela do Edge aberto com o perfil -Perfil.
# Seleciona o certificado cujo nome contem -Nome e aperta OK. Com -Confirmar 0 aperta Cancelar (teste, sem entrar).
# Saida (ultima linha): ok | teste-ok | sem-edge | sem-janela | sem-certificado | sem-botao
param([string]$Perfil, [int]$Confirmar = 1, [string]$Nome = 'DRILLGEO', [int]$Espera = 12)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$AE = [System.Windows.Automation.AutomationElement]
$TS = [System.Windows.Automation.TreeScope]
$CT = [System.Windows.Automation.ControlType]
$TRUE_ = [System.Windows.Automation.Condition]::TrueCondition

$pids = @(Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" | Where-Object { $_.CommandLine -like "*$Perfil*" } | ForEach-Object { [int]$_.ProcessId })
if (-not $pids) { 'sem-edge'; exit }

function Botao($raiz, $texto) {
  foreach ($b in $raiz.FindAll($TS::Descendants, (New-Object System.Windows.Automation.PropertyCondition($AE::ControlTypeProperty, $CT::Button)))) {
    if ($b.Current.Name -eq $texto) { return $b }
  }
  return $null
}

$fim = (Get-Date).AddSeconds($Espera)
while ((Get-Date) -lt $fim) {
  foreach ($w in $AE::RootElement.FindAll($TS::Children, $TRUE_)) {
    if ($pids -notcontains $w.Current.ProcessId) { continue }
    # a janela do certificado: pelo titulo "Selecionar um certificado..." (na propria janela ou dentro dela)
    $titulo = $null
    if ($w.Current.Name -like 'Selecionar um certificado*') { $titulo = $w } else {
      foreach ($t in $w.FindAll($TS::Descendants, $TRUE_)) { if ($t.Current.Name -like 'Selecionar um certificado*') { $titulo = $t; break } }
    }
    if (-not $titulo) { continue }
    # o certificado da lista (nome com DRILLGEO) e os botoes ficam na mesma janela
    # no Edge a linha do certificado aparece como "List" (classe EdgeCertPickerRow) com o nome do certificado
    $cert = $null
    foreach ($i in $w.FindAll($TS::Descendants, $TRUE_)) {
      $ct = $i.Current.ControlType
      if (($i.Current.ClassName -eq 'EdgeCertPickerRow' -or $ct -eq $CT::List -or $ct -eq $CT::ListItem -or $ct -eq $CT::DataItem) -and $i.Current.Name -like "*$Nome*") { $cert = $i; break }
    }
    if (-not $cert) {
      $dump = Join-Path $env:TEMP 'esocial_cert_arvore.txt'
      $w.FindAll($TS::Descendants, $TRUE_) | ForEach-Object { '{0} | {1} | {2}' -f $_.Current.ControlType.ProgrammaticName, $_.Current.Name, $_.Current.ClassName } | Out-File $dump -Encoding utf8
      'sem-certificado'; exit }
    if ($Confirmar -eq 0) { $nomeBotao = 'Cancelar'; $saida = 'teste-ok' } else { $nomeBotao = 'OK'; $saida = 'ok' }
    # 1) direto: seleciona a linha do certificado e aperta o botao
    foreach ($pat in @([System.Windows.Automation.SelectionItemPattern]::Pattern, [System.Windows.Automation.InvokePattern]::Pattern)) {
      try { $o = $cert.GetCurrentPattern($pat); if ($pat -eq [System.Windows.Automation.SelectionItemPattern]::Pattern) { $o.Select() } else { $o.Invoke() } } catch {}
    }
    try { $cert.SetFocus() } catch {}
    Start-Sleep -Milliseconds 400
    $b = Botao $w $nomeBotao
    if ($b -and $b.Current.IsEnabled) {
      try { $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke(); $saida + ' (direto)'; exit } catch {}
    }
    # 2) teclado, como a usuaria faz (Tab, Tab, Tab, Enter) - SO se a janela da frente for deste Edge
    if ($Confirmar -eq 0) { 'teste-ok (teclado nao testado para nao entrar)'; exit }
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type 'using System; using System.Runtime.InteropServices; public static class Frente { [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow(); [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p); }'
    try { $titulo.SetFocus() } catch {}
    Start-Sleep -Milliseconds 400
    $fp = 0; [void][Frente]::GetWindowThreadProcessId([Frente]::GetForegroundWindow(), [ref]$fp)
    if ($pids -notcontains [int]$fp) { 'sem-foco (janela da frente nao e o Edge do robo)'; exit }
    [System.Windows.Forms.SendKeys]::SendWait('{TAB}'); Start-Sleep -Milliseconds 150
    [System.Windows.Forms.SendKeys]::SendWait('{TAB}'); Start-Sleep -Milliseconds 150
    [System.Windows.Forms.SendKeys]::SendWait('{TAB}'); Start-Sleep -Milliseconds 150
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
    'ok (teclado)'; exit
  }
  Start-Sleep -Milliseconds 500
}
'sem-janela'
