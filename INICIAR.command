#!/bin/bash
# Doble clic (Mac) para instalar la primera vez e iniciar el sistema en http://127.0.0.1:8000
# Equivale a INICIAR.bat de Windows. Requiere MAMP (o MySQL de Homebrew) encendido y Python 3.11 o superior.
cd "$(dirname "$0")" || exit 1
printf '\033]0;Sistema Outbound de Cobros con IA\007'

PY=""
if [ -x "backend/.venv/bin/python" ]; then
    PY="backend/.venv/bin/python"
else
    for c in python3.13 python3.12 python3.11 \
             /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
             /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
             /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
        if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
            PY="$c"; break
        fi
    done
fi

if [ -z "$PY" ]; then
    echo
    echo "No se encontró Python 3.11 o superior (el python3 que trae macOS es 3.9 y no sirve)."
    echo "Instale Python 3.13 desde python.org (instalador para macOS) y vuelva a abrir este archivo."
    open "https://www.python.org/downloads/macos/"
    read -r -p "Presione Enter para cerrar..."
    exit 1
fi

"$PY" backend/arranque.py
echo
echo "Puede cerrar esta ventana; el sistema sigue funcionando en segundo plano."
echo "Para detenerlo abra DETENER.command"
read -r -p "Presione Enter para cerrar..."
