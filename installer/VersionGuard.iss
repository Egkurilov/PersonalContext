const
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{13A96698-E7A8-4BA4-AD40-012D57D437C1}_is1';

function NextVersionPart(var Remaining: String; var Part: Integer): Boolean;
var
  Token: String;
  Separator, I: Integer;
begin
  Result := False;
  if Remaining = '' then begin Part := 0; Result := True; exit; end;
  Separator := Pos('.', Remaining);
  if Separator = 0 then begin Token := Remaining; Remaining := ''; end
  else begin Token := Copy(Remaining, 1, Separator - 1); Delete(Remaining, 1, Separator); end;
  if (Length(Token) = 0) or (Length(Token) > 9) then exit;
  for I := 1 to Length(Token) do
    if (Token[I] < '0') or (Token[I] > '9') then exit;
  Part := StrToIntDef(Token, -1);
  Result := Part >= 0;
end;

function InstalledVersionAllowed: Boolean;
var
  Installed, Candidate: String;
  I, LeftPart, RightPart, Comparison: Integer;
begin
  Result := False;
  if not RegKeyExists(HKCU, UninstallKey) then begin Result := True; exit; end;
  if not RegQueryStringValue(HKCU, UninstallKey, 'DisplayVersion', Installed) then exit;
  Candidate := '{#AppVersion}';
  if (Installed = '') or (Copy(Installed, Length(Installed), 1) = '.') then exit;
  Comparison := 0;
  for I := 1 to 4 do begin
    if not NextVersionPart(Installed, LeftPart) then exit;
    if not NextVersionPart(Candidate, RightPart) then exit;
    if Comparison = 0 then begin
      if LeftPart > RightPart then Comparison := 1
      else if LeftPart < RightPart then Comparison := -1;
    end;
  end;
  Result := (Installed = '') and (Candidate = '') and (Comparison <= 0);
end;
