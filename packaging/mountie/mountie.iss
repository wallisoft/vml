; Mountie's Windows installer (Inno Setup): per user, no admin needed. Built by mountie-release.yml.
#ifndef AppVersion
  #define AppVersion "0.0"
#endif

[Setup]
AppId={{6A3F5E2C-8B7D-4C61-9E0A-4D2B7C9F1E35}
AppName=Mountie
AppVersion={#AppVersion}
AppPublisher=Wallisoft
AppPublisherURL=https://ssh-drive.eur.bz
DefaultDirName={localappdata}\Programs\Mountie
DefaultGroupName=Mountie
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=Mountie-Setup
SetupIconFile=..\..\build\mountie.ico
UninstallDisplayIcon={app}\Mountie.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Files]
Source: "..\..\build\mountie.dist\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Mountie"; Filename: "{app}\Mountie.exe"
Name: "{userdesktop}\Mountie"; Filename: "{app}\Mountie.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "A Mountie icon on the desktop"; Flags: unchecked

[Run]
Filename: "{app}\Mountie.exe"; Description: "Start Mountie now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c taskkill /im Mountie.exe /f"; Flags: runhidden; RunOnceId: "StopMountie"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
