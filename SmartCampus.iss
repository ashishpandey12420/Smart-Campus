[Setup]
AppId={{A1B2C3D4-E5F6-47A8-90AB-1234567890AB}
AppName=Smart Campus
AppVersion=1.0.0
AppPublisher=Smart Campus
DefaultDirName={autopf}\Smart Campus
DefaultGroupName=Smart Campus
OutputDir=installer_output
OutputBaseFilename=Smart Campus Setup
SetupIconFile=assets\smart-campus.ico
UninstallDisplayIcon={app}\Smart Campus.exe
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64

[Tasks]
Name: "desktopicon"; Description: "Create a Desktop Shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "dist\Smart Campus\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Smart Campus"; Filename: "{app}\Smart Campus.exe"
Name: "{autodesktop}\Smart Campus"; Filename: "{app}\Smart Campus.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Smart Campus.exe"; Description: "Launch Smart Campus"; Flags: postinstall nowait skipifsilent
