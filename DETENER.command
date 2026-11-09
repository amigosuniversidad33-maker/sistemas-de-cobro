#!/bin/bash
# Doble clic (Mac): detiene la API y el worker iniciados por INICIAR.command o por http://localhost/cobros/
cd "$(dirname "$0")" || exit 1
if [ ! -f backend/datos/pids.txt ]; then
    echo "No hay procesos registrados."
    read -r -p "Presione Enter para cerrar..."
    exit 0
fi
while read -r pid; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null
done < backend/datos/pids.txt
rm -f backend/datos/pids.txt
echo "Sistema detenido. Los datos permanecen en MySQL."
read -r -p "Presione Enter para cerrar..."
