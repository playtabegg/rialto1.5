; Rialto's Setup (Rialto-X.Y.Z-Setup.exe): installs Rialto for the person who runs it, with no administrator prompt.
;
; Built with the Inno Setup 6.5.4 that Rialto itself carries (helpers\inno\ISCC.exe):
;
;   ISCC.exe /Q /DPackageDir="<the Rialto 1.5.1 Disc Maker folder>" /DAppVersion=1.5.1
;            /DIconFile="assets\bird_icon.ico" /O"<output folder>" packaging\rialto-setup.iss
;
; A signed build passes the signing command too, after Rialto.exe itself is signed, and Inno signs the
; uninstaller and the finished Setup with it (and refuses a step that leaves no signature):
;
;   ISCC.exe ... /DSignWith=wti "/Swti=<signtool.exe> sign /fd SHA256 /tr <timestamp server> /td SHA256 ... $f"
;
; Why per-user: Rialto keeps its settings (config.json, signing_config.json, last_profile.json,
; last_session.json), templates\, input\, output\, docs\, tools\ and build_log.txt beside Rialto.exe,
; and writes config.json at every launch. Under Program Files a standard user cannot write there.
; {localappdata}\Programs is the folder Windows gives per-user programs.
;
; An upgrade replaces the program (Rialto.exe, menu.exe, the two texts, licenses\) and never touches
; what the person made: settings, profiles, input, output, tools\.

#ifndef PackageDir
  #error Pass /DPackageDir=<the "Rialto X.Y.Z Disc Maker" folder>
#endif
#ifndef AppVersion
  #error Pass /DAppVersion=<X.Y.Z, the __version__ in Rialto.pyw>
#endif

; One version: the one Rialto.exe carries. A mismatch stops the compile.
#define ExeVersion GetStringFileInfo(AddBackslash(PackageDir) + "Rialto.exe", "ProductVersion")
#if ExeVersion != AppVersion + ".0"
  #pragma message "Rialto.exe ProductVersion is " + ExeVersion + ", AppVersion is " + AppVersion
  #error Rialto.exe is not the version this installer is being built for
#endif

#define AppId "CB8B5DDB-EE8E-42C5-BCB1-457E8DC81CEE"

; The shortcuts' name, the version's: "Rialto 1.5.1" in the Start Menu and on the desktop (his ruling,
; 19 Oct 2026). 1.5.1 is the first Setup, so nothing older to remove; from 1.5.2 on, a Setup removes the
; earlier version's shortcuts that point at this install's Rialto.exe.
#ifndef ShortcutName
  #define ShortcutName "Rialto " + AppVersion
#endif

