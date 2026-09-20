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
; Always let the user pick the install folder (Inno hides this page on an
; upgrade by default, which is what made it "missing").
DisableDirPage=no
UsePreviousAppDir=yes
; Close a running LimpiaPro through the Windows Restart Manager before
; replacing files, and do NOT relaunch it behind the user's back.
CloseApplications=yes
CloseApplicationsFilter={#AppExeName}
RestartApplications=no
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

[CustomMessages]
spanish.PreviousVersion=Se detecto LimpiaPro %1 instalado en:%n%2%n%nSe actualizara a la version %3. En el siguiente paso puedes cambiar la carpeta de instalacion.
english.PreviousVersion=LimpiaPro %1 is already installed in:%n%2%n%nIt will be updated to %3. You can change the install folder in the next step.
spanish.AlreadyCurrent=LimpiaPro %1 ya esta instalado en:%n%2%n%nSe reinstalara sobre esa misma carpeta (puedes cambiarla en el siguiente paso).
english.AlreadyCurrent=LimpiaPro %1 is already installed in:%n%2%n%nIt will be reinstalled in place (you can change the folder in the next step).
spanish.RemoveOld=La version anterior estaba en:%n%1%n%nSe ha instalado en otra carpeta. Quieres eliminar la instalacion antigua?
english.RemoveOld=The previous version was in:%n%1%n%nThe app was installed in a different folder. Remove the old installation?

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
{ ---------------------------------------------------------------------------
  Previous-installation awareness.

  Inno already reuses the previous folder (UsePreviousAppDir=yes) and keeps
  the same uninstall entry (same AppId), but it did so SILENTLY. Here the
  user is told which version was found and where, and if they pick a
  different folder the old installation is removed instead of being left
  orphaned.
  --------------------------------------------------------------------------- }

const
  { Inno stores the uninstall entry under "<AppId>_is1" (HKCU for a
    per-user install, HKLM when installed elevated). The GUID MUST match
    the AppId above, or an existing install would not be recognized. }
  UninstallRegKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{8F2C41B7-9A5E-4C63-9F1D-2B7E5A3C6D18}_is1';

var
  PreviousInstallDir: String;
  PreviousVersion: String;

function GetInstalledValue(const Name: String): String;
var
  Value: String;
begin
  Result := '';
  if RegQueryStringValue(HKCU, UninstallRegKey, Name, Value) then
    Result := Value
  else if RegQueryStringValue(HKLM, UninstallRegKey, Name, Value) then
    Result := Value;
end;

function InitializeSetup(): Boolean;
var
  Message: String;
begin
  Result := True;
  PreviousVersion := GetInstalledValue('DisplayVersion');
  PreviousInstallDir := GetInstalledValue('InstallLocation');
  if PreviousVersion = '' then
    Exit;

  { Tell the user what was found. In silent mode the message is skipped so
    unattended installs stay quiet. }
  if WizardSilent then
    Exit;
  { NOTE: no line here may start with '[' - Inno's [Code] parser would
    read it as a section header. }
  if CompareText(PreviousVersion, '{#AppVersion}') = 0 then
  begin
    Message := FmtMessage(CustomMessage('AlreadyCurrent'), [PreviousVersion,
      PreviousInstallDir]);
    MsgBox(Message, mbInformation, MB_OK);
  end
  else
  begin
    Message := FmtMessage(CustomMessage('PreviousVersion'), [PreviousVersion,
      PreviousInstallDir, '{#AppVersion}']);
    MsgBox(Message, mbInformation, MB_OK);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  NewDir: String;
  Message: String;
begin
  if CurStep <> ssPostInstall then
    Exit;
  if PreviousInstallDir = '' then
    Exit;
  NewDir := ExpandConstant('{app}');
  { Same folder (the normal upgrade): nothing to clean up. }
  if CompareText(AddBackslash(PreviousInstallDir),
                 AddBackslash(NewDir)) = 0 then
    Exit;
  if not DirExists(PreviousInstallDir) then
    Exit;
  Message := FmtMessage(CustomMessage('RemoveOld'), [PreviousInstallDir]);
  if WizardSilent or (MsgBox(Message, mbConfirmation, MB_YESNO) = IDYES) then
    DelTree(PreviousInstallDir, True, True, True);
end;

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
