' Inicia el sistema (API + worker) sin abrir ninguna ventana. Lo usa la tarea programada «SistemaCobros».
' Si el sistema ya está en ejecución, arranque.py no hace nada.
Set fso = CreateObject("Scripting.FileSystemObject")
raiz = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
py = raiz & "\backend\.venv\Scripts\python.exe"
CreateObject("WScript.Shell").Run """" & py & """ """ & raiz & "\backend\arranque.py"" --fondo", 0, False
