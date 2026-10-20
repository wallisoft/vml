; TopCat's Windows installer (Inno Setup): per user, no admin needed.
#ifndef AppVersion
  #define AppVersion "0.0"
#endif

[Setup]
AppId={{5EC02ACE-942C-4B60-8C12-5AA341DF0070}
AppName=TopCat
AppVersion={#AppVersion}
AppPublisher=Wallisoft
AppPublisherURL=https://topcat.vml.onl
DefaultDirName={localappdata}\Programs\TopCat
DefaultGroupName=TopCat
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=TopCat-Setup
SetupIconFile=..\..\build\topcat.ico
UninstallDisplayIcon={app}\TopCat.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Files]
Source: "..\..\build\topcat.dist\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\TopCat"; Filename: "{app}\TopCat.exe"
Name: "{userdesktop}\TopCat"; Filename: "{app}\TopCat.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "A TopCat icon on the desktop"; Flags: unchecked

[Run]
Filename: "{app}\TopCat.exe"; Description: "Start TopCat now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c taskkill /im TopCat.exe /f"; Flags: runhidden; RunOnceId: "StopTopCat"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
