; Visualised Windows installer (built by the release workflow from the Nuitka output).
; Installs for the current user (no admin), associates .vml and .vmlproj files, and can add VML to the PATH.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{4E7B2C91-6A3D-4F58-9C0B-2D8E5A71B6F4}
AppName=Visualised
AppVersion={#AppVersion}
AppVerName=Visualised {#AppVersion}
AppPublisher=Wallisoft
AppPublisherURL=https://visualised.io
DefaultDirName={autopf}\Visualised
DefaultGroupName=Visualised
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=Visualised-Setup
SetupIconFile=art\vml.ico
UninstallDisplayIcon={app}\vml.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ChangesAssociations=yes
ChangesEnvironment=yes
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "addtopath"; Description: "Add vml to my PATH (so scripts and terminals can run it)"; GroupDescription: "Options:"

[Files]
; The whole compiled folder. Qt stays as separate, replaceable libraries (LGPL).
Source: "..\build\vml.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "THIRD-PARTY-NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Visualised"; Filename: "{app}\vml.exe"
Name: "{group}\Third-party notices"; Filename: "{app}\THIRD-PARTY-NOTICES.txt"
Name: "{autodesktop}\Visualised"; Filename: "{app}\vml.exe"; Tasks: desktopicon

[Registry]
; double-clicking a .vml file runs it
Root: HKCU; Subkey: "Software\Classes\.vml"; ValueType: string; ValueName: ""; ValueData: "VML.Form"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\VML.Form"; ValueType: string; ValueName: ""; ValueData: "VML form"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\VML.Form\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\vml.exe,0"
Root: HKCU; Subkey: "Software\Classes\VML.Form\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\vml.exe"" ""%1"""
; ...and double-clicking a .vmlproj runs that project
Root: HKCU; Subkey: "Software\Classes\.vmlproj"; ValueType: string; ValueName: ""; ValueData: "VML.Project"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\VML.Project"; ValueType: string; ValueName: ""; ValueData: "Visualised project"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\VML.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\vml.exe,0"
Root: HKCU; Subkey: "Software\Classes\VML.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\vml.exe"" ""%1"""
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\vml.exe"; Description: "Open Visualised"; Flags: nowait postinstall skipifsilent

[Code]
function NeedsAddPath(Dir: string): boolean;
var
  Path: string;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', Path) then
    Path := '';
  Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Path) + ';') = 0;
end;
