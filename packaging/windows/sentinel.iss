; Instalador Windows (Inno Setup 6) — SENTINEL AI
; Compilar: iscc /DAppVersion=0.1.0 /DSourceDir=..\..\dist\sentinel-agent packaging\windows\sentinel.iss
;
; Instalação por usuário (sem administrador), em %LOCALAPPDATA%\Programs\SentinelAI.
; O agente roda na sessão do usuário (docs/ARQUITETURA.md §12.1); nada é instalado como serviço.
; Sem assinatura de código por enquanto (§20.1): o SmartScreen exibirá um aviso.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\sentinel-agent"
#endif

[Setup]
AppId={{6B1F3C2A-8E4D-4F7A-9C5B-2D8E1A0F4B37}
AppName=Sentinel AI
AppVersion={#AppVersion}
; Strings exibidas ficam em ASCII: o arquivo é UTF-8 sem BOM.
AppVerName=Sentinel AI {#AppVersion} (pre-lancamento)
AppPublisher=PauloEverton05
AppPublisherURL=https://github.com/PauloEverton05/sensor-de-movimento
DefaultDirName={localappdata}\Programs\SentinelAI
DefaultGroupName=Sentinel AI
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000
OutputDir=..\..\dist\installer
OutputBaseFilename=SentinelAI-{#AppVersion}-windows-x64-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\..\LICENSE
UninstallDisplayName=Sentinel AI
CloseApplications=yes

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\THIRD_PARTY_LICENSES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Sentinel AI - Agente"; Filename: "{app}\sentinel-agent.exe"; Parameters: "--console-log"; WorkingDir: "{app}"
Name: "{group}\Sentinel AI - Status do agente"; Filename: "{cmd}"; Parameters: "/k """"{app}\sentinel-ctl.exe"" status"""; WorkingDir: "{app}"
Name: "{group}\Desinstalar Sentinel AI"; Filename: "{uninstallexe}"

[UninstallRun]
; Encerra o agente de forma limpa antes de remover os arquivos (os dados do usuário são preservados).
Filename: "{app}\sentinel-ctl.exe"; Parameters: "shutdown"; Flags: runhidden skipifdoesntexist; RunOnceId: "StopAgent"
