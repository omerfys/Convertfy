; Inno Setup script — per-user install, no admin rights needed.
#define AppVersion GetEnv("DS_VERSION")
#if AppVersion == ""
  #define AppVersion "1.1.0"
#endif

[Setup]
AppId={{A5B876C1-4D3E-4B12-9A88-84D63C1E2001}
AppName=Convertfy
AppVersion={#AppVersion}
AppPublisher=Convertfy
DefaultDirName={localappdata}\Programs\Convertfy
DefaultGroupName=Convertfy
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Convertfy-Setup
SetupIconFile=..\convertfy\assets\convertfy.ico
UninstallDisplayIcon={app}\Convertfy.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "autostart"; Description: "Start Convertfy when I sign in to Windows"; Flags: checkedonce
Name: "contextmenu"; Description: "Add ""Convertfy"" to the right-click menu for files"; Flags: checkedonce
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\Convertfy\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Convertfy"; Filename: "{app}\Convertfy.exe"
Name: "{autodesktop}\Convertfy"; Filename: "{app}\Convertfy.exe"; Tasks: desktopicon
Name: "{usersendto}\Convertfy"; Filename: "{app}\Convertfy.exe"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Convertfy"; ValueData: """{app}\Convertfy.exe"" --quiet"; Tasks: autostart; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\*\shell\Convertfy"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Convertfy…"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\*\shell\Convertfy"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\Convertfy.exe"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\*\shell\Convertfy"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\*\shell\Convertfy\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Convertfy.exe"" ""%1"""; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Convertfy"; Flags: uninsdeletekey

[Run]
Filename: "{app}\Convertfy.exe"; Description: "Launch Convertfy now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM Convertfy.exe"; Flags: runhidden; RunOnceId: "KillConvertfy"
