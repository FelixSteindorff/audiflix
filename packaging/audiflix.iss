; Inno Setup script for Audiflix.
;
; Builds a single Audiflix-<version>-Setup.exe from the PyInstaller onedir
; output in dist\Audiflix. The bundled VLC runtime is installed as an internal
; part of the application: no separate entry in the start menu, no separate
; uninstall entry, no file associations.
;
; Compile with:  python build_exe.py --installer
;            or: iscc /DAppVersion=0.2.0 packaging\audiflix.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef VlcVersion
  #define VlcVersion "unknown"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\Audiflix"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

#define AppName "Audiflix"
#define AppPublisher "Felix Steindorff"
#define AppUrl "https://github.com/FelixSteindorff/audiflix"
#define AppExe "audiflix.exe"

[Setup]
AppId={{9B1F6A2E-63C4-4D7B-9E3B-6D2A1F4C58A1}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Accessible desktop client for Audiobookshelf

; Per-user install by default: no administrator rights required, which also
; keeps the plugin cache writable.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes

LicenseFile=..\LICENSE
InfoAfterFile=..\packaging\INSTALL_NOTES.txt
OutputDir={#OutputDir}
OutputBaseFilename={#AppName}-{#AppVersion}-Setup
SetupIconFile=..\src\audiflix\resources\audiflix.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} {#AppVersion}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The whole PyInstaller output, including the bundled VLC runtime under
; _internal\vlc. VLC is an implementation detail of Audiflix here - it is not
; registered, not added to the PATH and not shown to the user as an app.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; DestName: "THIRD_PARTY_NOTICES.txt"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; DestName: "README.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "Accessible Audiobookshelf client"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; Pre-build the libVLC plugin cache so the first playback does not have to scan
; every module. Purely an optimisation - Audiflix works without it.
Filename: "{app}\_internal\vlc\vlc-cache-gen.exe"; Parameters: """{app}\_internal\vlc\plugins"""; \
    StatusMsg: "Preparing the audio engine..."; Flags: runhidden skipifdoesntexist

Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Generated at runtime by libVLC, so Inno Setup does not know about it.
Type: files; Name: "{app}\_internal\vlc\plugins\plugins.dat"
Type: dirifempty; Name: "{app}\_internal\vlc\plugins"
Type: dirifempty; Name: "{app}\_internal\vlc"
Type: dirifempty; Name: "{app}\_internal"
Type: dirifempty; Name: "{app}"

[Messages]
; Mention the bundled engine where users look for it.
english.WelcomeLabel2=This will install [name/ver] on your computer.%n%nAudiflix includes its own audio engine (VLC {#VlcVersion}), so you do not need to install VLC separately.
german.WelcomeLabel2=[name/ver] wird auf Ihrem Computer installiert.%n%nAudiflix bringt eine eigene Audio-Engine mit (VLC {#VlcVersion}); eine separate VLC-Installation ist nicht erforderlich.
