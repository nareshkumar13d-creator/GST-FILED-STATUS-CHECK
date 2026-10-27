[Setup]
AppName=GST Portal Checker
AppVersion=1.0
AppId={{B7A3C1E2-5D4F-4A8B-9C61-2F0E7D3A9B15}
DefaultDirName={autopf}\GSTPortalChecker
DefaultGroupName=GST Portal Checker
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=GSTPortal_Setup
SetupIconFile=gst_icon.ico
UninstallDisplayIcon={app}\GSTPortal.exe
Compression=lzma
SolidCompression=yes

[Tasks]
Name: "desktopicon"; Description: "Desktop par shortcut banao"; Flags: checkedonce

[Files]
Source: "dist\GSTPortal.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\GST Portal Checker"; Filename: "{app}\GSTPortal.exe"
Name: "{group}\Uninstall GST Portal Checker"; Filename: "{uninstallexe}"
Name: "{autodesktop}\GST Portal Checker"; Filename: "{app}\GSTPortal.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\GSTPortal.exe"; Description: "GST Portal Checker abhi chalao"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\gst_settings.json"
Type: files; Name: "{app}\gst_session.json"
