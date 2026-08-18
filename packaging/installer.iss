; Inno Setup — RecallDeck. Signed single-file installer, compiled in CI.
#define AppName "RecallDeck"
#define AppVersion "1.0.5"

[Setup]
AppMutex=QuickOpen.RecallDeck
AppId={{51A0F001-0013-4E5B-8C71-9B0E2F3A0013}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=QuickOpen (quickopen.ai)
AppPublisherURL=https://quickopen.ai/projects/recall-deck
DefaultDirName={autopf}\RecallDeck
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\RecallDeck.exe
OutputDir=dist
OutputBaseFilename=RecallDeck-Setup
SetupIconFile=..\recall-deck.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
WizardImageFile=branding\wizard-large.bmp
WizardSmallImageFile=branding\wizard-small.bmp
AppCopyright=Apache-2.0. 100%% AI-built, published on QuickOpen (quickopen.ai).
VersionInfoCompany=QuickOpen
VersionInfoProductName=RecallDeck
VersionInfoVersion=1.0.5.0
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=RecallDeck is a 100%% AI-built, open-source offline tool, published on QuickOpen (quickopen.ai).%n%nThis will install it on your computer.
BeveledLabel=QuickOpen · quickopen.ai

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "trustca"; Description: "Trust the QuickOpen Root CA (lets Windows verify QuickOpen signatures)"; GroupDescription: "Security:"; Flags: unchecked

[Files]
Source: "staging\RecallDeck.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\quickopen-root.crt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "staging\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme skipifsourcedoesntexist
Source: "staging\LICENSE"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\RecallDeck"; Filename: "{app}\RecallDeck.exe"; IconFilename: "{app}\RecallDeck.exe"
Name: "{group}\Uninstall RecallDeck"; Filename: "{uninstallexe}"
Name: "{autodesktop}\RecallDeck"; Filename: "{app}\RecallDeck.exe"; IconFilename: "{app}\RecallDeck.exe"; Tasks: desktopicon

[Run]
Filename: "certutil.exe"; Parameters: "-addstore -user Root ""{app}\quickopen-root.crt"""; Tasks: trustca; Flags: runhidden; StatusMsg: "Trusting the QuickOpen Root CA..."
Filename: "{app}\RecallDeck.exe"; Description: "Launch RecallDeck now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\RecallDeck"

