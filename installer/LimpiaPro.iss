; LimpiaPro installer (Inno Setup 6).
;
; Installs the portable OneDir build so it starts instantly (no %TEMP%
; unpacking) and leaves a proper uninstall entry:
;   - per-user install by default (%LOCALAPPDATA%\Programs\LimpiaPro):
;     no administrator prompt, works on locked-down machines;
;   - Start-menu entry + optional desktop shortcut pointing at the
;     INSTALLED exe (never at a build folder);
;   - /PORTABLE=1 installs anywhere without a shortcut (USB sticks);
;   - uninstaller removes the program files only: settings, cache and logs
;     under %LOCALAPPDATA%\LimpiaPro are the user's data and are kept
;     unless /PURGEDATA=1 is passed to the uninstaller.
;
; Build:  ISCC.exe /DAppVersion=2.10.4 LimpiaPro.iss
; The version is injected by upload_release.py so it always matches
; limpiapro.__init__.APP_VERSION.

#define AppName "LimpiaPro"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppPublisher "Luis Miguel Mendoza Guevara"
#define AppExeName "LimpiaPro.exe"
#define SourceDir "..\dist\LimpiaProPortable"

[Setup]
AppId={{8F2C41B7-9A5E-4C63-9F1D-2B7E5A3C6D18}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install: no UAC prompt for the installer itself. The app still
; elevates at runtime when it needs administrator rights.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename={#AppName}Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName} {#AppVersion}
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile=..\assets\limpiadora.ico
LicenseFile=..\LICENSE
MinVersion=10.0
; The exe is unsigned; SmartScreen may warn on first run. The generated
; installer is published with SHA256SUMS.txt for verification.

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "startupicon"; Description: "Iniciar LimpiaPro con Windows"; \
    GroupDescription: "Arranque"; Flags: unchecked

[Files]
; OneDir payload: _internal\ holds Qt and the bundled data (style.qss,
; winapp2.ini, icon). The whole folder is installed as-is.
Source: "{#SourceDir}\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\_internal\*"; DestDir: "{app}\_internal"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; \
    Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; \
    Tasks: startupicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The uninstaller removes the files it installed; this also drops the
; (now empty) install folder itself. The app's data lives in
; %LOCALAPPDATA%\LimpiaPro and is preserved on purpose.
Type: filesandordirs; Name: "{app}"

[Code]
{ Optional data purge: "LimpiaProSetup.exe /PURGEDATA=1" during uninstall
  (or "unins000.exe /PURGEDATA=1") removes the user data too. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if ExpandConstant('{param:PURGEDATA|0}') = '1' then
    begin
      DataDir := ExpandConstant('{localappdata}\LimpiaPro');
      if DirExists(DataDir) then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
