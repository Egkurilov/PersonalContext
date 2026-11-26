#define AppVersion "0.1.0"

[Setup]
AppId={{13A96698-E7A8-4BA4-AD40-012D57D437C1}
AppName=PersonalContext
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\PersonalContext
DefaultGroupName=PersonalContext
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=PersonalContext-Setup
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\PersonalContext.exe

[Files]
Source: "..\dist\PersonalContext\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\PersonalContext"; Filename: "{app}\PersonalContext.exe"

[Code]
#include "VersionGuard.iss"

function StopInstalledApp: Boolean;
var
  ResultCode: Integer;
  Executable: String;
begin
  Executable := ExpandConstant('{app}\PersonalContext.exe');
  Result := True;
  if FileExists(Executable) then
    Result := Exec(Executable, '--shutdown', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not InstalledVersionAllowed then
    Result := 'Установлена более новая или неизвестная версия PersonalContext. Установка отменена.'
  else if not StopInstalledApp then
    Result := 'Не удалось остановить PersonalContext. Закройте приложение и повторите установку.';
end;

function InitializeUninstall: Boolean;
begin
  Result := StopInstalledApp;
  if not Result then
    MsgBox('Не удалось остановить PersonalContext. Закройте приложение и повторите удаление.', mbError, MB_OK);
end;
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usUninstall) and (not UninstallSilent) then
    if MsgBox('Удалить локальные данные PersonalContext, включая резервные копии? Выберите «Нет», чтобы сохранить их.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      if not DelTree(ExpandConstant('{localappdata}\PersonalContext'), True, True, True) then
        MsgBox('Не удалось полностью удалить локальные данные. Проверьте каталог PersonalContext в LocalAppData.', mbError, MB_OK);
end;
