; Instalador Windows 11 (Inno Setup 6) — SENTINEL AI
; Compilar: uv run python scripts/build_installer.py
;
; Instalação por usuário (sem administrador), em %LOCALAPPDATA%\Programs\SentinelAI.
; O agente roda na sessão do usuário (docs/ARQUITETURA.md §12.1); nada é instalado como serviço.
; Sem assinatura de código por enquanto (§20.1): o SmartScreen exibirá um aviso.
; Strings exibidas ficam em ASCII: o arquivo é UTF-8 sem BOM.

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
AppVerName=Sentinel AI {#AppVersion} (pre-lancamento)
AppPublisher=PauloEverton05
AppPublisherURL=https://github.com/PauloEverton05/sensor-de-movimento
DefaultDirName={localappdata}\Programs\SentinelAI
DefaultGroupName=Sentinel AI
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Windows 11 (build 22000) ou superior
MinVersion=10.0.22000
OutputDir=..\..\dist\installer
OutputBaseFilename=SentinelAI-{#AppVersion}-windows11-x64-setup
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
Source: "..\..\docs\TESTE-FASE-3.md"; DestDir: "{app}"; DestName: "COMO-TESTAR.txt"; Flags: ignoreversion
Source: "..\..\THIRD_PARTY_LICENSES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Testes guiados: sobem o agente sozinhos e mostram o resultado na janela.
Name: "{group}\1 - Teste da webcam (1 minuto)"; Filename: "{cmd}"; Parameters: "/k sentinel-ctl.exe webcam-test"; WorkingDir: "{app}"
Name: "{group}\2 - Teste de tela bloqueada"; Filename: "{cmd}"; Parameters: "/k sentinel-ctl.exe lock-test"; WorkingDir: "{app}"
Name: "{group}\3 - Teste de controle (sem inibir o sono)"; Filename: "{cmd}"; Parameters: "/k sentinel-ctl.exe lock-test --allow-sleep"; WorkingDir: "{app}"
Name: "{group}\Prompt do Sentinel AI (comandos avancados)"; Filename: "{cmd}"; Parameters: "/k sentinel-ctl.exe --help"; WorkingDir: "{app}"
Name: "{group}\Agente Sentinel AI"; Filename: "{app}\sentinel-agent.exe"; Parameters: "--console-log"; WorkingDir: "{app}"
Name: "{group}\Pasta de resultados dos testes"; Filename: "{localappdata}\SentinelAI\diagnostics"
Name: "{group}\Como testar"; Filename: "{app}\COMO-TESTAR.txt"
Name: "{group}\Desinstalar Sentinel AI"; Filename: "{uninstallexe}"

[Dirs]
Name: "{localappdata}\SentinelAI\diagnostics"; Flags: uninsneveruninstall

[UninstallRun]
; Encerra o agente de forma limpa antes de remover os arquivos (os dados do usuário são preservados).
Filename: "{app}\sentinel-ctl.exe"; Parameters: "shutdown"; Flags: runhidden skipifdoesntexist; RunOnceId: "StopAgent"
