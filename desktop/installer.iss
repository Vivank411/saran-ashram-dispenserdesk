; Inno Setup script for the Dispensary Desk Windows installer. Build with desktop\build.bat.
; One installer, two choices on the first page:
;   Main computer (server)  - runs the app + database for the whole hospital network, starts with Windows
;   Counter computer         - only a shortcut that opens the app from the main computer

#define AppName "Dispensary Desk"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef DistDir
  #define DistDir "dist\DispensaryDesk"
#endif
#define AppExe "DispensaryDesk.exe"
#define Port "8000"

[Setup]
AppId={{6F3C2A1E-9B7D-4C58-A1E2-5D0F8B3C7A91}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Saran Ashram Hospital
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=DispensaryDesk-Setup-{#AppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=no

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{commonappdata}\DispensaryDesk"; Check: IsServer

[Icons]
; Server PC
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--open"; Check: IsServer
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--open"; Check: IsServer
Name: "{group}\Back up now"; Filename: "{app}\{#AppExe}"; Parameters: "--backup-now"; Check: IsServer
Name: "{group}\Data and backups folder"; Filename: "{commonappdata}\DispensaryDesk"; Check: IsServer
; Counter PC
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--open {code:ServerUrl}"; Check: IsCounter
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--open {code:ServerUrl}"; Check: IsCounter
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#AppExe}"; Parameters: "--install-server"; StatusMsg: "Starting the Dispensary Desk server..."; Flags: runhidden waituntilterminated; Check: IsServer
Filename: "{app}\{#AppExe}"; Parameters: "--open"; Description: "Open Dispensary Desk now"; Flags: postinstall nowait skipifsilent; Check: IsServer
Filename: "{app}\{#AppExe}"; Parameters: "--open {code:ServerUrl}"; Description: "Open Dispensary Desk now"; Flags: postinstall nowait skipifsilent; Check: IsCounter

[UninstallRun]
Filename: "{app}\{#AppExe}"; Parameters: "--uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "StopServer"

[Code]
var
  RolePage: TInputOptionWizardPage;
  ServerPage: TInputQueryWizardPage;

function IsServer: Boolean;
begin
  Result := RolePage.SelectedValueIndex = 0;
end;

function IsCounter: Boolean;
begin
  Result := not IsServer;
end;

function ServerUrl(Param: String): String;
var
  S: String;
begin
  S := Trim(ServerPage.Values[0]);
  if (Pos('http://', Lowercase(S)) <> 1) and (Pos('https://', Lowercase(S)) <> 1) then
    S := 'http://' + S;
  { add the default port when none was typed after the host name }
  if Pos(':', Copy(S, Pos('//', S) + 2, Length(S))) = 0 then
    S := S + ':{#Port}';
  Result := S;
end;

procedure InitializeWizard;
begin
  RolePage := CreateInputOptionPage(wpWelcome, 'Which computer is this?',
    'Install the main computer first, then the counters.',
    'Choose how this computer will be used:', True, False);
  RolePage.Add('Main computer (server): keeps all bills, stock and accounts, and starts automatically with Windows. Install this on ONE computer only.');
  RolePage.Add('Counter computer: opens Dispensary Desk from the main computer over the hospital network.');
  RolePage.SelectedValueIndex := StrToIntDef(GetPreviousData('Role', '0'), 0);

  ServerPage := CreateInputQueryPage(RolePage.ID, 'Main computer address',
    'Where is Dispensary Desk installed?',
    'Type the name or IP address of the main computer. It is shown on the last page of the main computer''s installation (for example DISPENSARY-PC or 192.168.1.20).');
  ServerPage.Add('Main computer name or address:', False);
  ServerPage.Values[0] := GetPreviousData('Server', '');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = ServerPage.ID) and IsServer;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = ServerPage.ID) and (Trim(ServerPage.Values[0]) = '') then
  begin
    MsgBox('Please type the main computer''s name or IP address.', mbError, MB_OK);
    Result := False;
  end;
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  SetPreviousData(PreviousDataKey, 'Role', IntToStr(RolePage.SelectedValueIndex));
  SetPreviousData(PreviousDataKey, 'Server', ServerPage.Values[0]);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
begin
  { upgrading: stop the running server so its files can be replaced }
  if CurStep = ssInstall then
  begin
    Exec(ExpandConstant('{sys}\schtasks.exe'), '/End /TN "Dispensary Desk Server"', '', SW_HIDE, ewWaitUntilTerminated, Code);
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, Code);
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and IsServer then
    WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10#13#10 +
      'This is the MAIN computer. When installing on counter computers, enter this address:' + #13#10#13#10 +
      '    ' + GetComputerNameString + #13#10#13#10 +
      'Counters can also open http://' + GetComputerNameString + ':{#Port} in a browser.' + #13#10 +
      'Keep this computer switched on while the dispensary is open.';
end;