[Setup]
; Fixed for every Rialto 1.5.x, never reused: an upgrade finds the old install by it.
; (Rialto's own game installers set no AppId, so theirs is their AppName; a GUID cannot collide.)
; "{{" is a literal "{"; the closing "}" is needed too, or the key is "{GUID_is1" (seen in the first proof run).
AppId={{{#AppId}}
AppName=Rialto {#AppVersion}
AppVersion={#AppVersion}
AppVerName=Rialto {#AppVersion}
AppPublisher=We The Indies, LLC
AppPublisherURL=https://github.com/playtabegg/rialto1.5
AppSupportURL=https://github.com/playtabegg/rialto1.5
AppUpdatesURL=https://github.com/playtabegg/rialto1.5/releases/latest
AppCopyright=Copyright (c) 2025-2026 We the Indies. MIT License.
VersionInfoVersion={#AppVersion}.0
VersionInfoProductVersion={#AppVersion}.0
VersionInfoProductTextVersion={#AppVersion}
VersionInfoTextVersion={#AppVersion}
VersionInfoCompany=We The Indies, LLC
VersionInfoDescription=Rialto {#AppVersion} Setup
VersionInfoProductName=Rialto
VersionInfoCopyright=Copyright (c) 2025-2026 We the Indies. MIT License.

; Per-user, never elevated, and no switch can turn it into an all-users install.
PrivilegesRequired=lowest
; The folder keeps the line's name: every 1.5.x upgrades in place (UsePreviousAppDir), so a folder named
; for one version would hold the next.
DefaultDirName={localappdata}\Programs\Rialto 1.5
UsePreviousAppDir=yes
DisableDirPage=auto
DisableProgramGroupPage=yes
DisableWelcomePage=yes
DisableReadyPage=no
UsePreviousTasks=yes

; Rialto.exe and menu.exe are 64-bit Python 3.12 builds: Windows 8.1 or later.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=6.3

; No restart, ever: a running Rialto or menu preview is closed through Restart Manager, not replaced at boot.
CloseApplications=yes
RestartApplications=no
RestartIfNeededByRun=no
ChangesAssociations=no
ChangesEnvironment=no
SetupMutex=RialtoSetup_{#AppId}
; Rialto.exe holds this name while it runs (Rialto.pyw, at start), so Setup asks the person to close it
; first. Restart Manager alone closed the window but left the one-file EXE's first process holding
; Rialto.exe, and the upgrade could not replace it.
AppMutex=RialtoDiscMaker15

OutputBaseFilename=Rialto-{#AppVersion}-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
#ifdef IconFile
SetupIconFile={#IconFile}
#endif
UninstallDisplayIcon={app}\Rialto.exe
SetupLogging=yes

#ifdef SignWith
SignTool={#SignWith}
SignedUninstaller=yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.ProtectedFolder=Rialto keeps its settings, profiles, input and output in the folder it is installed in, so it needs a folder you can write to.%n%n%1 is inside a protected Windows folder.%n%nGo back and choose a folder of your own, such as %2.
english.KeptYourFiles=Rialto is removed.%n%nYour settings, profiles, input and output are still in:%n%1%n%nDelete that folder yourself when you no longer need them.
english.OpenRialto=Open Rialto now

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Dirs]
; Made empty; removed at uninstall only if still empty.
Name: "{app}\input"
Name: "{app}\output"
Name: "{app}\templates"

[InstallDelete]
; licenses\ is the program's own: replaced whole, so a license a release drops does not linger.
Type: filesandordirs; Name: "{app}\licenses"

[Files]
; The program: replaced by every install and upgrade, by name, never by wildcard, so nothing a test run
; left in the package (a config.json, an ISO) can ride along.
Source: "{#PackageDir}\Rialto.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PackageDir}\menu.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PackageDir}\README.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PackageDir}\IMPORTANT - Before You Build.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PackageDir}\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs
; The samples: put down only where missing and never overwritten. Uninstall leaves them to [Code], which
; removes each only while it is still exactly what Setup put down.
Source: "{#PackageDir}\input\SampleGame\*"; DestDir: "{app}\input\SampleGame"; Flags: onlyifdoesntexist uninsneveruninstall recursesubdirs createallsubdirs
Source: "{#PackageDir}\templates\Sample Game.json"; DestDir: "{app}\templates"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
; /NOSHORTCUTS: the release check's throwaway install, so it never touches the real shortcuts.
Name: "{autoprograms}\{#ShortcutName}"; Filename: "{app}\Rialto.exe"; WorkingDir: "{app}"; Comment: "Rialto, the disc maker"; Check: WantShortcuts
Name: "{autodesktop}\{#ShortcutName}"; Filename: "{app}\Rialto.exe"; WorkingDir: "{app}"; Comment: "Rialto, the disc maker"; Tasks: desktopicon; Check: WantShortcuts

[Run]
Filename: "{app}\Rialto.exe"; Description: "{cm:OpenRialto}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
; The updater's hand-off: Setup.exe /SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /LAUNCH
Filename: "{app}\Rialto.exe"; WorkingDir: "{app}"; Flags: nowait; Check: LaunchRequested

[UninstallDelete]
; docs\ holds Rialto's own copies of its guide pages, remade on demand.
Type: filesandordirs; Name: "{app}\docs"

[Code]
function HasSwitch(const Name: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), Name) = 0 then
      Result := True;
end;

function LaunchRequested: Boolean;
begin
  Result := WizardSilent and HasSwitch('/LAUNCH');
end;

function WantShortcuts: Boolean;
begin
  Result := not HasSwitch('/NOSHORTCUTS');
end;

function IsUnder(const Dir, Root: String): Boolean;
begin
  Result := (Root <> '') and
    (Pos(Uppercase(AddBackslash(Root)), Uppercase(AddBackslash(Dir))) = 1);
end;

{ Runs in silent installs too, so /DIR= cannot put Rialto where it could not write. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Dir: String;
begin
  Result := '';
  Dir := ExpandConstant('{app}');
  { A line of [Code] must never start with "[": ISCC reads it as a section tag. }
  if IsUnder(Dir, ExpandConstant('{commonpf64}')) or IsUnder(Dir, ExpandConstant('{commonpf32}')) or
     IsUnder(Dir, ExpandConstant('{win}')) then
    Result := FmtMessage(CustomMessage('ProtectedFolder'), [Dir,
      ExpandConstant('{localappdata}\Programs\Rialto 1.5')]);
end;

#define SampleHash(str Rel) GetSHA256OfFile(AddBackslash(PackageDir) + Rel)

{ A sample is the person's once they change it. Uninstall removes one only while it is still the
  bytes this Setup put down (hashed at compile time), so an edited sample profile is never lost. }
procedure RemoveIfUntouched(const Rel, Hash: String);
var
  Path: String;
begin
  Path := ExpandConstant('{app}\') + Rel;
  if FileExists(Path) then
    try
      if CompareText(GetSHA256OfFile(Path), Hash) = 0 then
        DeleteFile(Path);
    except
    end;
end;

{ True when anything but the uninstaller's own files is left in the folder. }
function AnythingLeft(const Dir: String): Boolean;
var
  F: TFindRec;
begin
  Result := False;
  if FindFirst(AddBackslash(Dir) + '*', F) then
    try
      repeat
        if (F.Name <> '.') and (F.Name <> '..') and (Pos('UNINS', Uppercase(F.Name)) <> 1) then
          Result := True;
      until Result or not FindNext(F);
    finally
      FindClose(F);
    end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  App: String;
begin
  App := ExpandConstant('{app}');
  if CurUninstallStep = usPostUninstall then begin
    if DirExists(App) and AnythingLeft(App) and not UninstallSilent then
      MsgBox(FmtMessage(CustomMessage('KeptYourFiles'), [App]), mbInformation, MB_OK);
    Exit;
  end;
  { usUninstall, before Inno deletes its files and folders, so Inno's own pass then removes the folders
    this leaves empty. At usPostUninstall that pass is over (seen in the second proof run). }
  if CurUninstallStep <> usUninstall then
    Exit;
  RemoveIfUntouched('input\SampleGame\PUT YOUR GAME FILES HERE.txt', '{#SampleHash("input\SampleGame\PUT YOUR GAME FILES HERE.txt")}');
  RemoveIfUntouched('input\SampleGame\background.gif', '{#SampleHash("input\SampleGame\background.gif")}');
  RemoveIfUntouched('input\SampleGame\game_logo.png', '{#SampleHash("input\SampleGame\game_logo.png")}');
  RemoveIfUntouched('input\SampleGame\game_icon.ico', '{#SampleHash("input\SampleGame\game_icon.ico")}');
  RemoveIfUntouched('input\SampleGame\disc_icon.ico', '{#SampleHash("input\SampleGame\disc_icon.ico")}');
  RemoveIfUntouched('input\SampleGame\bonus\Sample Wallpaper.jpg', '{#SampleHash("input\SampleGame\bonus\Sample Wallpaper.jpg")}');
  RemoveIfUntouched('templates\Sample Game.json', '{#SampleHash("templates\Sample Game.json")}');
  { RemoveDir removes a folder only when it is empty. }
  RemoveDir(App + '\input\SampleGame\bonus');
  RemoveDir(App + '\input\SampleGame');
end;
