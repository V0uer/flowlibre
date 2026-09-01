; Instalador de FlowLibre para Windows.
;
; Construir:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\flowlibre.iss
; Requiere que packaging\dist\FlowLibre exista (ver packaging\flowlibre.spec).
;
; Decisiones que NO son cosmeticas:
;
; - Instalacion POR USUARIO en %LOCALAPPDATA%, no en Program Files. Sin UAC, sin
;   pedirle la contrasena de administrador a nadie, y sin el problema de permisos
;   que hace imposible escribir junto al programa.
; - El desinstalador NO borra %APPDATA%\FlowLibre. Ahi vive el historial de
;   dictados, que es lo unico que el usuario no puede reconstruir. Se pregunta.
; - Sin firma de codigo: Windows va a mostrar "Windows protegio tu PC". Las
;   instrucciones para saltarlo van en la pagina de descarga y en el README.

#define Nombre "FlowLibre"
#define Version "2.0.0"
#define Autor "V0uer"
#define Ejecutable "FlowLibre.exe"

[Setup]
AppId={{7E2B1F4A-9C3D-4E58-9A21-FL0WL1BRE2026}
AppName={#Nombre}
AppVersion={#Version}
AppPublisher={#Autor}
DefaultDirName={localappdata}\Programs\{#Nombre}
DefaultGroupName={#Nombre}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\packaging\salida
OutputBaseFilename={#Nombre}-Setup-{#Version}
SetupIconFile=..\assets\icons\FlowLibre.ico
UninstallDisplayIcon={app}\{#Ejecutable}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"
Name: "autoinicio"; Description: "Abrir FlowLibre al iniciar Windows"; GroupDescription: "Inicio:"

[Files]
Source: "dist\FlowLibre\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#Nombre}"; Filename: "{app}\{#Ejecutable}"
Name: "{userdesktop}\{#Nombre}"; Filename: "{app}\{#Ejecutable}"; Tasks: escritorio

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "FlowLibre"; ValueData: """{app}\{#Ejecutable}"""; Flags: uninsdeletevalue; Tasks: autoinicio

[Run]
Filename: "{app}\{#Ejecutable}"; Description: "Abrir FlowLibre"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; El bundle de PyInstaller deja .pyc y carpetas propias al correr; se limpian.
Type: filesandordirs; Name: "{app}\_internal\__pycache__"

[Code]
// Al desinstalar, los datos del usuario se preguntan aparte. Borrar el historial
// de dictados sin avisar seria destruir lo unico irrecuperable de la app.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Datos: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Datos := ExpandConstant('{userappdata}\FlowLibre');
    if DirExists(Datos) then
      if MsgBox('¿Borrar también tu configuración y tu historial de dictados?' + #13#10 +
                'Está en: ' + Datos + #13#10#13#10 +
                'Si piensas reinstalar FlowLibre, responde No.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(Datos, True, True, True);
  end;
end;
