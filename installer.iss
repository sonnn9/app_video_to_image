; ================================================================
;  Inno Setup script for Tach Anh Tu Video
;  Output: installer\TachAnhTuVideo_Setup_v<ver>.exe
; ================================================================

#define MyAppName        "Tach Anh Tu Video"
#define MyAppNameVi      "Tách Ảnh Từ Video"
#define MyAppVersion     "1.0.0"
#define MyAppPublisher   "requadimat"
#define MyAppExeName     "TachAnhTuVideo.exe"
#define MyAppSourceDir   "dist\TachAnhTuVideo"

[Setup]
AppId={{08FE90F1-B9A8-4684-B2B5-B2F7C253B872}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\TachAnhTuVideo
DefaultGroupName={#MyAppNameVi}
DisableProgramGroupPage=yes
UninstallDisplayName={#MyAppNameVi} {#MyAppVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=installer
OutputBaseFilename=TachAnhTuVideo_Setup_v{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
DisableWelcomePage=no
ShowLanguageDialog=yes

[Languages]
Name: "english";    MessagesFile: "compiler:Default.isl"
; Vietnamese translation shipped with Inno Setup community languages pack
; Name: "vietnamese"; MessagesFile: "compiler:Languages\Vietnamese.isl"

[Tasks]
Name: "desktopicon";  Description: "Tạo shortcut trên Desktop"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "quicklaunchicon"; Description: "Tạo shortcut Quick Launch"; GroupDescription: "Shortcuts:"; Flags: unchecked; OnlyBelowVersion: 6.1

[Files]
; Bundle the whole PyInstaller output directory
Source: "{#MyAppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppNameVi}";          Filename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\Uninstall {#MyAppNameVi}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppNameVi}";            Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Mở {#MyAppNameVi} ngay"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
