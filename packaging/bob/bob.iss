; Bob's Windows installer (Inno Setup): per user, no admin needed.
#ifndef AppVersion
  #define AppVersion "0.0"
#endif

[Setup]
AppId={{34F05882-E3DB-4EAF-A5AE-8EC997933860}
AppName=Bob
AppVersion={#AppVersion}
AppPublisher=Wallisoft
AppPublisherURL=https://bob.vml.onl
DefaultDirName={localappdata}\Programs\Bob
DefaultGroupName=Bob
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=Bob-Setup
SetupIconFile=..\..\build\bob.ico
UninstallDisplayIcon={app}\Bob.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Files]
Source: "..\..\build\bob.dist\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Bob"; Filename: "{app}\Bob.exe"
Name: "{userdesktop}\Bob"; Filename: "{app}\Bob.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "A Bob icon on the desktop"; Flags: unchecked

[Run]
Filename: "{app}\Bob.exe"; Description: "Start Bob now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c taskkill /im Bob.exe /f"; Flags: runhidden; RunOnceId: "StopBob"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
