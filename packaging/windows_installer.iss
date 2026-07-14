; Inno Setup script for SlackMsgReader.
; Compiled in CI via `ISCC packaging\windows_installer.iss` after PyInstaller
; has produced packaging\dist\SlackMsgReader\SlackMsgReader.exe.

#define MyAppName "SlackMsgReader"
#define MyAppVersion "0.1.0"
#define MyAppExeName "SlackMsgReader.exe"

[Setup]
AppId={{B6C6C7F0-7B8B-4F2C-9B7B-6E7D9E2F1A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=SlackMsgReaderSetup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\SlackMsgReader\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent unchecked
